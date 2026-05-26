# Transport Assistant — lokalny prototyp

Prototyp asystenta dla małej firmy transportowej. Odbiera wiadomości (z platformy Trans.eu i przez e-mail/Thunderbird), generuje odpowiedzi przez LLM oraz tworzy notatki z kluczowymi danymi.

## Uruchamianie

```powershell
cd C:\Users\ziela\Desktop\programowanie\transport_assistant
poetry install
poetry run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (sterowanie agentem, podgląd wiadomości) — katalog `frontend/`:

```powershell
python -m http.server 3000
# otwórz http://127.0.0.1:3000
```

## Konfiguracja (.env)

```env
# Trans.eu API
TRANS_CLIENT_ID=
TRANS_CLIENT_SECRET=
TRANS_API_KEY=
TRANS_USERNAME=
TRANS_PASSWORD=

# E-mail (IMAP — Thunderbird lub dowolny klient)
EMAIL_HOST=imap.example.com
EMAIL_USER=firma@example.com
EMAIL_PASSWORD=
EMAIL_FOLDER=INBOX

# LLM
LLM_PROVIDER=claude          # claude | openai | local
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
```

## Źródła wiadomości

### Trans.eu API
Pełna dokumentacja: `TRANSEU.md`. Klient Python: `backend/transeu_client.py`.

- Auth: OAuth 2.0 (`https://auth.system.trans.eu`)
- Base URL: `https://api.system.trans.eu/rest/v1`
- Webhooki: zdarzenia `freights.freight.offer_received`, `freight_orders.order.created` itp.
  Rejestracja callbacków przez api@trans.eu. Lokalnie symuluj: `POST /simulate/transeu-event`.

### Thunderbird / E-mail (IMAP)
Thunderbird nie ma REST API — wiadomości są odczytywane bezpośrednio przez IMAP z tego samego konta pocztowego.

```python
# pip install imap-tools
from imap_tools import MailBox
with MailBox(EMAIL_HOST).login(EMAIL_USER, EMAIL_PASSWORD) as mb:
    for msg in mb.fetch(limit=10, reverse=True):
        # wrzuć msg do POST /webhook
```

Docelowo: `backend/email_reader.py` uruchamiany w tle (polling co N minut).

## Typy wiadomości

System obsługuje 5 typów zdarzeń z Trans.eu. Każde zdarzenie trafia do agenta LLM, który generuje sugerowaną odpowiedź.

| Alias | Trans.eu `event_type` | Opis | Źródło (polling) |
|---|---|---|---|
| `offer_received` | `freights.freight.offer_received` | Oferta cenowa złożona na nasz ładunek | `GET /freights/{id}/offers` |
| `order_created` | `freight_orders.order.created` | Nowe zlecenie transportowe | `GET /freight-orders/received` |
| `loading_confirmed` | `freight_orders.order.loading_confirmed` | Kierowca potwierdził załadunek | `GET /transports` |
| `delivery_confirmed` | `freight_orders.order.delivery_was_confirmed` | Dostawa potwierdzona, zlecenie zamknięte | `GET /transports` |
| `new_freight` | `freights.freight.published` | Nowy ładunek na giełdzie (pasująca oferta) | `GET /freights?status=published` |

Testowanie bez dostępu do Trans.eu:
```
POST /mock/generate                      # losowy typ
POST /mock/generate/offer_received       # oferta
POST /mock/generate/order_created        # zlecenie
POST /mock/generate/loading_confirmed    # załadunek
POST /mock/generate/delivery_confirmed   # dostawa
POST /mock/generate/new_freight          # giełda
GET  /mock/event-types                   # lista typów
```

## Endpointy mock API

| Endpoint | Metoda | Opis |
|---|---|---|
| `/freights` | GET | Lista ładunków (format Trans.eu v1) |
| `/freights/{id}` | GET | Szczegóły ładunku |
| `/freight-orders` | GET | Lista zleceń |
| `/freight-orders/received` | GET | Zlecenia otrzymane |
| `/vehicles` | GET | Oferty pojazdów |
| `/contractors` | GET | Kontrahenci |
| `/messages` | GET/POST | Wiadomości (mock lokalny) |
| `/webhook` | POST | Webhook (plain + Trans.eu event format) |
| `/simulate/message` | POST | Symuluj wiadomość testową |
| `/simulate/transeu-event` | POST | Symuluj zdarzenie Trans.eu (offer_received) |
| `/responses` | GET | Odpowiedzi agenta |
| `/notes` | GET | Notatki |
| `/agent/status` | GET | Stan agenta |
| `/health` | GET | Health check |
