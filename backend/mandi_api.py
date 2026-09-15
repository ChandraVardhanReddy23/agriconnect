"""Small, failure-safe client for the data.gov.in Agmarknet API."""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


def fetch_live_prices(crop: str, state: str, limit: int = 10) -> list[dict]:
    """Return normalized current mandi prices, or an empty list on failure."""
    api_key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if not api_key or api_key.lower() in {"your-key-here", "your-data-gov-api-key"}:
        return []

    params = {
        "api-key": api_key,
        "format": "json",
        "limit": max(1, min(limit, 100)),
        "filters[commodity]": crop,
        "filters[state]": state,
    }
    request = Request(
        f"{AGMARKNET_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "AgriConnect/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
        records = payload.get("records", [])
        if not isinstance(records, list):
            return []

        prices = []
        for record in records:
            try:
                price = float(
                    record.get("modal_price")
                    or record.get("Modal_Price")
                    or record.get("max_price")
                    or record.get("Max Price")
                )
                market = str(record.get("market") or record.get("Market") or "").strip()
                recorded_on = str(
                    record.get("arrival_date")
                    or record.get("Arrival_Date")
                    or record.get("reported_date")
                    or ""
                ).strip()
                if price <= 0 or not market:
                    continue
                prices.append(
                    {
                        "crop": crop,
                        "market": market,
                        "price": price,
                        "unit": "quintal",
                        "recorded_on": recorded_on or None,
                    }
                )
            except (TypeError, ValueError):
                continue
        return prices
    except Exception:
        return []
