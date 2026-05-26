import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.poller import run_poller

    task = asyncio.create_task(run_poller())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Mock trans.eu API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RESPONSES_FILE = DATA_DIR / "responses.jsonl"
MESSAGES_FILE = DATA_DIR / "messages.jsonl"
NOTES_DIR = ROOT_DIR / "notes"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(NOTES_DIR, exist_ok=True)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# Load persisted messages on startup so they survive server restarts.
MESSAGES: list[dict] = read_jsonl(MESSAGES_FILE)
AGENT_ENABLED = True

# In-memory stores (for mock/testing only)
# Field names match the real Trans.eu REST API v1 structure.
FREIGHTS: list[dict] = [
    {
        "id": "fr1",
        "load_date": "2026-05-28",
        "unload_date": "2026-05-29",
        "loading_place": {
            "address": {"country": "PL", "postal_code": "00-001", "locality": "Warszawa"}
        },
        "unloading_place": {
            "address": {"country": "DE", "postal_code": "10115", "locality": "Berlin"}
        },
        "load_weight": {"value": 24000, "unit_code": "KGM"},
        "price": {"value": 1500, "currency": "EUR"},
        "vehicle_type": ["tent"],
        "status": "published",
    }
]

ORDERS: list[dict] = [
    {
        "id": "ord1",
        "freight_id": "fr1",
        "status": "in_realization",
        "loading_place": {
            "address": {"country": "PL", "postal_code": "00-001", "locality": "Warszawa"}
        },
        "unloading_place": {
            "address": {"country": "DE", "postal_code": "10115", "locality": "Berlin"}
        },
        "carrier": {"trans_id": "12-1234", "name": "Jan Kowalski Transport"},
        "price": {"value": 1500, "currency": "EUR"},
    }
]

AGENT_ENABLED = True

# Kept for backward compatibility with existing frontend calls.
OFFERS = [
    {
        "id": o["id"],
        "pickup": o["loading_place"]["address"]["locality"],
        "delivery": o["unloading_place"]["address"]["locality"],
        "date": o["load_date"],
        "weight": o["load_weight"]["value"],
    }
    for o in FREIGHTS
]
SHIPMENTS = {
    o["id"]: {"id": o["id"], "status": o["status"], "details": f"Zlecenie {o['id']}"}
    for o in ORDERS
}


def normalize_message(payload: dict) -> dict:
    msg = {
        "id": str(uuid4()),
        "sender": payload.get("sender") or payload.get("from") or "unknown",
        "recipient": payload.get("recipient") or payload.get("to"),
        "text": payload.get("text") or payload.get("message") or "",
        "shipment_id": payload.get("shipment_id"),
        "datetime": payload.get("datetime"),
        "source": payload.get("source"),
        "event_type": payload.get("event_type"),
    }
    append_jsonl(MESSAGES_FILE, msg)
    return msg


def process_message(msg: dict, background_tasks: BackgroundTasks | None = None):
    global AGENT_ENABLED
    if not AGENT_ENABLED:
        return {"status": "skipped", "reason": "agent_disabled"}
    try:
        from backend.agents.generator import handle_message
        from backend.agents.notes import extract_and_append

        response = handle_message(msg)
        if background_tasks is not None:
            background_tasks.add_task(extract_and_append, msg)
        else:
            extract_and_append(msg)
        return response
    except Exception as exc:
        # fallback: record incoming message but continue
        if background_tasks is not None:
            background_tasks.add_task(lambda _: None, msg)
        return {"error": "agent_unavailable", "detail": str(exc)}


@app.get("/agent/status")
def agent_status():
    return {"agent_enabled": AGENT_ENABLED}


@app.post("/agent/enable")
def enable_agent():
    global AGENT_ENABLED
    AGENT_ENABLED = True
    return {"agent_enabled": AGENT_ENABLED}


@app.post("/agent/disable")
def disable_agent():
    global AGENT_ENABLED
    AGENT_ENABLED = False
    return {"agent_enabled": AGENT_ENABLED}


