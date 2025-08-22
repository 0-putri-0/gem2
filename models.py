import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import secrets, string

db = SQLAlchemy()

def gen_room_id():
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(6))

def gen_room_key():
    return ''.join(secrets.choice(string.digits) for _ in range(6))

class Room(db.Model):
    __tablename__ = "rooms"
    id = db.Column(db.String(12), primary_key=True)   
    key = db.Column(db.String(12), nullable=False)       
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    vs_computer = db.Column(db.Boolean, default=False, nullable=False)
    max_players = db.Column(db.Integer, default=2, nullable=False)

    players = db.relationship("Player", backref="room", cascade="all,delete-orphan")

class Player(db.Model):
    __tablename__ = "players"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sid = db.Column(db.String(64), index=True)           
    username = db.Column(db.String(32), nullable=False)
    color = db.Column(db.String(16), nullable=False)
    x = db.Column(db.Integer, default=100, nullable=False)
    y = db.Column(db.Integer, default=100, nullable=False)
    is_bot = db.Column(db.Boolean, default=False, nullable=False)

    room_id = db.Column(db.String(12), db.ForeignKey("rooms.id"), nullable=False)

class Vote(db.Model):
    __tablename__ = "votes"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    option = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now())
