# Trans.eu Platform API — Dokumentacja dla Claude Code

> Źródło: https://www.trans.eu/api/  
> Oficjalne repo: https://github.com/Transeu/api-rest-documentation  
> Kontakt: api@trans.eu

---

## SPIS TREŚCI

1. [Przegląd API](#1-przegląd-api)
2. [Rejestracja i uzyskanie dostępu](#2-rejestracja-i-uzyskanie-dostępu)
3. [Autoryzacja i tokeny](#3-autoryzacja-i-tokeny)
4. [Struktura requestów](#4-struktura-requestów)
5. [Moduły API — przegląd endpointów](#5-moduły-api--przegląd-endpointów)
6. [Przykłady w Pythonie](#6-przykłady-w-pythonie)
7. [Błędy i kody odpowiedzi](#7-błędy-i-kody-odpowiedzi)
8. [Słowniki i wartości](#8-słowniki-i-wartości)
9. [Callback URLs (Webhooks)](#9-callback-urls-webhooks)
10. [Linki do pełnej dokumentacji](#10-linki-do-pełnej-dokumentacji)

---

## 1. PRZEGLĄD API

Trans.eu API to REST API platformy transportowej łączącej Shippers, Freight Forwarders i Carriers.

**Baza URL API:** `https://api.system.trans.eu`  
**Baza URL Auth:** `https://auth.system.trans.eu`  
**Format danych:** JSON  
**Protokół autoryzacji:** OAuth 2.0  

**Główne moduły:**
- Freights (ładunki)
- Orders (zlecenia transportowe)
- Vehicles (pojazdy)
- Partners (kontrahenci)
- Fleet (flota)
- Transports in realization (transport w realizacji)
- Dock Scheduler (harmonogram doków)
- My Company (dane firmy)
- Attachments (załączniki)

---

## 2. REJESTRACJA I UZYSKANIE DOSTĘPU

### Wymagania wstępne

Aby korzystać z API potrzebujesz:

1. **Konta firmowego** na platformie Trans.eu  
   → Rejestracja: https://register.trans.eu/?lang=en

2. **Zarejestrowanej aplikacji** (aby uzyskać `client_id`, `client_secret`, `api-key`)  
   → Formularz: https://www.trans.eu/api/register-your-app/

3. **TransId** — unikalny identyfikator użytkownika w formacie `CompanyId-EmployeeId`  
   Przykład: `12-1234` (CompanyId=12, EmployeeId=1234)  
   → Aby uzyskać TransId: kontakt z api@trans.eu

### Co otrzymujesz po rejestracji aplikacji

| Credential | Opis |
|---|---|
| `client_id` | Identyfikator Twojej aplikacji |
| `client_secret` | Tajny klucz aplikacji (NIGDY nie umieszczaj w URL) |
| `api-key` | Klucz API wymagany w nagłówku każdego requestu |

---

## 3. AUTORYZACJA I TOKENY

### Dwa przepływy OAuth 2.0

#### Przepływ A: Resource Owner Password Credentials (dla aplikacji wewnętrznych)

Najprostszy przepływ — bezpośrednie wysłanie loginu i hasła użytkownika.  
**Wymaga:** grant type `password` dopuszczonego dla Twojej aplikacji.

**Request:**
```
POST /oauth2/token
Host: auth.system.trans.eu
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client_id:client_secret)>

grant_type=password
&username=jan.kowalski@trans.eu   # lub TransId np. 12-1234
&password=haslo_uzytkownika
&scope=offers.loads.manage
&client_id=example_app_client_id
&client_secret=example_app_client_secret
```

**Response (200 OK):**
```json
{
  "access_token": "59d9aa9b15cd59a61fc52014792efb6caa82373b",
  "expires_in": 3600,
  "token_type": "Bearer",
  "scope": "offers.loads.manage",
  "refresh_token": "d52d1d998d6533a3be8e7f26f904be513287938b"
}
```

#### Przepływ B: Authorization Code Grant (dla aplikacji zewnętrznych / SaaS)

Klasyczny OAuth redirect flow — użytkownik loguje się przez przeglądarkę.

**Krok 1 — redirect do serwera autoryzacji:**
```
GET https://auth.system.trans.eu/oauth2/auth
  ?client_id=example_app_client_id
  &response_type=code
  &redirect_uri=https://example.com/callback
  &state=random_csrf_token
```

**Krok 2 — odbiór kodu:**
```
# Serwer autoryzacji przekierowuje na:
https://example.com/callback?code=SDF41D54F54D45DF4

# UWAGA: kod jest ważny tylko 1 minutę!
```

**Krok 3 — wymiana kodu na token:**
```
POST /oauth2/token
Host: auth.system.trans.eu
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=SDF41D54F54D45DF4
&redirect_uri=https://example.com/callback
&client_id=example_app_client_id
&client_secret=example_app_secret
```

### Odświeżanie tokenu (Refresh Token)

```
POST /oauth2/token
Host: auth.system.trans.eu
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&refresh_token=d52d1d998d6533a3be8e7f26f904be513287938b
&client_id=example_app_client_id
&client_secret=example_app_secret
```

### Ważne informacje o tokenach

| Parametr | Wartość |
|---|---|
| `access_token` ważność | **1 godzina** (3600 sekund) |
| `refresh_token` ważność | **60 dni** (jednorazowy!) |
| Po użyciu refresh_token | otrzymujesz nową parę tokenów |
| Typ tokenu | Bearer |

### Użycie tokenu w requestach

Każdy request do API musi zawierać dwa nagłówki:

```
Authorization: Bearer <access_token>
Api-key: <twój_api_key>
```

---

## 4. STRUKTURA REQUESTÓW

### Nagłówki (wymagane dla każdego endpointu)

```
Authorization: Bearer 59d9aa9b15cd59a61fc52014792efb6caa82373b
Api-key: twoj_api_key
Content-Type: application/json
Accept: application/json
```

### Autentykacja aplikacji — ważne zasady

- `client_secret` przekazuj TYLKO w body requestu lub nagłówku `Authorization: Basic`
- NIGDY nie umieszczaj `client_secret` w URL query string
- Używaj wyłącznie HTTPS (TLS)

---

## 5. MODUŁY API — PRZEGLĄD ENDPOINTÓW

### 5.1 FREIGHTS (Ładunki)

**Base:** `https://api.system.trans.eu/rest/v1/freights`

| Metoda | Endpoint | Opis |
|---|---|---|
| POST | `/freights` | Utwórz ładunek |
| PUT | `/freights/{id}` | Aktualizuj ładunek |
| DELETE | `/freights/{id}` | Usuń ładunek |
| GET | `/freights/{id}` | Pobierz szczegóły ładunku |
| GET | `/freights` | Lista ładunków |
| GET | `/freights/accepted` | Lista zaakceptowanych ładunków |
| GET | `/freights/archived` | Lista zarchiwizowanych ładunków |

**Publikacja ładunku:**

| Metoda | Endpoint | Opis |
|---|---|---|
| POST | `/freights/{id}/publications` | Publikuj na Trans.eu Exchange |
| POST | `/freights/{id}/publications/private` | Publikuj na prywatnej giełdzie |
| POST | `/freights/{id}/publications/multi` | Publikuj na wielu giełdach |
| DELETE | `/freights/{id}/publications` | Anuluj publikację |
| PUT | `/freights/{id}/publications/refresh` | Odśwież publikację |

**Negocjacje:**

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/freights/{id}/offers` | Lista ofert do ładunku |
| GET | `/freights/{id}/offers/{offer_id}` | Szczegóły oferty |
| PUT | `/freights/{id}/offers/{offer_id}/negotiate` | Kontrproponuj cenę |
| PUT | `/freights/{id}/offers/{offer_id}/accept` | Akceptuj ofertę |
| PUT | `/freights/{id}/offers/{offer_id}/reject` | Odrzuć ofertę |

**Dokumentacja:** https://www.trans.eu/api/freights-section/freight-creation/

---

### 5.2 ORDERS (Zlecenia transportowe)

**Base:** `https://api.system.trans.eu/rest/v1/freight-orders`

| Metoda | Endpoint | Opis |
|---|---|---|
| POST | `/freight-orders` | Utwórz zlecenie |
| GET | `/freight-orders` | Lista utworzonych zleceń |
| GET | `/freight-orders/received` | Lista otrzymanych zleceń |
| GET | `/freight-orders/{id}` | Szczegóły zlecenia |
| PUT | `/freight-orders/{id}/cancel` | Anuluj zlecenie |
| PUT | `/freight-orders/{id}/archive` | Archiwizuj zlecenie |

**Potwierdzenia realizacji:**

| Metoda | Endpoint | Opis |
|---|---|---|
| PUT | `/freight-orders/{id}/arrival-at-loading` | Potwierdź przybycie do załadunku |
| PUT | `/freight-orders/{id}/loading` | Potwierdź załadunek |
| PUT | `/freight-orders/{id}/arrival-at-unloading` | Potwierdź przybycie do rozładunku |
| PUT | `/freight-orders/{id}/unloading` | Potwierdź rozładunek |
| PUT | `/freight-orders/{id}/delivery` | Potwierdź dostawę |

**Dokumentacja:** https://www.trans.eu/api/orders/orders-description/

---

### 5.3 VEHICLES (Pojazdy — oferty)

**Base:** `https://api.system.trans.eu/rest/v1/vehicles`

| Metoda | Endpoint | Opis |
|---|---|---|
| POST | `/vehicles` | Utwórz ofertę pojazdu |
| PUT | `/vehicles/{id}` | Aktualizuj ofertę |
| DELETE | `/vehicles/{id}` | Usuń ofertę |
| GET | `/vehicles` | Lista ofert pojazdów |
| GET | `/vehicles/{id}` | Szczegóły oferty pojazdu |
| PUT | `/vehicles/{id}/refresh` | Odśwież ofertę |

**Dokumentacja:** https://www.trans.eu/api/vehicles/vehicle-offer-description/

---

### 5.4 PARTNERS (Kontrahenci)

**Base:** `https://api.system.trans.eu/rest/v1/contractors`

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/contractors` | Lista kontrahentów |
| GET | `/contractors/{id}` | Szczegóły kontrahenta |
| POST | `/contractors` | Dodaj kontrahenta |
| POST | `/contractors/{id}/invitation` | Wyślij zaproszenie |
| PUT | `/contractors/{id}/block` | Zablokuj współpracę |
| PUT | `/contractors/{id}/activate` | Aktywuj współpracę |
| GET | `/contractors/{id}/fleet` | Flota kontrahenta |
| GET | `/contractors/{id}/employees` | Pracownicy kontrahenta |

**Dokumentacja:** https://www.trans.eu/api/partners/contractor-description/

---

### 5.5 FLEET (Flota własna)

**Base:** `https://api.system.trans.eu/rest/v1/fleet`

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/fleet/vehicles` | Lista pojazdów firmy |
| GET | `/fleet/vehicles/{id}` | Szczegóły pojazdu |
| POST | `/fleet/vehicles` | Dodaj pojazd |
| DELETE | `/fleet/vehicles/{id}` | Usuń pojazd |

**Dokumentacja:** https://www.trans.eu/api/fleet/vehicle-fleet-description/

---

### 5.6 TRANSPORTS IN REALIZATION (Monitoring)

**Base:** `https://api.system.trans.eu/rest/v1/transports`

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/transports` | Lista transportów w realizacji |
| GET | `/transports/{id}` | Szczegóły transportu |
| GET | `/transports/{id}/monitoring-events` | Eventy monitoringu |
| GET | `/transports/{id}/trace` | Trasa (GeoJSON format) |

**Dokumentacja:** https://www.trans.eu/api/transports-in-realization/getting-information-about-transports-in-realization/

---

### 5.7 DOCK SCHEDULER

**Base:** `https://api.system.trans.eu/rest/v1/dock-scheduler`

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/time-windows` | Lista okien czasowych |
| GET | `/time-windows/{id}` | Szczegóły okna |
| POST | `/time-windows` | Dodaj okno czasowe |
| PUT | `/time-windows/{id}` | Aktualizuj okno |
| DELETE | `/time-windows/{id}` | Usuń okno |
| GET | `/announcements` | Lista awizacji |
| GET | `/announcements/{id}` | Szczegóły awizacji |
| POST | `/announcements` | Dodaj awizację |
| PUT | `/announcements/{id}` | Aktualizuj awizację |
| DELETE | `/announcements/{id}` | Usuń awizację |
| GET | `/warehouses` | Lista magazynów |
| GET | `/warehouses/{id}` | Szczegóły magazynu |

**Dokumentacja:** https://www.trans.eu/api/dock-scheduler/dock-scheduler-description/

---

### 5.8 MY COMPANY

**Base:** `https://api.system.trans.eu/rest/v1`

| Metoda | Endpoint | Opis |
|---|---|---|
| GET | `/employees` | Lista pracowników firmy |
| GET | `/companies/my-company` | Dane własnej firmy |

---

### 5.9 ATTACHMENTS

| Metoda | Endpoint | Opis |
|---|---|---|
| POST | `/attachments` | Upload załącznika |
| GET | `/attachments/{id}` | Pobierz załącznik |

**Dokumentacja:** https://www.trans.eu/api/attachments/uploading-and-downloading-attachments/

---

## 6. PRZYKŁADY W PYTHONIE

### Instalacja zależności

```bash
pip install requests python-dotenv
```

### Struktura pliku .env

```env
TRANS_CLIENT_ID=twoj_client_id
TRANS_CLIENT_SECRET=twoj_client_secret
TRANS_API_KEY=twoj_api_key
TRANS_USERNAME=jan.kowalski@trans.eu
TRANS_PASSWORD=twoje_haslo
```

---

### Klasa klienta Trans.eu API

```python
import os
import base64
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class TransEuAuth:
    """
    Klient autoryzacji Trans.eu API (OAuth 2.0).
    Obsługuje Resource Owner Password Credentials grant.
    """
    
    AUTH_URL = "https://auth.system.trans.eu/oauth2/token"
    
    def __init__(self):
        self.client_id = os.getenv("TRANS_CLIENT_ID")
        self.client_secret = os.getenv("TRANS_CLIENT_SECRET")
        self.api_key = os.getenv("TRANS_API_KEY")
        self.username = os.getenv("TRANS_USERNAME")
        self.password = os.getenv("TRANS_PASSWORD")
        
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = None
    
    def _basic_auth_header(self) -> str:
        """Tworzy nagłówek Basic Auth z client_id:client_secret."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def get_token(self) -> str:
        """Pobiera access_token — odświeża automatycznie jeśli wygasł."""
        if self._is_token_valid():
            return self._access_token
        
        if self._refresh_token:
            return self._refresh_access_token()
        
        return self._fetch_new_token()
    
    def _is_token_valid(self) -> bool:
        if not self._access_token or not self._token_expires_at:
            return False
        # Bufor 60 sekund przed wygaśnięciem
        return datetime.now() < self._token_expires_at - timedelta(seconds=60)
    
    def _fetch_new_token(self) -> str:
        """Pobiera nowy token przez Resource Owner Password Credentials."""
        response = requests.post(
            self.AUTH_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "scope": "offers.loads.manage offers.trucks.manage",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )
        response.raise_for_status()
        return self._save_token(response.json())
    
    def _refresh_access_token(self) -> str:
        """Odświeża token używając refresh_token."""
        response = requests.post(
            self.AUTH_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )
        
        if response.status_code == 400:
            # refresh_token wygasł — pobierz nowy token
            return self._fetch_new_token()
        
        response.raise_for_status()
        return self._save_token(response.json())
    
    def _save_token(self, data: dict) -> str:
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        return self._access_token
    
    def get_headers(self) -> dict:
        """Zwraca pełne nagłówki do requestów API."""
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class TransEuClient:
    """
    Główny klient Trans.eu API.
    """
    
    BASE_URL = "https://api.system.trans.eu/rest/v1"
    
    def __init__(self):
        self.auth = TransEuAuth()
        self.session = requests.Session()
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.BASE_URL}{endpoint}"
        headers = self.auth.get_headers()
        
        response = self.session.request(
            method,
            url,
            headers=headers,
            **kwargs
        )
        response.raise_for_status()
        return response.json() if response.content else {}
    
    # --- FREIGHTS ---
    
    def create_freight(self, freight_data: dict) -> dict:
        """Tworzy nowy ładunek."""
        return self._request("POST", "/freights", json=freight_data)
    
    def get_freights(self, params: dict = None) -> dict:
        """Pobiera listę ładunków."""
        return self._request("GET", "/freights", params=params)
    
    def get_freight(self, freight_id: str) -> dict:
        """Pobiera szczegóły ładunku."""
        return self._request("GET", f"/freights/{freight_id}")
    
    def update_freight(self, freight_id: str, data: dict) -> dict:
        """Aktualizuje ładunek."""
        return self._request("PUT", f"/freights/{freight_id}", json=data)
    
    def delete_freight(self, freight_id: str) -> None:
        """Usuwa ładunek."""
        self._request("DELETE", f"/freights/{freight_id}")
    
    def publish_freight(self, freight_id: str) -> dict:
        """Publikuje ładunek na Trans.eu Exchange."""
        return self._request("POST", f"/freights/{freight_id}/publications")
    
    # --- ORDERS ---
    
    def create_order(self, order_data: dict) -> dict:
        """Tworzy zlecenie transportowe."""
        return self._request("POST", "/freight-orders", json=order_data)
    
    def get_orders(self, params: dict = None) -> dict:
        """Pobiera listę zleceń."""
        return self._request("GET", "/freight-orders", params=params)
    
    def get_order(self, order_id: str) -> dict:
        """Pobiera szczegóły zlecenia."""
        return self._request("GET", f"/freight-orders/{order_id}")
    
    # --- VEHICLES ---
    
    def get_vehicles(self, params: dict = None) -> dict:
        """Pobiera listę ofert pojazdów."""
        return self._request("GET", "/vehicles", params=params)
    
    def create_vehicle_offer(self, vehicle_data: dict) -> dict:
        """Tworzy ofertę pojazdu."""
        return self._request("POST", "/vehicles", json=vehicle_data)
    
    # --- PARTNERS ---
    
    def get_contractors(self, params: dict = None) -> dict:
        """Pobiera listę kontrahentów."""
        return self._request("GET", "/contractors", params=params)
    
    def get_contractor(self, contractor_id: str) -> dict:
        """Pobiera szczegóły kontrahenta."""
        return self._request("GET", f"/contractors/{contractor_id}")
    
    # --- MY COMPANY ---
    
    def get_my_company(self) -> dict:
        """Pobiera dane własnej firmy."""
        return self._request("GET", "/companies/my-company")
    
    def get_employees(self) -> dict:
        """Pobiera listę pracowników."""
        return self._request("GET", "/employees")
    
    # --- TRANSPORTS IN REALIZATION ---
    
    def get_transports(self, params: dict = None) -> dict:
        """Pobiera listę transportów w realizacji."""
        return self._request("GET", "/transports", params=params)
    
    def get_transport_trace(self, transport_id: str) -> dict:
        """Pobiera trasę transportu w formacie GeoJSON."""
        return self._request("GET", f"/transports/{transport_id}/trace")
```

---

### Przykład użycia — pobieranie ładunków

```python
def main():
    client = TransEuClient()
    
    # Pobierz listę ładunków
    freights = client.get_freights(params={"page": 1, "per_page": 20})
    print(f"Znaleziono ładunków: {len(freights.get('data', []))}")
    
    # Utwórz nowy ładunek
    new_freight = {
        "load_date": "2026-06-01",
        "unload_date": "2026-06-02",
        "loading_place": {
            "address": {
                "country": "PL",
                "postal_code": "00-001",
                "locality": "Warszawa"
            }
        },
        "unloading_place": {
            "address": {
                "country": "DE",
                "postal_code": "10115",
                "locality": "Berlin"
            }
        },
        "load_weight": {
            "value": 24000,
            "unit_code": "KGM"
        },
        "price": {
            "value": 1500,
            "currency": "EUR"
        },
        "vehicle_type": ["tent"]
    }
    
    created = client.create_freight(new_freight)
    freight_id = created["id"]
    print(f"Utworzono ładunek: {freight_id}")
    
    # Opublikuj na giełdzie
    client.publish_freight(freight_id)
    print("Ładunek opublikowany!")


if __name__ == "__main__":
    main()
```

---

### Przykład — tylko autoryzacja (minimal)

```python
import requests
import base64

CLIENT_ID = "twoj_client_id"
CLIENT_SECRET = "twoj_client_secret"
USERNAME = "jan.kowalski@trans.eu"  # lub TransId: "12-1234"
PASSWORD = "twoje_haslo"

def get_token():
    credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    
    response = requests.post(
        "https://auth.system.trans.eu/oauth2/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "password",
            "username": USERNAME,
            "password": PASSWORD,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    )
    
    data = response.json()
    return data["access_token"], data["refresh_token"]

access_token, refresh_token = get_token()
print(f"Token: {access_token[:20]}...")
```

---

## 7. BŁĘDY I KODY ODPOWIEDZI

### HTTP Status Codes

| Kod | Znaczenie |
|---|---|
| 200 | Sukces |
| 201 | Zasób utworzony |
| 204 | Sukces, brak treści (np. DELETE) |
| 400 | Błędny request (walidacja danych) |
| 401 | Brak autoryzacji (zły/wygasły token) |
| 403 | Brak uprawnień (subskrypcja, uprawnienia) |
| 404 | Zasób nie istnieje |
| 422 | Błąd semantyczny danych |
| 429 | Zbyt wiele requestów (rate limit) |
| 500 | Błąd serwera |

### Błędy autoryzacji OAuth

```json
{
  "error": "invalid_grant",
  "error_description": "Invalid username and password combination"
}
```

| Kod błędu | Opis |
|---|---|
| `invalid_grant` | Złe hasło lub login |
| `invalid_client` | Zły client_id lub client_secret |
| `not_unique_username` | Email nie jest unikalny — użyj TransId |
| `invalid_request` | Brak wymaganych parametrów |

### Typowe błędy biznesowe

| Sytuacja | Kod | Rozwiązanie |
|---|---|---|
| Wygasła subskrypcja | 403 | Sprawdź subskrypcję na Trans.eu |
| Brak uprawnień do dodawania ofert | 403 | Firma musi być autoryzowana |
| Nieprawidłowy format daty | 400 | Format: `YYYY-MM-DD` |
| Brak wymaganego pola | 400 | Sprawdź dokumentację endpointu |

---

## 8. SŁOWNIKI I WARTOŚCI

### Typy pojazdów (`vehicle_type`)

```
tent          - Plandeka
coilmulde     - Mulda
mega          - Mega
jumbo         - Jumbo
ref           - Chłodnia
isothermal    - Izoterma
curtain_sider - Firanka
tanker        - Cysterna
flat          - Platforma
box           - Box
```

### Jednostki wagi (`unit_code`)

```
KGM - kilogramy
TNE - tony
```

### Waluty

```
EUR, PLN, CZK, HUF, RON, BGN, GBP, USD
```

### Kraje (ISO 3166-1 alpha-2)

```
PL, DE, FR, CZ, SK, HU, RO, BG, IT, ES, NL, BE, AT, ...
```

### Pełny słownik: https://www.trans.eu/api/general-information/allowed-values/

---

## 9. CALLBACK URLS (Webhooks)

Trans.eu API może wysyłać zdarzenia na Twój URL (callback).

**Dokumentacja:** https://www.trans.eu/api/general-information/api-callback-urls/

### Dostępne eventy (stan na 2026-02)

```
freights.freight.published          - ładunek opublikowany
freights.freight.offer_received     - otrzymano ofertę cenową
freights.freight.offer_accepted     - oferta zaakceptowana
freight_orders.order.created        - zlecenie utworzone
freight_orders.order.delivery_was_confirmed    - dostawa potwierdzona
freight_orders.order.transports_was_finished   - transport zakończony
transports.transport.devices_set_changed       - zmiana urządzeń monitoringu
```

### Konfiguracja callbacku

Skontaktuj się z api@trans.eu, aby zarejestrować URL dla webhooków.

---

## 9b. TYPY WIADOMOŚCI — co sprawdza asystent

Poniżej lista typów zdarzeń obsługiwanych przez `backend/poller.py` i `backend/mock_generator.py`.

| Alias w systemie | Trans.eu `event_type` | Opis | Źródło danych |
|---|---|---|---|
| `offer_received` | `freights.freight.offer_received` | Ktoś złożył **ofertę cenową** na nasz opublikowany ładunek | `GET /freights/{id}/offers` |
| `order_created` | `freight_orders.order.created` | Nowe **zlecenie transportowe** przypisane do firmy | `GET /freight-orders/received` |
| `loading_confirmed` | `freight_orders.order.loading_confirmed` | **Załadunek potwierdzony** przez kierowcę | `GET /transports` |
| `delivery_confirmed` | `freight_orders.order.delivery_was_confirmed` | **Dostawa potwierdzona**, zlecenie zamknięte | `GET /transports` |
| `new_freight` | `freights.freight.published` | Nowy **ładunek na giełdzie** (pasująca oferta od innej firmy) | `GET /freights?status=published` |

### Logika pollingu (backend/poller.py)

Co `POLL_INTERVAL_SECONDS` sekund (domyślnie 60) sprawdzamy:

1. **Oferty do ładunków** — iterujemy nasze ładunki, dla każdego `GET /freights/{id}/offers`. Nowe offer_id → `offer_received`.
2. **Nowe zlecenia** — `GET /freight-orders/received`. Nowy order_id → `order_created`.
3. **Statusy transportów** — `GET /transports`. Zmiana statusu (loading_confirmed, delivery_confirmed, finished) → odpowiedni event.
4. **Giełda** — `GET /freights?status=published`. Nowy freight_id → `new_freight`.

Każde zdarzenie trafia do `POST /webhook` → agent LLM generuje odpowiedź → notatka do pliku.

### Testowanie bez dostępu do Trans.eu

```bash
# losowe zdarzenie
POST /mock/generate

# konkretny typ
POST /mock/generate/offer_received
POST /mock/generate/order_created
POST /mock/generate/loading_confirmed
POST /mock/generate/delivery_confirmed
POST /mock/generate/new_freight

# lista typów
GET /mock/event-types
```

---

## 10. LINKI DO PEŁNEJ DOKUMENTACJI

| Sekcja | URL |
|---|---|
| Strona główna API | https://www.trans.eu/api/ |
| Autoryzacja (przepływ) | https://www.trans.eu/api/authorization/authorization-flow/ |
| Autoryzacja JWT | https://www.trans.eu/api/authorization/authorize-using-jwt/ |
| Rejestracja aplikacji | https://www.trans.eu/api/register-your-app/ |
| Freights — opis | https://www.trans.eu/api/freights-section/freight-creation/ |
| Orders — opis | https://www.trans.eu/api/orders/orders-description/ |
| Vehicles — opis | https://www.trans.eu/api/vehicles/vehicle-offer-description/ |
| Partners — opis | https://www.trans.eu/api/partners/contractor-description/ |
| Fleet — opis | https://www.trans.eu/api/fleet/vehicle-fleet-description/ |
| Transports monitoring | https://www.trans.eu/api/transports-in-realization/getting-information-about-transports-in-realization/ |
| Dock Scheduler | https://www.trans.eu/api/dock-scheduler/dock-scheduler-description/ |
| Callback URLs | https://www.trans.eu/api/general-information/api-callback-urls/ |
| Słowniki wartości | https://www.trans.eu/api/general-information/allowed-values/ |
| YAML / OpenAPI spec | https://www.trans.eu/api/yaml-documentation/ |
| FAQ | https://www.trans.eu/api/general-information/faq/ |
| GitHub (stara dok.) | https://github.com/Transeu/api-rest-documentation |
| Kontakt API | api@trans.eu |
