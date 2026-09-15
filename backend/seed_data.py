"""Seed demo users, listings, orders and mandi prices. Run: python -m backend.seed_data"""

from datetime import datetime, timedelta
from .db import get_connection, init_db

USERS = [
    ("Ravi Kumar", "ravi@agri.demo", "ravi123", "farmer", "Nashik", "9000000001", 4.8),
    ("Meena Devi", "meena@agri.demo", "meena123", "farmer", "Pune", "9000000002", 4.2),
    ("Arjun Patil", "arjun@agri.demo", "arjun123", "farmer", "Aurangabad", "9000000003", 3.8),
    ("Sita Farms", "sita@agri.demo", "sita123", "farmer", "Nagpur", "9000000004", 4.6),
    ("FreshMart", "freshmart@agri.demo", "fresh123", "buyer", "Mumbai", "9100000001", 4.0),
    ("Green Basket", "green@agri.demo", "green123", "buyer", "Pune", "9100000002", 4.0),
    ("Hotel Harvest", "hotel@agri.demo", "hotel123", "buyer", "Nashik", "9100000003", 4.0),
    ("AgroFoods", "agro@agri.demo", "agro123", "buyer", "Nagpur", "9100000004", 4.0),
]


def seed() -> None:
    init_db()
    with get_connection() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("AgriConnect demo data already exists.")
            print("Demo credentials: ravi@agri.demo / ravi123 and freshmart@agri.demo / fresh123")
            return
        ids = []
        for user in USERS:
            ids.append(conn.execute(
                "INSERT INTO users (name,email,password,role,location,phone,rating) VALUES (?,?,?,?,?,?,?)", user
            ).lastrowid)
        listings = [
            (ids[0], "Tomato", "Hybrid", 120, "quintal", 2200, "Nashik", "2026-09-01", "A", "Fresh red tomatoes"),
            (ids[1], "Onion", "Red", 200, "quintal", 1800, "Pune", "2026-08-28", "A", "Stored onions"),
            (ids[2], "Wheat", "Lokwan", 85, "quintal", 2600, "Aurangabad", "2026-08-20", "standard", "Clean wheat"),
            (ids[3], "Cotton", "Desi", 60, "quintal", 7000, "Nagpur", "2026-08-15", "A", "Grade A cotton"),
        ]
        conn.executemany(
            """INSERT INTO listings
            (farmer_id,crop,variety,quantity,unit,price,location,harvest_date,quality,description)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", listings
        )
        listing_ids = [
            row["id"] for row in conn.execute(
                "SELECT id FROM listings WHERE farmer_id IN (?,?,?,?) ORDER BY id",
                tuple(ids[:4]),
            ).fetchall()
        ]
        orders = [
            (listing_ids[0], ids[4], 20, 2200, "2026-09-20"),
            (listing_ids[1], ids[4], 30, 1800, "2026-09-22"),
            (listing_ids[2], ids[5], 15, 2600, "2026-09-19"),
            (listing_ids[0], ids[6], 10, 2200, "2026-09-18"),
        ]
        conn.executemany(
            """INSERT INTO orders
               (listing_id,buyer_id,quantity,agreed_price,delivery_deadline)
               VALUES (?,?,?,?,?)""",
            orders,
        )
        conn.executemany(
            "UPDATE listings SET status='reserved' WHERE id=?",
            [(order[0],) for order in orders],
        )
        today = datetime.now().date()
        trends = {
            "Tomato": [2060, 2080, 2090, 2110, 2130, 2150, 2170, 2190, 2220],
            "Onion": [1830, 1810, 1800, 1790, 1770, 1760, 1750, 1730, 1710],
            "Wheat": [2550, 2555, 2548, 2552, 2550, 2549, 2553, 2551, 2550],
            "Cotton": [6820, 6860, 6890, 6930, 6970, 7000, 7040, 7070, 7100],
        }
        markets = {
            "Tomato": "Nashik Mandi", "Onion": "Nashik Mandi",
            "Wheat": "Nashik Mandi", "Cotton": "Nashik Mandi",
        }
        prices = [
            (crop, markets[crop], price, "quintal", (today - timedelta(days=offset)).isoformat())
            for crop, values in trends.items()
            for offset, price in enumerate(reversed(values))
        ]
        conn.executemany(
            "INSERT INTO mandi_prices (crop,market,price,unit,recorded_on) VALUES (?,?,?,?,?)",
            prices,
        )
    print("AgriConnect demo credentials (passwords are intentionally plaintext for this MVP):")
    for user in USERS:
        print(f"{user[3]:7} {user[1]:24} / {user[2]}")


if __name__ == "__main__":
    seed()
