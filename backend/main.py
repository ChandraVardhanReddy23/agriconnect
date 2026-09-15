import hashlib
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .auth import login, signup
from .db import get_connection, init_db, row_to_dict, rows_to_dict
from .llm import extract_listing, generate_market_narrative, get_advice
from .matching import delivery_score, haversine, rank_matches
from .models import (
    AdvisoryRequest, CounterRequest, DemandCreate, ListingCreate, ListingIngestRequest, LoginRequest,
    ListingUpdate, MatchRequest, OrderCreate, PaymentRequest, QualityRequest, RouteClaimRequest,
    SignupRequest, TransportPhotoRequest,
)

PLATFORM_FEE_RATE = 0.0  # 0% introductory rate during pilot phase

CITY_COORDS = {
    "nashik": (20.0059, 73.7897), "pune": (18.5204, 73.8567),
    "aurangabad": (19.8762, 75.3433), "nagpur": (21.1458, 79.0882),
    "mumbai": (19.0760, 72.8777), "vijayawada": (16.5062, 80.6480),
}


def location_point(location: str) -> tuple[float, float]:
    return CITY_COORDS.get(location.strip().lower(), (20.5937, 78.9629))

app = FastAPI(title="AgriConnect MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/signup")
@app.post("/api/signup")
def auth_signup(payload: SignupRequest) -> dict[str, Any]:
    return signup(payload)


@app.post("/api/auth/login")
@app.post("/api/login")
def auth_login(payload: LoginRequest) -> dict[str, Any]:
    return login(payload)


