"""Optional Groq advisory integration with deterministic offline behavior."""

import json
import os
import re
from typing import Any

EXTRACTION_KEYS = (
    "crop", "quantity", "quality_grade", "location", "expected_price",
    "availability_start", "availability_end",
)


def _fallback(crop: str, question: str) -> str:
    return (
        f"For {crop}, use clean seed, monitor soil moisture, and inspect leaves daily. "
        f"Regarding '{question}', consult your local agriculture officer before applying "
        "any chemical and follow the label dosage."
    )


def _strict_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.S)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response did not contain JSON")
        candidate = candidate[start:end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        raise ValueError("model JSON must contain an answer string")
    return parsed


def get_advice(crop: str, question: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _fallback(crop, question)

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            temperature=0,
            messages=[
                {"role": "system", "content": (
                    "Return only JSON: {\"answer\":\"...\"}. The answer must be under 120 words, "
                    "with one-line summary followed by up to 4 bullet points using '- '. "
                    "Do not use headers or bold markdown."
                )},
                {"role": "user", "content": f"Crop: {crop}\nQuestion: {question}"},
            ],
        )
        parsed = _strict_json(response.choices[0].message.content or "")
        return parsed["answer"]
    except Exception as exc:
        print(f"WARNING: Groq advisory call failed, falling back: {exc}")
        return _fallback(crop, question)


def generate_market_narrative(
    crop: str, region: str, current_average: float | None, regional_average: float | None,
    change_percent: float | None, available: bool,
) -> str | None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or not available or current_average is None or regional_average is None or change_percent is None:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            temperature=0.2,
            messages=[{
                "role": "system",
                "content": (
                    "Write a short 2-3 sentence proactive market recommendation. Use only the "
                    "numbers supplied by the user; do not invent, estimate, or assume any other "
                    "price data. Return plain text only."
                ),
            }, {
                "role": "user",
                "content": (
                    f"Crop: {crop}\nRegion: {region}\nCurrent average: {current_average}\n"
                    f"Regional average: {regional_average}\nChange percent: {change_percent}\n"
                    f"Available: {available}"
                ),
            }],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None


def extract_listing(raw_text: str) -> dict[str, Any]:
    """Extract the structured listing shape used by the demo wizard."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for natural-language listing extraction")
    try:
        from groq import APIError, Groq
    except ImportError as exc:
        raise RuntimeError("GROQ_API_KEY is set but groq package is not installed") from exc

    prompt = (
        "Extract structured data from this farmer's produce listing. Return ONLY valid JSON "
        "with these exact keys: crop (string), quantity (number, in quintals), "
        "quality_grade (one of 'A','B','C'), location (non-empty string), expected_price (number, per "
        "quintal), availability_start (YYYY-MM-DD), availability_end (YYYY-MM-DD). "
        "No other text, markdown, or code fences.\n\nListing:\n" + raw_text
    )
    client = Groq(api_key=api_key)
    last_error: Exception | None = None
    for reminder in ("", "\nReturn only the JSON object now."):
        try:
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                temperature=0.2,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": raw_text + reminder},
                ],
            )
            content = response.choices[0].message.content or ""
            candidate = content.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict) or any(key not in parsed for key in EXTRACTION_KEYS):
                raise ValueError("model response is missing required listing fields")
            return parsed
        except APIError as exc:
            raise RuntimeError(f"Groq listing extraction failed: {exc}") from exc
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = exc
    raise ValueError("Groq returned invalid listing JSON after two attempts") from last_error
