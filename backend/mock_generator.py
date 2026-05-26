"""
Generates realistic fake Trans.eu events for testing without API access.

────────────────────────────────────────────────────────────────
 Alias             Trans.eu event_type                          Opis
────────────────────────────────────────────────────────────────
 offer_received    freights.freight.offer_received              Oferta cenowa do ładunku
 order_created     freight_orders.order.created                 Nowe zlecenie transportowe
 loading_confirmed freight_orders.order.loading_confirmed       Załadunek potwierdzony
 delivery_confirmed freight_orders.order.delivery_was_confirmed Dostawa potwierdzona
 new_freight       freights.freight.published                   Nowy ładunek na giełdzie
────────────────────────────────────────────────────────────────

Usage:
    from backend.mock_generator import generate_event, EVENT_TYPES

    event = generate_event()                    # losowy typ
    event = generate_event("offer_received")    # konkretny typ
    event = generate_event("new_freight")       # nowy ładunek na giełdzie
"""

import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

EVENT_TYPES = [
    "offer_received",
    "order_created",
    "loading_confirmed",
    "delivery_confirmed",
    "new_freight",
]

# ── realistic data pools ─────────────────────────────────────────────────────

_CITIES_PL = [
    "Warszawa",
    "Wrocław",
    "Kraków",
    "Gdańsk",
    "Poznań",
    "Łódź",
    "Katowice",
    "Szczecin",
    "Rzeszów",
    "Lublin",
]
_CITIES_DE = [
    "Berlin",
    "Hamburg",
    "Monachium",
    "Frankfurt",
    "Kolonia",
    "Stuttgart",
    "Lipsk",
    "Drezno",
]
_CITIES_OTHER = [
    "Praga",
    "Bratysława",
    "Wiedeń",
    "Amsterdam",
    "Paryż",
    "Bruksela",
    "Lyon",
    "Rotterdam",
]

_ROUTES = [
    ("PL", "Warszawa", "DE", "Berlin"),
    ("PL", "Wrocław", "DE", "Frankfurt"),
    ("PL", "Gdańsk", "DE", "Hamburg"),
    ("PL", "Kraków", "DE", "Monachium"),
    ("PL", "Warszawa", "NL", "Amsterdam"),
    ("PL", "Poznań", "DE", "Berlin"),
    ("PL", "Katowice", "AT", "Wiedeń"),
    ("PL", "Wrocław", "CZ", "Praga"),
    ("DE", "Berlin", "PL", "Warszawa"),
    ("DE", "Frankfurt", "PL", "Kraków"),
    ("CZ", "Praga", "PL", "Wrocław"),
    ("PL", "Szczecin", "BE", "Bruksela"),
]

_CARRIERS = [
    {"trans_id": "12-1234", "name": "Fast Logistics Sp. z o.o."},
    {"trans_id": "45-5678", "name": "EuroTrans GmbH"},
    {"trans_id": "78-9012", "name": "Kowalski Transport"},
    {"trans_id": "33-4455", "name": "Trans-Pol Spedycja"},
    {"trans_id": "21-3344", "name": "Schnell Spedition GmbH"},
    {"trans_id": "67-7788", "name": "Nowak Logistyka"},
    {"trans_id": "55-1122", "name": "Baltic Cargo Sp. z o.o."},
]

_VEHICLE_TYPES = ["tent", "mega", "ref", "box", "jumbo", "curtain_sider"]

_CURRENCIES = ["EUR", "PLN"]
_WEIGHTS_KG = [1000, 2500, 5000, 10000, 15000, 20000, 24000]


# ── helpers ──────────────────────────────────────────────────────────────────


def _route():
    return random.choice(_ROUTES)


def _future_date(days_min=1, days_max=14) -> str:
    d = datetime.now(timezone.utc) + timedelta(days=random.randint(days_min, days_max))
    return d.strftime("%Y-%m-%d")


def _price(base_min=800, base_max=3000) -> dict:
    currency = random.choice(_CURRENCIES)
    value = random.randint(base_min, base_max)
    if currency == "PLN":
        value = int(value * 4.2)
    return {"value": value, "currency": currency}