class MessageIn(BaseModel):
    sender: str | None = None
    recipient: str | None = None
    from_: str | None = None
    text: str
    shipment_id: str | None = None
    datetime: str | None = None

    class Config:
        allow_population_by_field_name = True
        fields = {
            "from_": "from",
            "recipient": "to",
        }


# --- Trans.eu API v1 — mock endpoints (field names match real API) ---


@app.get("/freights")
def list_freights():
    return {"data": FREIGHTS, "total": len(FREIGHTS)}


@app.get("/freights/{freight_id}")
def get_freight(freight_id: str):
    for f in FREIGHTS:
        if f["id"] == freight_id:
            return f
    raise HTTPException(status_code=404, detail="Freight not found")


@app.post("/freights")
def create_freight(payload: dict):
    freight = {"id": str(uuid4()), **payload, "status": "draft"}
    FREIGHTS.append(freight)
    return freight


@app.get("/freight-orders")
def list_orders():
    return {"data": ORDERS, "total": len(ORDERS)}


@app.get("/freight-orders/received")
def list_received_orders():
    received = [o for o in ORDERS if o.get("status") in ("received", "in_realization")]
    return {"data": received, "total": len(received)}


@app.get("/freight-orders/{order_id}")
def get_order(order_id: str):
    for o in ORDERS:
        if o["id"] == order_id:
            return o
    raise HTTPException(status_code=404, detail="Order not found")


@app.get("/vehicles")
def list_vehicles():
    return {"data": [], "total": 0}


@app.get("/contractors")
def list_contractors():
    return {"data": [], "total": 0}


# --- Backward-compat aliases ---


@app.get("/offers")
def list_offers():
    return {"offers": OFFERS}


@app.get("/messages")
def list_messages():
    return {"messages": MESSAGES}


@app.get("/messages/latest")
def get_latest_message():
    if not MESSAGES:
        raise HTTPException(status_code=404, detail="No messages found")
    return MESSAGES[-1]


@app.get("/messages/latest-with-response")
def get_latest_message_with_response():
    if not MESSAGES:
        raise HTTPException(status_code=404, detail="No messages found")
    latest = MESSAGES[-1]
    response = None
    for item in read_jsonl(RESPONSES_FILE):
        if item.get("message_id") == latest.get("id"):
            response = item
            break
    return {"message": latest, "response": response}


@app.get("/messages/{message_id}")
def get_message(message_id: str):
    for msg in MESSAGES:
        if msg.get("id") == message_id:
            return msg
    raise HTTPException(status_code=404, detail="Message not found")


@app.post("/messages")
def create_message(msg: MessageIn, background_tasks: BackgroundTasks):
    payload = {k: v for k, v in msg.dict().items() if v is not None}
    message = normalize_message(payload)
    MESSAGES.append(message)
    response = process_message(message, background_tasks)
    return {
        "status": "created",
        "message": message,
        "response": response,
    }


