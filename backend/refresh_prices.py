"""Refresh seeded mandi prices from Agmarknet without risking fallback data.

Run from the repository root with: python -m backend.refresh_prices
"""

from datetime import date, datetime

from .db import get_connection, init_db
from .mandi_api import fetch_live_prices


CROPS = ("Tomato", "Onion", "Wheat", "Cotton")
STATE = "Maharashtra"


def _recorded_on(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], pattern).date().isoformat()
        except ValueError:
            continue
    return value[:10]


def refresh() -> None:
    init_db()
    with get_connection() as conn:
        for crop in CROPS:
            prices = fetch_live_prices(crop, STATE, limit=10)
            if not prices:
                print(f"{crop}: no live data; keeping existing rows")
                continue
            conn.execute("DELETE FROM mandi_prices WHERE lower(crop)=lower(?)", (crop,))
            conn.executemany(
                """INSERT INTO mandi_prices
                   (crop, market, price, unit, recorded_on)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        item["crop"],
                        item["market"],
                        item["price"],
                        item.get("unit", "quintal"),
                        _recorded_on(item.get("recorded_on")),
                    )
                    for item in prices
                ],
            )
            print(f"{crop}: replaced with {len(prices)} live rows")


if __name__ == "__main__":
    refresh()