@app.get("/api/users/{user_id}")
def get_user(user_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        user = row_to_dict(conn.execute(
            """SELECT id,name,email,role,location,phone,rating,vehicle_type,vehicle_capacity
               FROM users WHERE id=?""", (user_id,)
        ).fetchone())
    if not user:
        raise HTTPException(404, "User not found")
    return user


@app.post("/api/listings")
def create_listing(payload: ListingCreate) -> dict[str, Any]:
    with get_connection() as conn:
        farmer = conn.execute("SELECT role FROM users WHERE id=?", (payload.farmer_id,)).fetchone()
        if not farmer or farmer["role"] != "farmer":
            raise HTTPException(400, "farmer_id must belong to a farmer")
        cursor = conn.execute(
            """INSERT INTO listings
            (farmer_id,crop,variety,quantity,unit,price,location,harvest_date,quality,description,photo_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(payload.model_dump().values()),
        )
        return row_to_dict(conn.execute("SELECT * FROM listings WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.get("/api/listings")
def list_listings(crop: str | None = None, farmer_id: int | None = None,
                  status: str = "available") -> list[dict[str, Any]]:
    clauses, args = ([] if status == "all" else ["l.status=?"],
                     [] if status == "all" else [status])
    if crop:
        clauses.append("lower(l.crop)=lower(?)")
        args.append(crop)
    if farmer_id:
        clauses.append("l.farmer_id=?")
        args.append(farmer_id)
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT l.*, u.name AS farmer_name, u.rating AS farmer_rating FROM listings l JOIN users u ON u.id=l.farmer_id
                WHERE {' AND '.join(clauses)} ORDER BY l.created_at DESC""", args
        ).fetchall()
    return rows_to_dict(rows)


@app.post("/api/listings/ingest")
def ingest_listing(payload: ListingCreate | ListingIngestRequest) -> dict[str, Any]:
    if isinstance(payload, ListingCreate):
        return create_listing(payload)
    try:
        extracted = extract_listing(payload.raw_text)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        listing = ListingCreate(
            farmer_id=payload.farmer_id,
            crop=str(extracted["crop"]),
            quantity=float(extracted["quantity"]),
            price=float(extracted["expected_price"]),
            location=str(extracted["location"]),
            harvest_date=str(extracted["availability_start"]),
            quality=str(extracted["quality_grade"]),
            description=payload.raw_text,
            photo_url=payload.photo_url,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            422, "Groq could not extract valid listing details; please use the structured form."
        ) from exc
    return create_listing(listing)


@app.patch("/api/listings/{listing_id}")
def update_listing(listing_id: int, payload: ListingUpdate) -> dict[str, Any]:
    with get_connection() as conn:
        listing = conn.execute(
            "SELECT farmer_id FROM listings WHERE id=?", (listing_id,)
        ).fetchone()
        if not listing:
            raise HTTPException(404, "Listing not found")
        if listing["farmer_id"] != payload.farmer_id:
            raise HTTPException(403, "Only the listing farmer can update it")
        conn.execute(
            """UPDATE listings SET crop=?,variety=?,quantity=?,unit=?,price=?,location=?,
               harvest_date=?,quality=?,description=?,photo_url=? WHERE id=?""",
            (payload.crop, payload.variety, payload.quantity, payload.unit, payload.price,
             payload.location, payload.harvest_date, payload.quality, payload.description,
             payload.photo_url, listing_id),
        )
        return row_to_dict(conn.execute(
            "SELECT * FROM listings WHERE id=?", (listing_id,)
        ).fetchone())


@app.post("/api/matches")
def matches(payload: MatchRequest) -> list[dict[str, Any]]:
    listings = list_listings(crop=None, status="available")
    return rank_matches(listings, payload.crop, payload.quantity, payload.location)


@app.post("/api/listings/match")
def match_listings(payload: MatchRequest) -> list[dict[str, Any]]:
    return matches(payload)


@app.post("/api/listings/{listing_id}/match")
def match_listing_buyers(listing_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        listing = row_to_dict(conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone())
        if not listing:
            raise HTTPException(404, "Listing not found")
        rows = conn.execute(
            """SELECT o.*, buyer.name AS buyer_name, buyer.location AS buyer_location
               FROM orders o JOIN users buyer ON buyer.id=o.buyer_id
               WHERE o.listing_id=? ORDER BY o.created_at DESC""",
            (listing_id,),
        ).fetchall()
        demand_rows = conn.execute(
            """SELECT d.*, buyer.name AS buyer_name, buyer.location AS buyer_location
               FROM demands d JOIN users buyer ON buyer.id=d.buyer_id
               WHERE lower(d.crop)=lower(?) AND d.status='open'""",
            (listing["crop"],),
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        price_score = min(item["agreed_price"] / listing["price"], 1.2) / 1.2
        qty_score = 1 - abs(item["quantity"] - listing["quantity"]) / max(item["quantity"], listing["quantity"])
        farmer_point = location_point(listing["location"])
        buyer_point = location_point(item["buyer_location"] or "")
        distance_km = haversine(*farmer_point, *buyer_point)
        distance_score = max(0, 1 - distance_km / 300)
        quality_score = 1.0 if listing["quality"].lower() in ("a", "premium") else 0.8
        delivery_fit, days_margin = delivery_score(
            listing, {"delivery_deadline": item.get("delivery_deadline") or ""}
        )
        breakdown = {
            "price_score": round(price_score, 2),
            "qty_score": round(max(0, qty_score), 2),
            "dist_score": round(distance_score, 2),
            "quality_score": quality_score,
            "delivery_score": delivery_fit,
            "days_margin": days_margin,
            "distance_km": round(distance_km, 2),
        }
        item["score_breakdown"] = breakdown
        item["total_score"] = round(
            0.30 * price_score + 0.20 * max(0, qty_score) +
            0.20 * distance_score + 0.15 * quality_score + 0.15 * delivery_fit, 2
        )
        results.append(item)
    for demand in demand_rows:
        item = dict(demand)
        item["buyer_id"] = demand["buyer_id"]
        item["quantity"] = demand["quantity"]
        item["agreed_price"] = demand["target_price"] or listing["price"]
        item["is_demand"] = True
        fit, days_margin = delivery_score(
            {**listing, "harvest_date": listing.get("harvest_date", "")},
            {"delivery_deadline": demand["needed_by"]},
        )
        qty_score = 1 - abs(item["quantity"] - listing["quantity"]) / max(item["quantity"], listing["quantity"])
        price_score = min(item["agreed_price"] / listing["price"], 1.2) / 1.2
        item["score_breakdown"] = {
            "price_score": round(price_score, 2), "qty_score": round(max(0, qty_score), 2),
            "dist_score": 0.7, "quality_score": 0.8, "delivery_score": fit,
            "days_margin": days_margin,
        }
        item["total_score"] = round(
            0.30 * price_score + 0.20 * max(0, qty_score) + 0.20 * 0.7 +
            0.15 * 0.8 + 0.15 * fit, 2
        )
        results.append(item)
    return sorted(results, key=lambda item: item["total_score"], reverse=True)


@app.get("/api/listings/{listing_id}/preview-profit")
def preview_profit(listing_id: int, buyer_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        listing = row_to_dict(conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone())
        buyer = row_to_dict(conn.execute("SELECT * FROM users WHERE id=? AND role='buyer'", (buyer_id,)).fetchone())
        demand = row_to_dict(conn.execute(
            "SELECT target_price FROM demands WHERE buyer_id=? AND lower(crop)=lower(?) ORDER BY created_at DESC LIMIT 1",
            (buyer_id, listing["crop"] if listing else ""),
        ).fetchone()) if listing else None
    if not listing or not buyer:
        raise HTTPException(404, "Listing or buyer not found")
    offer = (demand or {}).get("target_price") or listing["price"]
    estimated_total = offer * listing["quantity"]
    farmer_point = location_point(listing["location"])
    buyer_point = location_point(buyer["location"])
    distance = haversine(*farmer_point, *buyer_point)
    estimated_logistics = distance * 8 * listing["quantity"] / 100
    estimated_platform_fee = estimated_total * PLATFORM_FEE_RATE
    return {
        "buyer_id": buyer_id, "offer_price": offer, "estimated_total": estimated_total,
        "estimated_logistics": estimated_logistics, "estimated_platform_fee": estimated_platform_fee,
        "estimated_net_payout": estimated_total - estimated_logistics - estimated_platform_fee,
    }


@app.get("/api/matches")
def matches_query(crop: str, quantity: float | None = None, location: str = "") -> list[dict[str, Any]]:
    return matches(MatchRequest(crop=crop, quantity=quantity, location=location))


@app.post("/api/demands")
def create_demand(payload: DemandCreate) -> dict[str, Any]:
    with get_connection() as conn:
        buyer = conn.execute("SELECT role FROM users WHERE id=?", (payload.buyer_id,)).fetchone()
        if not buyer or buyer["role"] != "buyer":
            raise HTTPException(400, "buyer_id must belong to a buyer")
        cursor = conn.execute(
            """INSERT INTO demands (buyer_id,crop,quantity,unit,target_price,location,needed_by)
               VALUES (?,?,?,?,?,?,?)""",
            tuple(payload.model_dump().values()),
        )
        return row_to_dict(conn.execute("SELECT * FROM demands WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.post("/api/buyer/demand")
def create_buyer_demand(payload: DemandCreate) -> dict[str, Any]:
    return create_demand(payload)


@app.get("/api/demands")
def list_demands(buyer_id: int | None = None) -> list[dict[str, Any]]:
    query, args = "SELECT * FROM demands", []
    if buyer_id:
        query += " WHERE buyer_id=?"
        args.append(buyer_id)
    query += " ORDER BY created_at DESC"
    with get_connection() as conn:
        return rows_to_dict(conn.execute(query, args).fetchall())


@app.post("/api/orders")
def create_order(payload: OrderCreate) -> dict[str, Any]:
    with get_connection() as conn:
        listing = row_to_dict(conn.execute("SELECT * FROM listings WHERE id=?", (payload.listing_id,)).fetchone())
        buyer = conn.execute("SELECT role FROM users WHERE id=?", (payload.buyer_id,)).fetchone()
        if not listing or listing["status"] != "available":
            raise HTTPException(404, "Listing is not available")
        if not buyer or buyer["role"] != "buyer":
            raise HTTPException(400, "buyer_id must belong to a buyer")
        if payload.quantity > listing["quantity"]:
            raise HTTPException(400, "Requested quantity exceeds listing")
        price = payload.agreed_price or listing["price"]
        delivery_deadline = payload.delivery_deadline
        if delivery_deadline is None:
            demand = conn.execute(
                """SELECT needed_by FROM demands
                   WHERE buyer_id=? AND lower(crop)=lower(?) AND needed_by != ''
                   ORDER BY created_at DESC LIMIT 1""",
                (payload.buyer_id, listing["crop"]),
            ).fetchone()
            delivery_deadline = demand["needed_by"] if demand else None
        cursor = conn.execute(
            """INSERT INTO orders
               (listing_id,buyer_id,quantity,agreed_price,last_offer_by,delivery_deadline)
               VALUES (?,?,?,?,?,?)""",
            (payload.listing_id, payload.buyer_id, payload.quantity, price, "buyer",
             delivery_deadline),
        )
        conn.execute("UPDATE listings SET status='reserved' WHERE id=?", (payload.listing_id,))
        order_id = cursor.lastrowid
    return _order(order_id)


def _add_order_values(order: dict[str, Any]) -> dict[str, Any]:
    delivery_status = order.get("delivery_status", "placed")
    raw_status = order.get("status", "pending")
    if raw_status in ("completed",):
        order_status = "COMPLETED"
    elif raw_status in ("disputed",):
        order_status = "DISPUTED"
    elif delivery_status == "pickup_scheduled":
        order_status = "PICKUP_SCHEDULED"
    elif delivery_status == "in_transit":
        order_status = "IN_TRANSIT"
    elif delivery_status == "delivered":
        order_status = "DELIVERED"
    elif raw_status in ("accepted", "paid"):
        order_status = "CONFIRMED"
    elif raw_status in ("countered", "suggested"):
        order_status = "NEGOTIATING"
    else:
        order_status = "MATCHED"
    payment_status = {
        "unpaid": "NONE",
        "pending": "PENDING",
        "paid": "ESCROW_HELD",
        "escrow_held": "ESCROW_HELD",
        "released": "RELEASED",
        "disputed": "DISPUTED",
    }.get(order.get("payment_status", "unpaid"), str(order.get("payment_status", "NONE")).upper())
    order["order_status"] = order_status
    order["payment_status"] = payment_status
    current_offer = order["counter_price"] or order["agreed_price"]
    order["current_offer_price"] = current_offer
    if current_offer:
        total_amount = current_offer * order["quantity"]
        order["total_amount"] = round(total_amount, 2)
        order["platform_fee"] = round(total_amount * PLATFORM_FEE_RATE, 2)
        order["logistics_cost"] = round(total_amount * 0.08, 2)
        order["net_farmer_payout"] = round(total_amount - order["platform_fee"] - order["logistics_cost"], 2)
        order["payout_is_final"] = order_status in (
            "CONFIRMED", "PICKUP_SCHEDULED", "IN_TRANSIT", "DELIVERED",
            "COMPLETED", "DISPUTED",
        )
    else:
        order["total_amount"] = None
        order["platform_fee"] = None
        order["logistics_cost"] = None
        order["net_farmer_payout"] = None
        order["payout_is_final"] = False
    return order


def _order(order_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        order = row_to_dict(conn.execute(
            """SELECT o.*, l.crop,l.variety,l.location,l.farmer_id,l.price AS listing_price,
                      u.name AS farmer_name, u.rating AS farmer_rating, buyer.name AS buyer_name,
                      buyer.location AS buyer_location, transporter.name AS transporter_name,
                      transporter.phone AS transporter_phone
               FROM orders o JOIN listings l ON l.id=o.listing_id
               JOIN users u ON u.id=l.farmer_id
               JOIN users buyer ON buyer.id=o.buyer_id
               LEFT JOIN users transporter ON transporter.id=o.transporter_id
               WHERE o.id=?""", (order_id,)).fetchone())
    if not order:
        raise HTTPException(404, "Order not found")
    return _add_order_values(order)


def _adjust_farmer_rating(farmer_id: int, delta: float) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE users SET rating = MAX(1.0, MIN(5.0, COALESCE(rating, 4.0) + ?))
               WHERE id=?""",
            (delta, farmer_id),
        )


@app.get("/api/orders/{order_id}")
def get_order(order_id: int) -> dict[str, Any]:
    return _order(order_id)


@app.get("/api/orders")
def list_orders(user_id: int | None = None, role: str | None = None) -> list[dict[str, Any]]:
    query = """SELECT o.*, l.crop,l.location,l.farmer_id,
                      farmer.name AS farmer_name, buyer.name AS buyer_name,
                      transporter.name AS transporter_name
               FROM orders o
               JOIN listings l ON l.id=o.listing_id
               JOIN users farmer ON farmer.id=l.farmer_id
               JOIN users buyer ON buyer.id=o.buyer_id
               LEFT JOIN users transporter ON transporter.id=o.transporter_id"""
    args = []
    if user_id and role == "buyer":
        query += " WHERE o.buyer_id=?"
        args.append(user_id)
    elif user_id and role == "farmer":
        query += " WHERE l.farmer_id=?"
        args.append(user_id)
    query += " ORDER BY o.created_at DESC"
    with get_connection() as conn:
        rows = rows_to_dict(conn.execute(query, args).fetchall())
    return [_add_order_values(row) for row in rows]


@app.post("/api/orders/{order_id}/counter")
def counter_order(order_id: int, payload: CounterRequest) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] not in ("MATCHED", "NEGOTIATING"):
        raise HTTPException(400, f"Cannot negotiate — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET counter_price=?,last_offer_by=?,status='countered',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (payload.counter_price, payload.by, order_id))
    return _order(order_id)


@app.post("/api/orders/{order_id}/suggest")
def suggest_order(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] not in ("MATCHED", "NEGOTIATING"):
        raise HTTPException(400, f"Cannot negotiate — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET counter_price=agreed_price,status='suggested',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (order_id,))
    return _order(order_id)


@app.get("/api/orders/{order_id}/suggest-counter")
def suggest_counter(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    suggested = round((order["listing_price"] + order["current_offer_price"]) / 2, 2)
    return {"suggested_price": suggested, "reasoning": "A midpoint between the listing price and current offer."}


@app.post("/api/orders/{order_id}/accept")
def accept_order(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] not in ("MATCHED", "NEGOTIATING"):
        raise HTTPException(400, f"Cannot negotiate — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET agreed_price=?,status='accepted',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (order["current_offer_price"], order_id))
    return _order(order_id)


@app.post("/api/orders/{order_id}/pay")
def pay_order(order_id: int, payload: PaymentRequest) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] != "CONFIRMED":
        raise HTTPException(400, "Cannot pay — price not yet agreed")
    if order["payment_status"] == "ESCROW_HELD":
        raise HTTPException(400, "Payment already made")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET payment_status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (order_id,))
    return _order(order_id)


@app.post("/api/orders/{order_id}/advance")
def advance_order(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] in ("PICKUP_SCHEDULED", "IN_TRANSIT"):
        raise HTTPException(
            400, "Cannot advance delivery — use the transporter /pickup and /deliver endpoints with a photo",
        )
    if order["payment_status"] != "ESCROW_HELD":
        raise HTTPException(400, "Cannot advance delivery — payment not yet escrowed")
    if order["order_status"] != "CONFIRMED":
        raise HTTPException(400, f"Cannot advance — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET delivery_status='pickup_scheduled',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (order_id,))
    return _order(order_id)


def _route_id(order_ids: list[int]) -> str:
    digest = hashlib.sha1(",".join(map(str, sorted(order_ids))).encode()).hexdigest()[:12]
    return f"route-{digest}"


def _route_from_rows(rows: list[dict[str, Any]], route_id: str) -> dict[str, Any]:
    buyer_point = location_point(rows[0]["buyer_location"])
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["farmer_location"].strip().lower()
        stop = grouped.setdefault(key, {
            "farmer_name": row["farmer_name"],
            "farmer_phone": row["farmer_phone"],
            "location": row["farmer_location"],
            "point": location_point(row["farmer_location"]),
            "quantity": 0,
            "order_count": 0,
            "order_ids": [],
            "orders": [],
        })
        stop["quantity"] += row["quantity"]
        stop["order_count"] += 1
        stop["order_ids"].append(row["id"])
        stop["orders"].append({
            "id": row["id"],
            "quantity": row["quantity"],
            "delivery_status": row["delivery_status"],
            "order_status": _add_order_values({
                "status": row["status"],
                "payment_status": row["payment_status"],
                "delivery_status": row["delivery_status"],
                "counter_price": None,
                "agreed_price": 0,
                "quantity": row["quantity"],
            })["order_status"],
            "payment_status": row["payment_status"],
        })
    remaining = list(grouped.values())
    current = buyer_point
    stops = []
    total_distance = 0
    while remaining:
        stop = min(remaining, key=lambda item: haversine(*current, *item["point"]))
        total_distance += haversine(*current, *stop["point"])
        stops.append(stop)
        current = stop["point"]
        remaining.remove(stop)
    total_distance += haversine(*current, *buyer_point)
    total_quantity = sum(row["quantity"] for row in rows)
    estimated_payout = total_distance * 8 + len(stops) * 150
    for stop in stops:
        stop.pop("point", None)
    return {
        "route_id": route_id,
        "stops": stops,
        "buyer_id": rows[0]["buyer_id"],
        "buyer_name": rows[0]["buyer_name"],
        "buyer_location": rows[0]["buyer_location"],
        "total_distance": round(total_distance, 2),
        "estimated_payout": round(estimated_payout, 2),
        "total_quantity": total_quantity,
        "stop_count": len(stops),
        "capacity_warning": total_quantity > 100,
        "capacity_warning_text": (
            "Route exceeds the common 100-quintal vehicle reference capacity."
            if total_quantity > 100 else None
        ),
        "order_ids": [row["id"] for row in rows],
    }


def _route_rows(where: str = "", args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    query = """SELECT o.id,o.quantity,o.delivery_status,o.buyer_id,o.route_id,
                      l.location AS farmer_location, farmer.name AS farmer_name,
                      farmer.phone AS farmer_phone,
                      buyer.name AS buyer_name, buyer.location AS buyer_location,
                      o.status, o.payment_status, o.transporter_id
               FROM orders o
               JOIN listings l ON l.id=o.listing_id
               JOIN users farmer ON farmer.id=l.farmer_id
               JOIN users buyer ON buyer.id=o.buyer_id"""
    if where:
        query += f" WHERE {where}"
    query += " ORDER BY o.buyer_id,o.id"
    with get_connection() as conn:
        return rows_to_dict(conn.execute(query, args).fetchall())


def _available_route_groups() -> list[dict[str, Any]]:
    rows = _route_rows(
        "o.transporter_id IS NULL AND o.status IN ('pending','countered','accepted')"
    )
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["buyer_id"], []).append(row)
    return [
        _route_from_rows(group, _route_id([row["id"] for row in group]))
        for group in groups.values() if len(group) >= 2
    ]


@app.get("/api/routes/available")
def available_routes() -> list[dict[str, Any]]:
    return _available_route_groups()


@app.post("/api/routes/{route_id}/claim")
def claim_route(route_id: str, payload: RouteClaimRequest) -> dict[str, Any]:
    with get_connection() as conn:
        transporter = conn.execute(
            "SELECT id,role FROM users WHERE id=?", (payload.transporter_id,)
        ).fetchone()
    if not transporter or transporter["role"] != "transporter":
        raise HTTPException(400, "Only a transporter can claim routes")
    matching = [route for route in _available_route_groups() if route["route_id"] == route_id]
    if not matching:
        with get_connection() as conn:
            claimed = conn.execute(
                "SELECT 1 FROM orders WHERE route_id=? LIMIT 1", (route_id,)
            ).fetchone()
        if claimed:
            raise HTTPException(409, "Route has already been claimed")
        raise HTTPException(404, "Route is no longer available")
    order_ids = matching[0]["order_ids"]
    with get_connection() as conn:
        placeholders = ",".join("?" for _ in order_ids)
        current = conn.execute(
            f"SELECT id,transporter_id FROM orders WHERE id IN ({placeholders})",
            order_ids,
        ).fetchall()
        if len(current) != len(order_ids) or any(row["transporter_id"] for row in current):
            raise HTTPException(409, "One or more orders in this route are already claimed")
        conn.execute(
            f"UPDATE orders SET transporter_id=?,route_id=?,updated_at=CURRENT_TIMESTAMP "
            f"WHERE id IN ({placeholders})",
            (payload.transporter_id, route_id, *order_ids),
        )
    return next(route for route in matching if route["route_id"] == route_id)


@app.get("/api/transporter/{transporter_id}/routes")
def transporter_routes(transporter_id: int) -> list[dict[str, Any]]:
    rows = _route_rows("o.transporter_id=? AND o.route_id IS NOT NULL", (transporter_id,))
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["route_id"], []).append(row)
    return [_route_from_rows(group, route_id) for route_id, group in groups.items()]


@app.post("/api/orders/{order_id}/pickup")
def transporter_pickup(order_id: int, payload: TransportPhotoRequest) -> dict[str, Any]:
    order = _order(order_id)
    if order.get("transporter_id") != payload.transporter_id:
        raise HTTPException(403, "Only the assigned transporter can pick up this order")
    if order["payment_status"] != "ESCROW_HELD":
        raise HTTPException(400, "Cannot pick up delivery — payment not yet escrowed")
    if order["order_status"] not in ("CONFIRMED", "PICKUP_SCHEDULED"):
        raise HTTPException(400, f"Cannot pick up — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute(
            """UPDATE orders SET pickup_photo_url=?,actual_pickup_at=CURRENT_TIMESTAMP,
               delivery_status='in_transit',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (payload.photo_url, order_id),
        )
    return _order(order_id)


@app.post("/api/orders/{order_id}/deliver")
def transporter_deliver(order_id: int, payload: TransportPhotoRequest) -> dict[str, Any]:
    order = _order(order_id)
    if order.get("transporter_id") != payload.transporter_id:
        raise HTTPException(403, "Only the assigned transporter can deliver this order")
    if order["order_status"] != "IN_TRANSIT":
        raise HTTPException(400, f"Cannot deliver — order is {order['order_status']}")
    with get_connection() as conn:
        conn.execute(
            """UPDATE orders SET transporter_delivery_photo_url=?,
               delivery_status='delivered',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (payload.photo_url, order_id),
        )
    return _order(order_id)


@app.post("/api/orders/{order_id}/quality")
def quality_order(order_id: int, payload: QualityRequest) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] != "DELIVERED":
        raise HTTPException(400, "Cannot confirm/reject quality — order not yet delivered")
    if order["payment_status"] != "ESCROW_HELD":
        raise HTTPException(400, "No payment in escrow to release or dispute")
    with get_connection() as conn:
        conn.execute("UPDATE orders SET quality_status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (payload.status, order_id))
    return _order(order_id)


@app.post("/api/orders/{order_id}/confirm-quality")
def confirm_quality(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] != "DELIVERED":
        raise HTTPException(400, "Cannot confirm/reject quality — order not yet delivered")
    if order["payment_status"] != "ESCROW_HELD":
        raise HTTPException(400, "No payment in escrow to release or dispute")
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET quality_status='passed',payment_status='released',status='completed',delivery_status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (order_id,),
        )
    _adjust_farmer_rating(order["farmer_id"], 0.05)
    return _order(order_id)


@app.post("/api/orders/{order_id}/reject-quality")
def reject_quality(order_id: int) -> dict[str, Any]:
    order = _order(order_id)
    if order["order_status"] != "DELIVERED":
        raise HTTPException(400, "Cannot confirm/reject quality — order not yet delivered")
    if order["payment_status"] != "ESCROW_HELD":
        raise HTTPException(400, "No payment in escrow to release or dispute")
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET quality_status='failed',payment_status='disputed',status='disputed',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (order_id,),
        )
    _adjust_farmer_rating(order["farmer_id"], -0.3)
    return _order(order_id)


@app.post("/api/advisory")
def advisory(payload: AdvisoryRequest) -> dict[str, Any]:
    answer = get_advice(payload.crop, payload.question)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO advisories (farmer_id,crop,question,answer) VALUES (?,?,?,?)",
            (payload.farmer_id, payload.crop, payload.question, answer),
        )
        return row_to_dict(conn.execute("SELECT * FROM advisories WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.get("/api/advisory")
def advisory_history(farmer_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return rows_to_dict(conn.execute(
            "SELECT * FROM advisories WHERE farmer_id=? ORDER BY created_at DESC", (farmer_id,)
        ).fetchall())


@app.get("/api/mandi-prices")
def mandi_prices(crop: str | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if crop:
            rows = conn.execute("SELECT * FROM mandi_prices WHERE lower(crop)=lower(?) ORDER BY recorded_on DESC", (crop,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM mandi_prices ORDER BY recorded_on DESC").fetchall()
    return rows_to_dict(rows)


@app.get("/api/advisory/{crop}/{region}")
def regional_advisory(crop: str, region: str) -> dict[str, Any]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT price, recorded_on FROM mandi_prices
               WHERE lower(crop)=lower(?) AND lower(market) LIKE lower(?)
               ORDER BY recorded_on DESC LIMIT 10""",
            (crop, f"%{region}%"),
        ).fetchall()
    prices = [float(row["price"]) for row in rows]
    if not prices:
        return {
            "crop": crop,
            "region": region,
            "available": False,
            "advice": "sell_now",
            "change_percent": None,
            "current_average": None,
            "regional_average": None,
            "message": f"No recent mandi prices are available for {crop} in {region}. "
                       "Add regional market data to enable a price comparison.",
        }
    midpoint = max(1, len(prices) // 2)
    recent_average = sum(prices[:midpoint]) / midpoint
    baseline_average = sum(prices[midpoint:]) / max(1, len(prices[midpoint:]))
    change_percent = ((recent_average - baseline_average) / baseline_average * 100) if baseline_average else 0
    advice = "wait" if change_percent > 5 else "sell_now"
    narrative = generate_market_narrative(
        crop, region, round(recent_average, 2), round(baseline_average, 2),
        round(change_percent, 2), True,
    )
    return {
        "crop": crop, "region": region, "available": True,
        "current_average": round(recent_average, 2),
        "regional_average": round(baseline_average, 2), "change_percent": round(change_percent, 2),
        "advice": advice,
        "message": narrative or (
            f"Current average ₹{recent_average:.0f}/quintal is {abs(change_percent):.1f}% "
            f"{'higher' if change_percent >= 0 else 'lower'} than the 10-day regional average "
            f"of ₹{baseline_average:.0f}."
        ),
    }


@app.get("/api/logistics/optimize-routes")
def optimize_routes(buyer_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT o.id,o.quantity,o.agreed_price,o.status,l.location AS farmer_location,
                      farmer.name AS farmer_name, buyer.location AS buyer_location
               FROM orders o JOIN listings l ON l.id=o.listing_id
               JOIN users farmer ON farmer.id=l.farmer_id
               JOIN users buyer ON buyer.id=o.buyer_id
               WHERE o.buyer_id=? AND o.status IN ('pending','countered','accepted')""",
            (buyer_id,),
        ).fetchall()
    if len(rows) < 2:
        return {"message": "No route consolidation opportunities right now"}
    buyer_point = location_point(rows[0]["buyer_location"])
    grouped = {}
    for row in rows:
        key = row["farmer_location"].strip().lower()
        stop = grouped.setdefault(key, {
            "name": row["farmer_name"], "location": row["farmer_location"],
            "point": location_point(row["farmer_location"]), "quantity": 0, "order_count": 0,
        })
        stop["quantity"] += row["quantity"]
        stop["order_count"] += 1
    stops = list(grouped.values())
    separate_distance = 2 * sum(
        haversine(*location_point(row["farmer_location"]), *buyer_point) for row in rows
    )
    remaining = stops.copy()
    current = buyer_point
    route = []
    combined_distance = 0
    while remaining:
        next_stop = min(remaining, key=lambda stop: haversine(*current, *stop["point"]))
        combined_distance += haversine(*current, *next_stop["point"])
        route.append(next_stop)
        current = next_stop["point"]
        remaining.remove(next_stop)
    combined_distance += haversine(*current, *buyer_point)
    per_stop_fee = 150
    separate_cost = separate_distance * 8 + len(rows) * per_stop_fee
    combined_cost = combined_distance * 8 + len(stops) * per_stop_fee
    return {
        "separate_trip_cost": round(separate_cost, 2),
        "combined_trip_cost": round(combined_cost, 2),
        "savings": round(max(0, separate_cost - combined_cost), 2),
        "route_order": [f"{stop['name']} ({stop['location']})" for stop in route],
    }
