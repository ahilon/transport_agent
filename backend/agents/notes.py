import json
import os
import re
from datetime import date

NOTES_DIR = os.path.join(os.path.dirname(__file__), "..", "notes")
os.makedirs(NOTES_DIR, exist_ok=True)
NOTES_JSONL = os.path.join(NOTES_DIR, "notes.jsonl")


def guess_route(text: str) -> dict[str, str]:
    route = {"pickup": None, "delivery": None}
    lowered = text.lower()
    _RE_ROUTE = (
        r"(?:z|from)\s+([A-Za-ząćęłńóśżźĄĆĘŁŃÓŚŻŹ]+)\s+(?:do|to)\s+([A-Za-ząćęłńóśżźĄĆĘŁŃÓŚŻŹ]+)"
    )
    match = re.search(_RE_ROUTE, lowered)
    if match:
        route["pickup"] = match.group(1).capitalize()
        route["delivery"] = match.group(2).capitalize()
    return route


def guess_date(text: str) -> str | None:
    match = re.search(r"(\d{2}[\.\-/]\d{2}(?:[\.\-/]\d{2,4})?)", text)
    if match:
        return match.group(1)
    return None


def extract_fields(msg: dict) -> dict:
    text = (msg.get("text") or "").strip()
    route = guess_route(text)
    return {
        "id": msg.get("id"),
        "sender": msg.get("sender"),
        "text": text,
        "shipment_id": msg.get("shipment_id"),
        "pickup": route.get("pickup"),
        "delivery": route.get("delivery"),
        "datetime": msg.get("datetime") or guess_date(text),
    }


def extract_and_append(msg: dict):
    """Extract important fields from message and append to notes files.

    Writes both a machine-friendly `notes.jsonl` and a human-readable daily markdown.
    """
    entry = extract_fields(msg)
    # append to jsonl
    with open(NOTES_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # append to daily markdown
    today = date.today().isoformat()
    md_path = os.path.join(NOTES_DIR, f"{today}.md")
    md_line = f"- [{entry.get('id')}] From {entry.get('sender')}: {entry.get('text')}\n"
    with open(md_path, "a", encoding="utf-8") as f:
        f.write(md_line)

    return entry
