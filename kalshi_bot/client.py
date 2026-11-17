"""Minimal Kalshi REST client with RSA-PSS request signing.

Prices are integer cents (1-99) on the wire. Verify endpoints against
https://docs.kalshi.com before going live; the API evolves.
"""
import base64
import time
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .config import Config


class KalshiClient:
    def __init__(self, cfg: Config, session: requests.Session | None = None):
        self.cfg = cfg
        self.http = session or requests.Session()
        self._key = None
        if cfg.private_key_path:
            with open(cfg.private_key_path, "rb") as f:
                self._key = serialization.load_pem_private_key(f.read(), password=None)

    # -- auth -------------------------------------------------------------
    def _sign(self, ts_ms: str, method: str, path: str) -> str:
        msg = f"{ts_ms}{method}{path}".encode()
        sig = self._key.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def _headers(self, method: str, url: str) -> dict:
        ts = str(int(time.time() * 1000))
        path = urlparse(url).path  # signature excludes query string
        return {
            "KALSHI-ACCESS-KEY": self.cfg.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method, path),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, endpoint: str, *, params=None, json=None, auth=True) -> Any:
        url = self.cfg.base_url + endpoint
        headers = self._headers(method, url) if auth else {}
        for attempt in range(4):
            r = self.http.request(method, url, params=params, json=json, headers=headers, timeout=10)
            if r.status_code == 429:  # rate limited
                time.sleep(2 ** attempt * 0.5)
                headers = self._headers(method, url) if auth else {}
                continue
            r.raise_for_status()
            return r.json() if r.content else {}
        r.raise_for_status()

    # -- market data (public) --------------------------------------------
    def list_markets(self, **params) -> list[dict]:
        out, cursor = [], None
        while True:
            p = {"limit": 200, **params, **({"cursor": cursor} if cursor else {})}
            d = self._request("GET", "/markets", params=p, auth=False)
            out += d.get("markets", [])
            cursor = d.get("cursor")
            if not cursor:
                return out

    def get_market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}", auth=False)["market"]

    def get_orderbook(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}/orderbook", auth=False)["orderbook"]

    # -- portfolio (authenticated) ---------------------------------------
    def get_balance_cents(self) -> int:
        return self._request("GET", "/portfolio/balance")["balance"]

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/portfolio/positions").get("market_positions", [])

    def get_open_orders(self) -> list[dict]:
        return self._request("GET", "/portfolio/orders", params={"status": "resting"}).get("orders", [])

    def place_limit_order(self, ticker: str, side: str, count: int, price_cents: int,
                          action: str = "buy", client_order_id: str | None = None) -> dict:
        assert side in ("yes", "no") and action in ("buy", "sell")
        assert 1 <= price_cents <= 99 and count >= 1
        body = {
            "ticker": ticker, "action": action, "side": side, "type": "limit",
            "count": count, f"{side}_price": price_cents,
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/portfolio/orders", json=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")