def _address(country: str, city: str, postal_code: str = None) -> dict:
    if postal_code is None:
        postal_code = f"{random.randint(10, 99)}-{random.randint(100, 999)}"
    return {"address": {"country": country, "postal_code": postal_code, "locality": city}}


def _weight() -> dict:
    return {"value": random.choice(_WEIGHTS_KG), "unit_code": "KGM"}


def _carrier() -> dict:
    return random.choice(_CARRIERS)


def _freight_id() -> str:
    return f"fr-{uuid4().hex[:8]}"


def _order_id() -> str:
    return f"ord-{uuid4().hex[:8]}"


# ── event builders ───────────────────────────────────────────────────────────


def _build_offer_received() -> dict:
    from_country, from_city, to_country, to_city = _route()
    carrier = _carrier()
    fid = _freight_id()
    return {
        "event_type": "freights.freight.offer_received",
        "data": {
            "freight_id": fid,
            "offer_id": f"off-{uuid4().hex[:8]}",
            "carrier": carrier,
            "price": _price(800, 2500),
            "loading_place": _address(from_country, from_city),
            "unloading_place": _address(to_country, to_city),
            "load_date": _future_date(1, 7),
        },
    }


def _build_order_created() -> dict:
    from_country, from_city, to_country, to_city = _route()
    carrier = _carrier()
    oid = _order_id()
    fid = _freight_id()
    load_date = _future_date(1, 10)
    return {
        "event_type": "freight_orders.order.created",
        "data": {
            "order_id": oid,
            "freight_id": fid,
            "carrier": carrier,
            "loading_place": _address(from_country, from_city),
            "unloading_place": _address(to_country, to_city),
            "load_date": load_date,
            "unload_date": _future_date(3, 14),
            "load_weight": _weight(),
            "price": _price(900, 3000),
            "vehicle_type": [random.choice(_VEHICLE_TYPES)],
        },
    }


def _build_loading_confirmed() -> dict:
    carrier = _carrier()
    oid = _order_id()
    from_country, from_city, to_country, to_city = _route()
    return {
        "event_type": "freight_orders.order.loading_confirmed",
        "data": {
            "order_id": oid,
            "carrier": carrier,
            "loading_place": _address(from_country, from_city),
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _build_delivery_confirmed() -> dict:
    carrier = _carrier()
    oid = _order_id()
    from_country, from_city, to_country, to_city = _route()
    return {
        "event_type": "freight_orders.order.delivery_was_confirmed",
        "data": {
            "order_id": oid,
            "carrier": carrier,
            "unloading_place": _address(to_country, to_city),
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _build_new_freight() -> dict:
    from_country, from_city, to_country, to_city = _route()
    fid = _freight_id()
    load_date = _future_date(1, 10)
    return {
        "event_type": "freights.freight.published",
        "data": {
            "freight_id": fid,
            "loading_place": _address(from_country, from_city),
            "unloading_place": _address(to_country, to_city),
            "load_date": load_date,
            "unload_date": _future_date(3, 14),
            "load_weight": _weight(),
            "price": _price(700, 2800),
            "vehicle_type": [random.choice(_VEHICLE_TYPES)],
        },
    }


_BUILDERS = {
    "offer_received": _build_offer_received,
    "order_created": _build_order_created,
    "loading_confirmed": _build_loading_confirmed,
    "delivery_confirmed": _build_delivery_confirmed,
    "new_freight": _build_new_freight,
}


# ── public API ───────────────────────────────────────────────────────────────


def generate_event(event_type: str = None) -> dict:
    """
    Returns a realistic fake Trans.eu event dict.
    Pass event_type to get a specific kind, or None for a random one.
    """
    if event_type is None:
        event_type = random.choice(EVENT_TYPES)
    builder = _BUILDERS.get(event_type)
    if builder is None:
        raise ValueError(f"Unknown event_type: {event_type!r}. Choose from: {EVENT_TYPES}")
    return builder()
