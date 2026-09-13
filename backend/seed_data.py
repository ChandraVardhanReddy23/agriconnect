"""Seed demo users, listings and mandi prices. Run: python -m backend.seed_data"""

from .db import get_connection, init_db

USERS = [
    ("Ravi Kumar", "ravi@agri.demo", "ravi123", "farmer", "Nashik", "9000000001"),
    ("Meena Devi", "meena@agri.demo", "meena123", "farmer", "Pune", "9000000002"),
    ("Arjun Patil", "arjun@agri.demo", "arjun123", "farmer", "Aurangabad", "9000000003"),
    ("Sita Farms", "sita@agri.demo", "sita123", "farmer", "Nagpur", "9000000004"),
    ("FreshMart", "freshmart@agri.demo", "fresh123", "buyer", "Mumbai", "9100000001"),
    ("Green Basket", "green@agri.demo", "green123", "buyer", "Pune", "9100000002"),
    ("Hotel Harvest", "hotel@agri.demo", "hotel123", "buyer", "Nashik", "9100000003"),
    ("AgroFoods", "agro@agri.demo", "agro123", "buyer", "Nagpur", "9100000004"),
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
                "INSERT INTO users (name,email,password,role,location,phone) VALUES (?,?,?,?,?,?)", user
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
        prices = [
            ("Tomato", "Nashik Mandi", 2100, "quintal"),
            ("Onion", "Pune Mandi", 1750, "quintal"),
            ("Wheat", "Aurangabad Mandi", 2550, "quintal"),
            ("Cotton", "Nagpur Mandi", 6900, "quintal"),
        ]
        conn.executemany("INSERT INTO mandi_prices (crop,market,price,unit) VALUES (?,?,?,?)", prices)
    print("AgriConnect demo credentials (passwords are intentionally plaintext for this MVP):")
    for user in USERS:
        print(f"{user[3]:7} {user[1]:24} / {user[2]}")


if __name__ == "__main__":
    seed()
