import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from dotenv import load_dotenv
from models import db, Room, Player, Vote, gen_room_id, gen_room_key

load_dotenv()

app = Flask(__name__, template_folder="templates")

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "secret!")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Gunakan eventlet/gevent untuk WebSocket di production
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ----------------------- UTIL -----------------------

def room_player_count(room: Room) -> int:
    return Player.query.filter_by(room_id=room.id, is_bot=False).count() + (1 if room.vs_computer else 0)

def get_room_or_404(room_id: str) -> Room:
    r = Room.query.get(room_id)
    if not r:
        abort(404, description="Room not found")
    return r

# ----------------------- ROUTES -----------------------

with app.app_context():
    db.create_all()

@app.route("/")
def index():
    # hitung total votes sebagai contoh
    votes_count = {
        "option1": Vote.query.filter_by(option="option1").count(),
        "option2": Vote.query.filter_by(option="option2").count(),
    }
    return render_template("index.html", votes=votes_count)

@app.route("/create-circle-room", methods=["POST"])
def create_circle_room():
    data = request.get_json(silent=True) or {}
    vs_computer = bool(data.get("vs_computer", False))

    r = Room(id=gen_room_id(), key=gen_room_key(), vs_computer=vs_computer, max_players=2)
    db.session.add(r)
    db.session.commit()

    # Jika vs_computer, tambahkan bot menempati slot ke-2
    if vs_computer:
        bot = Player(sid=None, username="COMPUTER", color="#888888", is_bot=True, room_id=r.id, x=200, y=200)
        db.session.add(bot)
        db.session.commit()

    return render_template("room_created.html", room_id=r.id, room_key=r.key)

@app.route("/circle-room/<room_id>")
def circle_room(room_id):
    room = get_room_or_404(room_id)
    return render_template("game.html", room_id=room.id)

# ----------------------- VOTE FEATURE -----------------------

@socketio.on("vote")
def handle_vote(data):
    option = data.get("option")
    if option not in ("option1", "option2"):
        return
    v = Vote(option=option)
    db.session.add(v)
    db.session.commit()
    # broadcast total terkini
    counts = {
        "option1": Vote.query.filter_by(option="option1").count(),
        "option2": Vote.query.filter_by(option="option2").count(),
    }
    emit("vote_count", counts, broadcast=True)

# ----------------------- GAME FEATURE -----------------------

@socketio.on("join_room_game")
def join_room_game(data):
    """
    data: {
      room_id, room_key, username, color
    }
    """
    room_id = (data or {}).get("room_id")
    room_key = (data or {}).get("room_key")
    username = (data or {}).get("username") or "Player"
    color = (data or {}).get("color") or "#"+os.urandom(3).hex()

    room = Room.query.get(room_id)
    if not room:
        emit("join_error", {"message": "Room tidak ditemukan."})
        disconnect()
        return

    # Validasi kunci (PIN)
    if room.key != str(room_key):
        emit("join_error", {"message": "Kunci/PIN salah."})
        disconnect()
        return

    # Batas 2 pemain (vs_computer mengisi 1 slot)
    if room_player_count(room) >= room.max_players:
        emit("join_error", {"message": "Room penuh (maks 2 pemain)."})
        disconnect()
        return

    # Masukkan player
    p = Player(sid=request.sid, username=username[:32], color=color[:16], room_id=room.id)
    db.session.add(p)
    db.session.commit()

    join_room(room.id)
    broadcast_players(room.id)

@socketio.on("move_circle")
def move_circle(data):
    room_id = (data or {}).get("room_id")
    x = int((data or {}).get("x", 0))
    y = int((data or {}).get("y", 0))

    if not room_id:
        return

    player = Player.query.filter_by(sid=request.sid, room_id=room_id).first()
    if not player:
        return

    player.x = x
    player.y = y
    db.session.commit()
    broadcast_players(room_id)

@socketio.on("disconnect")
def on_disconnect():
    # Hapus player dari room mana pun
    player = Player.query.filter_by(sid=request.sid).first()
    if player:
        room_id = player.room_id
        db.session.delete(player)
        db.session.commit()
        broadcast_players(room_id)

# ----------------------- HELPERS -----------------------

def broadcast_players(room_id: str):
    """Kirim snapshot semua pemain (termasuk BOT) ke room."""
    players = Player.query.filter_by(room_id=room_id).all()
    payload = {
        str(p.id): {
            "username": p.username,
            "x": p.x,
            "y": p.y,
            "color": p.color,
            "is_bot": p.is_bot
        } for p in players
    }
    socketio.emit("update_players", payload, room=room_id)

# ----------------------- MAIN -----------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host="127.0.0.1", port=8080)
