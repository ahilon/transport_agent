"""
Background Trans.eu poller — runs as an asyncio task inside FastAPI lifespan.

When TRANS_CLIENT_ID is set in the environment, polls the real Trans.eu API.
Otherwise logs a warning and does nothing (safe to run without credentials).

Interval: POLL_INTERVAL_SECONDS env var (default: 60s).

────────────────────────────────────────────────────────────────
 #  Co sprawdzamy            API endpoint                 Event type
────────────────────────────────────────────────────────────────
 1  Oferty do ładunków       GET /freights/{id}/offers    freights.freight.offer_received
    Ktoś złożył ofertę cenową na nasz opublikowany ładunek.

 2  Nowe zlecenia            GET /freight-orders/received freight_orders.order.created
    Zlecenie transportowe przypisane do firmy (jako przewoźnik).

 3  Statusy transportów   GET /transports         freight_orders.order.loading_confirmed
    Zmiany stanu: załadunek, rozładunek.         freight_orders.order.delivery_was_confirmed
                                                 freight_orders.order.transports_was_finished

 4  Nowe ładunki na giełdzie GET /freights?status=published freights.freight.published
    Ładunki innych firm — potencjalnie pasujące do naszych tras.
────────────────────────────────────────────────────────────────

Deduplication: seen IDs are tracked in memory for the lifetime of the process.
Normalised events are forwarded to POST /webhook so the agent pipeline handles them.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger("poller")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
WEBHOOK_URL = "http://127.0.0.1:8000/webhook"

_STATE_FILE = Path(__file__).parent / "data" / "poller_state.json"

_seen_offer_ids: set[str] = set()
_seen_order_ids: set[str] = set()
_seen_transport_statuses: dict[str, str] = {}
_seen_freight_ids: set[str] = set()


def _load_state() -> None:
    """Load deduplication state from disk so restarts don't reprocess old events."""
    if not _STATE_FILE.exists():
        return
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        _seen_offer_ids.update(data.get("offer_ids", []))
        _seen_order_ids.update(data.get("order_ids", []))
        _seen_transport_statuses.update(data.get("transport_statuses", {}))
        _seen_freight_ids.update(data.get("freight_ids", []))
        logger.info(
            "Poller state loaded (%d offers, %d orders, %d freights)",
            len(_seen_offer_ids),
            len(_seen_order_ids),
            len(_seen_freight_ids),
        )
    except Exception as exc:
        logger.warning("Could not load poller state: %s", exc)


