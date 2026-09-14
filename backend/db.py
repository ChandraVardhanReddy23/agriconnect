"""SQLite persistence for the AgriConnect MVP.

WARNING: This hackathon MVP stores passwords as visible plaintext. Do not use
this implementation in production; replace it with salted password hashes.
"""

from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, Optional

DB_PATH = Path(__file__).resolve().parent / "agriconnect.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('farmer', 'buyer')),
                location TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                lat REAL,
                lon REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER NOT NULL REFERENCES users(id),
                crop TEXT NOT NULL,
                variety TEXT DEFAULT '',
                quantity REAL NOT NULL,
                unit TEXT DEFAULT 'quintal',
                price REAL NOT NULL,
                location TEXT DEFAULT '',
                harvest_date TEXT DEFAULT '',
                quality TEXT DEFAULT 'standard',
                description TEXT DEFAULT '',
                photo_url TEXT DEFAULT '',
                status TEXT DEFAULT 'available',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS demands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id INTEGER NOT NULL REFERENCES users(id),
                crop TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT DEFAULT 'quintal',
                target_price REAL DEFAULT 0,
                location TEXT DEFAULT '',
                needed_by TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL REFERENCES listings(id),
                buyer_id INTEGER NOT NULL REFERENCES users(id),
                quantity REAL NOT NULL,
                agreed_price REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                counter_price REAL,
                last_offer_by TEXT DEFAULT 'buyer',
                payment_status TEXT DEFAULT 'unpaid',
                quality_status TEXT DEFAULT 'pending',
                delivery_status TEXT DEFAULT 'placed',
                delivery_deadline TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS mandi_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT NOT NULL,
                market TEXT NOT NULL,
                price REAL NOT NULL,
                unit TEXT DEFAULT 'quintal',
                recorded_on TEXT DEFAULT CURRENT_DATE
            );
            CREATE TABLE IF NOT EXISTS advisories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER NOT NULL REFERENCES users(id),
                crop TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if "last_offer_by" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN last_offer_by TEXT DEFAULT 'buyer'")
        if "delivery_deadline" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN delivery_deadline TEXT")
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "lat" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN lat REAL")
        if "lon" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN lon REAL")
        listing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(listings)").fetchall()}
        if "photo_url" not in listing_columns:
            conn.execute("ALTER TABLE listings ADD COLUMN photo_url TEXT DEFAULT ''")


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def rows_to_dict(rows: Iterable[sqlite3.Row]) -> list[Dict[str, Any]]:
    return [dict(row) for row in rows]
