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
        # This dataset often ignores or mishandles server-side filter casing.
        "limit": 1000,
    }
    request = Request(
        f"{AGMARKNET_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "AgriConnect/1.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
        records = payload.get("records", [])
        if not isinstance(records, list):
            return []
        print(f"[mandi_api] Fetched {len(records)} raw records from Agmarknet")

        crop_lower = crop.strip().lower()
        state_lower = state.strip().lower()
        prices = []
        for record in records:
            record_crop = str(
                record.get("commodity") or record.get("Commodity") or ""
            ).strip().lower()
            record_state = str(
                record.get("state") or record.get("State") or ""
            ).strip().lower()
            if crop_lower not in record_crop and record_crop not in crop_lower:
                continue
            if state_lower and state_lower not in record_state:
                continue

            try:
                price = float(
                    record.get("modal_price")
                    or record.get("Modal_Price")
                    or record.get("max_price")
                    or record.get("Max_Price")
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
            if len(prices) >= limit:
                break
        print(f"[mandi_api] Matched {len(prices)} records for crop={crop}, state={state}")
        return prices
    except Exception:
        return []
