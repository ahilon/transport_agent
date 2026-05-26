import json
import os

from backend.llm.adapter import build_claude_prompt, generate_response

RESPONSES_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(RESPONSES_DIR, exist_ok=True)
RESPONSES_FILE = os.path.join(RESPONSES_DIR, "responses.jsonl")


def handle_message(msg: dict):
    """Process incoming message and generate an automated response."""
    prompt = build_claude_prompt(
        message_text=msg.get("text", ""),
        sender=msg.get("sender"),
        shipment_id=msg.get("shipment_id"),
    )
    resp_text = generate_response(prompt)
    resp_obj = {
        "message_id": msg.get("id"),
        "response": resp_text,
        "to": msg.get("sender"),
    }
    # append to file
    with open(RESPONSES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(resp_obj, ensure_ascii=False) + "\n")
    return resp_obj
