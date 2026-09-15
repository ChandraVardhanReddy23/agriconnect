import sqlite3
from fastapi import HTTPException
from .db import get_connection, row_to_dict
from .models import LoginRequest, SignupRequest


def public_user(user: dict) -> dict:
    return {key: user[key] for key in ("id", "name", "email", "role", "location", "phone", "rating")}


def signup(payload: SignupRequest) -> dict:
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (name,email,password,role,location,phone,lat,lon) VALUES (?,?,?,?,?,?,?,?)",
                (payload.name, payload.email.lower().strip(), payload.password, payload.role,
                 payload.location, payload.phone, payload.lat, payload.lon),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Email is already registered") from exc
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone())
    return public_user(user)


def login(payload: LoginRequest) -> dict:
    with get_connection() as conn:
        user = row_to_dict(conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (payload.email.lower().strip(), payload.password),
        ).fetchone())
    if not user:
        raise HTTPException(401, "Invalid email or password")
    return public_user(user)
