"""
LLM adapter for the transport assistant.

Modes (set via LLM_MODE env var):
  stub    — canned replies for local testing, no API key needed (default)
  remote  — calls Anthropic Messages API (claude-sonnet-4-6 by default)
  local   — placeholder for a future local model
"""

import os

import httpx

MESSAGES_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = (
    "Jesteś asystentem biura transportowego. Odpowiadasz w języku polskim, "
    "krótko i konkretnie.\n\n"
    "Wiadomości mogą być dwojakiego rodzaju:\n"
    "1) Nowe zapytanie o transport — klient pyta o dostępność, trasę lub cenę. "
    "Jeśli brakuje miejsca załadunku, miejsca docelowego lub daty — dopytaj o nie.\n"
    "2) Aktualizacja istniejącego zlecenia — jeśli nie ma numeru zlecenia, poproś o nie.\n\n"
    "Zdarzenia z platformy Trans.eu (offer_received, order.created itp.) potraktuj "
    "jako powiadomienie wewnętrzne — krótko potwierdź odbiór i opisz co się stało.\n\n"
    "Nie wymyślaj cen ani terminów, których nie znasz. "
    "Odpowiadaj jako pracownik biura, nie jako robot."
)


def build_claude_prompt(message_text: str, sender: str = None, shipment_id: str = None) -> str:
    """Returns the user-turn text. System prompt is passed separately to the API."""
    parts = []
    if sender:
        parts.append(f"Nadawca: {sender}")
    if shipment_id:
        parts.append(f"Numer zlecenia/ładunku: {shipment_id}")
    if parts:
        return "\n".join(parts) + "\n\n" + message_text
    return message_text


def call_claude(user_text: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        return "[ERROR] Brak ANTHROPIC_API_KEY w zmiennych środowiskowych."

    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "max_tokens": 400,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_text}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(MESSAGES_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()
    except httpx.HTTPStatusError as exc:
        body_text = exc.response.text[:300]
        return f"[ERROR] Anthropic {exc.response.status_code}: {body_text}"
    except httpx.RequestError as exc:
        return f"[ERROR] RequestError: {exc}"
    except Exception as exc:
        return f"[ERROR] {exc}"


def generate_response(prompt: str, mode: str = "stub") -> str:
    llm_mode = os.environ.get("LLM_MODE", mode)

    if llm_mode == "remote":
        return call_claude(prompt)

    if llm_mode == "local":
        return f"[LOCAL stub] {prompt[:200]}"

    # stub mode — simple keyword matching for manual testing
    text = prompt.lower()
    if any(k in text for k in ("transport", "ładunek", "przesył", "zlecenie")):
        return "Dziękuję za zapytanie. Sprawdzam dostępność i wrócę z propozycją."
    if any(k in text for k in ("offer_received", "oferta", "offer")):
        return "Otrzymano nową ofertę — przekazuję do weryfikacji."
    if any(k in text for k in ("order.created", "zlecenie utworzone")):
        return "Nowe zlecenie zostało zarejestrowane."
    return "Wiadomość odebrana. Skontaktujemy się wkrótce."