@app.post("/webhook")
def webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Accepts both plain message payloads and Trans.eu callback events.
    Trans.eu event types: freights.freight.offer_received,
    freight_orders.order.created, freight_orders.order.delivery_was_confirmed, etc.
    """
    event_type = payload.get("event_type") or payload.get("type")
    if event_type:
        # Trans.eu callback event — extract text for the agent
        data = payload.get("data", {})
        text = _event_to_text(event_type, data)
        inner = {**data, "text": text, "event_type": event_type}
        message = normalize_message(inner)
    else:
        message = normalize_message(payload)

    MESSAGES.append(message)
    response = process_message(message, background_tasks)
    return {"status": "received", "message_id": message["id"], "response": response}


def _event_to_text(event_type: str, data: dict) -> str:
    """Converts a Trans.eu webhook event into a human-readable text for the LLM agent."""
    freight_id = data.get("freight_id") or data.get("id", "")
    order_id = data.get("order_id") or data.get("id", "")
    carrier = (data.get("carrier") or {}).get("name", "")
    price = data.get("price") or {}
    price_str = f"{price.get('value', '')} {price.get('currency', '')}".strip()

    descriptions = {
        "freights.freight.published": f"Ładunek {freight_id} został opublikowany na giełdzie.",
        "freights.freight.offer_received": (
            f"Otrzymano ofertę do ładunku {freight_id}. Przewoźnik: {carrier}. Cena: {price_str}."
        ),
        "freights.freight.offer_accepted": (
            f"Oferta do ładunku {freight_id} została zaakceptowana."
        ),
        "freight_orders.order.created": (
            f"Utworzono zlecenie {order_id}. Przewoźnik: {carrier}. Kwota: {price_str}."
        ),
        "freight_orders.order.delivery_was_confirmed": (
            f"Dostawa zlecenia {order_id} potwierdzona."
        ),
        "freight_orders.order.transports_was_finished": (
            f"Transport zlecenia {order_id} zakończony."
        ),
        "transports.transport.devices_set_changed": (
            f"Zmiana urządzeń monitoringu dla transportu {data.get('transport_id', '')}."
        ),
    }
    return descriptions.get(event_type, f"Zdarzenie Trans.eu: {event_type}")


@app.post("/webhook/process")
def webhook_process(payload: dict, background_tasks: BackgroundTasks):
    message = normalize_message(payload)
    MESSAGES.append(message)
    response = process_message(message, background_tasks)
    return {"status": "processed", "message_id": message["id"], "response": response}


@app.get("/responses")
def list_responses():
    return {"responses": read_jsonl(RESPONSES_FILE)}


@app.get("/responses/latest")
def get_latest_response():
    responses = read_jsonl(RESPONSES_FILE)
    if not responses:
        raise HTTPException(status_code=404, detail="No responses found")
    return responses[-1]


@app.get("/responses/{message_id}")
def get_response(message_id: str):
    for item in read_jsonl(RESPONSES_FILE):
        if item.get("message_id") == message_id:
            return item
    raise HTTPException(status_code=404, detail="Response not found")


@app.get("/notes")
def list_notes():
    notes = []
    if NOTES_DIR.exists():
        for path in sorted(NOTES_DIR.glob("*.md")):
            notes.append({"file": path.name, "path": str(path.relative_to(ROOT_DIR))})
    return {"notes": notes, "jsonl": read_jsonl(NOTES_DIR / "notes.jsonl")}


@app.get("/notes/latest")
def get_latest_note():
    md_files = sorted(NOTES_DIR.glob("*.md"))
    if not md_files:
        raise HTTPException(status_code=404, detail="No notes found")
    path = md_files[-1]
    return {"date": path.stem, "content": path.read_text(encoding="utf-8")}


@app.get("/notes/{note_date}")
def get_note_by_date(note_date: str):
    md_path = NOTES_DIR / f"{note_date}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")
    return {"date": note_date, "content": md_path.read_text(encoding="utf-8")}


@app.get("/shipments")
def list_shipments():
    return {"shipments": list(SHIPMENTS.values())}


@app.get("/poll")
def poll_status():
    """Lightweight canary endpoint — returns message/response counts and timestamp.
    Frontend polls this every 30s; if messages_total grows, it fetches new data.
    """
    from datetime import datetime, timezone

    responses = read_jsonl(RESPONSES_FILE)
    last_msg = MESSAGES[-1] if MESSAGES else None
    return {
        "ok": True,
        "agent_enabled": AGENT_ENABLED,
        "messages_total": len(MESSAGES),
        "responses_total": len(responses),
        "last_message_at": last_msg.get("datetime") if last_msg else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "freights": len(FREIGHTS),
        "orders": len(ORDERS),
        "messages": len(MESSAGES),
        "responses_file_exists": RESPONSES_FILE.exists(),
        "notes_dir_exists": NOTES_DIR.exists(),
    }


@app.get("/", response_class=HTMLResponse)
def root_ui():
    return """
    <!DOCTYPE html>
    <html lang='pl'>
    <head>
      <meta charset='UTF-8'>
      <title>Transport Assistant API Tester</title>
      <style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;}button{margin:6px 0;padding:10px 14px;}textarea{width:100%;height:220px;margin-top:8px;}</style>
    </head>
    <body>
      <h1>Transport Assistant — Tester</h1>
      <p>Szybki podgląd i generowanie zdarzeń testowych Trans.eu.</p>

      <h3>Status &amp; dane</h3>
      <button onclick='call("/health","GET")'>Health</button>
      <button onclick='call("/messages","GET")'>GET /messages</button>
      <button onclick='call("/responses","GET")'>GET /responses</button>
      <button onclick='call("/freights","GET")'>GET /freights</button>
      <button onclick='call("/freight-orders","GET")'>GET /freight-orders</button>
      <button onclick='call("/agent/status","GET")'>Status agenta</button>
      <button onclick='call("/agent/enable","POST")'>Włącz agenta</button>
      <button onclick='call("/agent/disable","POST")'>Wyłącz agenta</button>

      <h3>Generowanie zdarzeń testowych (mock Trans.eu)</h3>
      <button onclick='call("/mock/generate","POST")'>Losowe zdarzenie</button>
      <button onclick='call("/mock/generate/offer_received","POST")'>Oferta do ładunku</button>
      <button onclick='call("/mock/generate/order_created","POST")'>Nowe zlecenie</button>
      <button onclick='call("/mock/generate/loading_confirmed","POST")'>Załadunek potwierdzony</button>
      <button onclick='call("/mock/generate/delivery_confirmed","POST")'>Dostawa potwierdzona</button>
      <button onclick='call("/mock/generate/new_freight","POST")'>Nowy ładunek na giełdzie</button>

      <h2>Odpowiedź</h2>
      <textarea id='output' readonly></textarea>
      <script>
        async function call(path, method='GET', body=null){
          const opts={method,headers:{'Content-Type':'application/json'}};
          if(body) opts.body=JSON.stringify(body);
          const res=await fetch(path,opts);
          const text=await res.text();
          try {
            const pretty=JSON.stringify(JSON.parse(text),null,2);
            document.getElementById('output').value=`${method} ${path}  →  ${res.status}\n\n${pretty}`;
          } catch {
            document.getElementById('output').value=`${method} ${path}  →  ${res.status}\n\n${text}`;
          }
        }
      </script>
    </body>
    </html>
    """


@app.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: str):
    data = SHIPMENTS.get(shipment_id)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return data


@app.post("/simulate/message")
def simulate_message(background_tasks: BackgroundTasks):
    sample = {
        "sender": "kontrahent@spedycja.pl",
        "recipient": "firma@transport.pl",
        "text": "Czy macie wolny pojazd na trasę Warszawa–Berlin 28.05, ładunek 24t plandeka?",
        "shipment_id": "fr1",
        "datetime": "2026-05-24T10:00:00",
    }
    message = normalize_message(sample)
    MESSAGES.append(message)
    response = process_message(message, background_tasks)
    return {"status": "simulated", "message": message, "response": response}


@app.post("/mock/generate")
def mock_generate(background_tasks: BackgroundTasks):
    """Generuje losowe zdarzenie Trans.eu i przekazuje je do agenta."""
    from backend.mock_generator import generate_event

    event = generate_event()
    return webhook(event, background_tasks)


@app.post("/mock/generate/{event_type}")
def mock_generate_typed(event_type: str, background_tasks: BackgroundTasks):
    """
    Generuje zdarzenie konkretnego typu i przekazuje je do agenta.

    Dostępne typy:
      offer_received, order_created, loading_confirmed,
      delivery_confirmed, new_freight
    """
    from backend.mock_generator import EVENT_TYPES, generate_event

    if event_type not in EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznany typ zdarzenia. Dostępne: {EVENT_TYPES}",
        )
    event = generate_event(event_type)
    result = webhook(event, background_tasks)
    return {**result, "generated_event": event}


@app.get("/mock/event-types")
def mock_event_types():
    """Zwraca listę dostępnych typów zdarzeń testowych."""
    from backend.mock_generator import EVENT_TYPES

    return {"event_types": EVENT_TYPES}
