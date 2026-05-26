"""
Real Trans.eu API client (OAuth 2.0, Resource Owner Password Credentials).
Requires env vars: TRANS_CLIENT_ID, TRANS_CLIENT_SECRET, TRANS_API_KEY,
                   TRANS_USERNAME, TRANS_PASSWORD
"""

import base64
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()


class TransEuAuth:
    AUTH_URL = "https://auth.system.trans.eu/oauth2/token"

    def __init__(self):
        self.client_id = os.getenv("TRANS_CLIENT_ID")
        self.client_secret = os.getenv("TRANS_CLIENT_SECRET")
        self.api_key = os.getenv("TRANS_API_KEY")
        self.username = os.getenv("TRANS_USERNAME")
        self.password = os.getenv("TRANS_PASSWORD")

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

    def _basic_auth_header(self) -> str:
        credentials = f"{self.client_id}:{self.client_secret}"
        return "Basic " + base64.b64encode(credentials.encode()).decode()

    def get_token(self) -> str:
        if self._is_token_valid():
            return self._access_token
        if self._refresh_token:
            return self._refresh_access_token()
        return self._fetch_new_token()

    def _is_token_valid(self) -> bool:
        if not self._access_token or not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at - timedelta(seconds=60)

    def _fetch_new_token(self) -> str:
        resp = requests.post(
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
            },
            timeout=30,
        )
        resp.raise_for_status()
        return self._save_token(resp.json())

    def _refresh_access_token(self) -> str:
        resp = requests.post(
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
            },
            timeout=30,
        )
        if resp.status_code == 400:
            return self._fetch_new_token()
        resp.raise_for_status()
        return self._save_token(resp.json())

    def _save_token(self, data: dict) -> str:
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._token_expires_at = datetime.now() + timedelta(seconds=data.get("expires_in", 3600))
        return self._access_token

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class TransEuClient:
    BASE_URL = "https://api.system.trans.eu/rest/v1"

    def __init__(self):
        self.auth = TransEuAuth()
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        resp = self.session.request(
            method,
            f"{self.BASE_URL}{endpoint}",
            headers=self.auth.get_headers(),
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- FREIGHTS ---

    def get_freights(self, params: dict = None) -> dict:
        return self._request("GET", "/freights", params=params)

    def get_freight(self, freight_id: str) -> dict:
        return self._request("GET", f"/freights/{freight_id}")

    def create_freight(self, data: dict) -> dict:
        return self._request("POST", "/freights", json=data)

    def update_freight(self, freight_id: str, data: dict) -> dict:
        return self._request("PUT", f"/freights/{freight_id}", json=data)

    def delete_freight(self, freight_id: str) -> None:
        self._request("DELETE", f"/freights/{freight_id}")

    def publish_freight(self, freight_id: str) -> dict:
        return self._request("POST", f"/freights/{freight_id}/publications")

    def get_freight_offers(self, freight_id: str) -> dict:
        return self._request("GET", f"/freights/{freight_id}/offers")

    def accept_freight_offer(self, freight_id: str, offer_id: str) -> dict:
        return self._request("PUT", f"/freights/{freight_id}/offers/{offer_id}/accept")

    def reject_freight_offer(self, freight_id: str, offer_id: str) -> dict:
        return self._request("PUT", f"/freights/{freight_id}/offers/{offer_id}/reject")

    # --- ORDERS ---

    def get_orders(self, params: dict = None) -> dict:
        return self._request("GET", "/freight-orders", params=params)

    def get_received_orders(self, params: dict = None) -> dict:
        return self._request("GET", "/freight-orders/received", params=params)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/freight-orders/{order_id}")

    def create_order(self, data: dict) -> dict:
        return self._request("POST", "/freight-orders", json=data)

    def confirm_loading(self, order_id: str) -> dict:
        return self._request("PUT", f"/freight-orders/{order_id}/loading")

    def confirm_delivery(self, order_id: str) -> dict:
        return self._request("PUT", f"/freight-orders/{order_id}/delivery")

    # --- VEHICLES ---

    def get_vehicles(self, params: dict = None) -> dict:
        return self._request("GET", "/vehicles", params=params)

    def create_vehicle_offer(self, data: dict) -> dict:
        return self._request("POST", "/vehicles", json=data)

    # --- CONTRACTORS ---

    def get_contractors(self, params: dict = None) -> dict:
        return self._request("GET", "/contractors", params=params)

    def get_contractor(self, contractor_id: str) -> dict:
        return self._request("GET", f"/contractors/{contractor_id}")

    # --- TRANSPORTS IN REALIZATION ---

    def get_transports(self, params: dict = None) -> dict:
        return self._request("GET", "/transports", params=params)

    def get_transport_trace(self, transport_id: str) -> dict:
        return self._request("GET", f"/transports/{transport_id}/trace")

    # --- MY COMPANY ---

    def get_my_company(self) -> dict:
        return self._request("GET", "/companies/my-company")

    def get_employees(self) -> dict:
        return self._request("GET", "/employees")
