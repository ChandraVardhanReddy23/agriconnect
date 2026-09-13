from datetime import date
from math import asin, cos, radians, sin, sqrt
from typing import Any


def delivery_score(listing: dict[str, Any], buyer: dict[str, Any]) -> tuple[float, int | None]:
    try:
        availability_end = date.fromisoformat(listing.get("harvest_date", ""))
        deadline = date.fromisoformat(buyer.get("delivery_deadline", ""))
    except (TypeError, ValueError):
        return 0.5, None
    days_margin = (deadline - availability_end).days
    if days_margin >= 3:
        return 1.0, days_margin
    if days_margin >= 0:
        return 0.6, days_margin
    return 0.0, days_margin


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    value = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius * asin(sqrt(value))


def score_listing(listing: dict[str, Any], crop: str, quantity: float | None = None,
                  location: str = "") -> float:
    score = 0.0
    if listing.get("crop", "").strip().lower() == crop.strip().lower():
        score += 70
    if quantity and listing.get("quantity", 0) >= quantity:
        score += 20
    if location and listing.get("location", "").strip().lower() == location.strip().lower():
        score += 10
    return score


def rank_matches(listings: list[dict[str, Any]], crop: str,
                 quantity: float | None = None, location: str = "") -> list[dict[str, Any]]:
    ranked = []
    for listing in listings:
        item = dict(listing)
        item["match_score"] = score_listing(item, crop, quantity, location)
        if item["match_score"] >= 70:
            ranked.append(item)
    return sorted(ranked, key=lambda item: (-item["match_score"], item.get("price", 0)))