def _save_state() -> None:
    """Persist deduplication state to disk."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(
                {
                    "offer_ids": list(_seen_offer_ids),
                    "order_ids": list(_seen_order_ids),
                    "transport_statuses": _seen_transport_statuses,
                    "freight_ids": list(_seen_freight_ids),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not save poller state: %s", exc)


# ── polling functions (sync, run in threadpool) ───────────────────────────────


def _poll_freight_offers(client) -> list[dict]:
    """Check each published freight for new offers."""
    events = []
    try:
        freights = client.get_freights(params={"page": 1, "per_page": 20})
    except Exception as exc:
        logger.warning("get_freights failed: %s", exc)
        return events

    for freight in freights.get("data", []):
        fid = freight.get("id", "")
        if not fid:
            continue
        try:
            offers_resp = client.get_freight_offers(fid)
        except Exception as exc:
            logger.debug("get_freight_offers(%s) failed: %s", fid, exc)
            continue
        for offer in offers_resp.get("data", []):
            oid = offer.get("id", "")
            if not oid or oid in _seen_offer_ids:
                continue
            _seen_offer_ids.add(oid)
            events.append(
                {
                    "event_type": "freights.freight.offer_received",
                    "data": {
                        "freight_id": fid,
                        "offer_id": oid,
                        "carrier": offer.get("carrier", {}),
                        "price": offer.get("price", {}),
                    },
                }
            )
    return events


def _poll_received_orders(client) -> list[dict]:
    """Check for new incoming orders."""
    events = []
    try:
        resp = client.get_received_orders(params={"page": 1, "per_page": 20})
    except Exception as exc:
        logger.warning("get_received_orders failed: %s", exc)
        return events

    for order in resp.get("data", []):
        oid = order.get("id", "")
        if not oid or oid in _seen_order_ids:
            continue
        _seen_order_ids.add(oid)
        events.append(
            {
                "event_type": "freight_orders.order.created",
                "data": {
                    "order_id": oid,
                    "freight_id": order.get("freight_id", ""),
                    "carrier": order.get("carrier", {}),
                    "loading_place": order.get("loading_place", {}),
                    "unloading_place": order.get("unloading_place", {}),
                    "price": order.get("price", {}),
                },
            }
        )
    return events


def _poll_transport_statuses(client) -> list[dict]:
    """Detect status changes in transports in realization."""
    events = []
    try:
        resp = client.get_transports(params={"page": 1, "per_page": 20})
    except Exception as exc:
        logger.warning("get_transports failed: %s", exc)
        return events

    for transport in resp.get("data", []):
        tid = transport.get("id", "")
        status = transport.get("status", "")
        if not tid or not status:
            continue
        if _seen_transport_statuses.get(tid) == status:
            continue
        _seen_transport_statuses[tid] = status

        # map Trans.eu status → event_type
        event_map = {
            "loading_confirmed": "freight_orders.order.loading_confirmed",
            "unloading_confirmed": "freight_orders.order.unloading_confirmed",
            "delivery_confirmed": "freight_orders.order.delivery_was_confirmed",
            "finished": "freight_orders.order.transports_was_finished",
        }
        event_type = event_map.get(status, "transports.transport.status_changed")
        events.append(
            {
                "event_type": event_type,
                "data": {
                    "transport_id": tid,
                    "order_id": transport.get("order_id", ""),
                    "status": status,
                },
            }
        )
    return events


def _poll_exchange_freights(client) -> list[dict]:
    """Check for new freights published on the exchange."""
    events = []
    try:
        # status=published returns freights available on the exchange
        resp = client.get_freights(params={"page": 1, "per_page": 20, "status": "published"})
    except Exception as exc:
        logger.warning("get_exchange_freights failed: %s", exc)
        return events

    for freight in resp.get("data", []):
        fid = freight.get("id", "")
        if not fid or fid in _seen_freight_ids:
            continue
        _seen_freight_ids.add(fid)
        events.append(
            {
                "event_type": "freights.freight.published",
                "data": {
                    "freight_id": fid,
                    "loading_place": freight.get("loading_place", {}),
                    "unloading_place": freight.get("unloading_place", {}),
                    "load_date": freight.get("load_date", ""),
                    "load_weight": freight.get("load_weight", {}),
                    "price": freight.get("price", {}),
                    "vehicle_type": freight.get("vehicle_type", []),
                },
            }
        )
    return events


def _fetch_all_events() -> list[dict]:
    """Runs all four polls synchronously. Called via asyncio.to_thread."""
    from backend.transeu_client import TransEuClient

    client = TransEuClient()
    events: list[dict] = []
    events.extend(_poll_freight_offers(client))
    events.extend(_poll_received_orders(client))
    events.extend(_poll_transport_statuses(client))
    events.extend(_poll_exchange_freights(client))
    return events


# ── async helpers ─────────────────────────────────────────────────────────────


async def _post_webhook(payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(WEBHOOK_URL, json=payload)
            if resp.status_code >= 400:
                logger.warning("Webhook %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Webhook post failed: %s", exc)


# ── main loop ─────────────────────────────────────────────────────────────────


async def run_poller() -> None:
    if not os.getenv("TRANS_CLIENT_ID"):
        logger.warning(
            "TRANS_CLIENT_ID not set — Trans.eu poller inactive. "
            "Use POST /mock/generate to inject test events."
        )
        return

    _load_state()
    logger.info("Trans.eu poller started (interval=%ds)", POLL_INTERVAL)

    while True:
        try:
            events = await asyncio.to_thread(_fetch_all_events)
            for event in events:
                await _post_webhook(event)
                logger.info("Forwarded: %s", event.get("event_type"))
            if events:
                _save_state()
        except Exception as exc:
            logger.error("Poller cycle error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)
