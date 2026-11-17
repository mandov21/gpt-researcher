"""Minimal Kalshi REST client with RSA-PSS request signing.

Prices are dollar strings ("0.5600"). Orders use the V2 endpoint (the legacy
/portfolio/orders write endpoints return 410). Verify against docs.kalshi.com before going live.
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
        """Returns {"yes_dollars": [[price, qty], ...], "no_dollars": [...]} of resting BIDS."""
        return self._request("GET", f"/markets/{ticker}/orderbook", auth=False).get("orderbook_fp", {})

    # -- portfolio (authenticated) ---------------------------------------
    def get_balance_usd(self) -> float:
        return float(self._request("GET", "/portfolio/balance")["balance"]) / 100  # cents -> $

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/portfolio/positions").get("market_positions", [])

    def place_order(self, ticker: str, side: str, count: int, price: float,
                    client_order_id: str | None = None, tif: str = "immediate_or_cancel") -> dict:
        """V2 order. side='yes' buys YES at `price`; side='no' buys NO at `price`.
        The V2 book is YES-only: buying NO at q == selling YES (ask) at 1-q."""
        assert side in ("yes", "no") and count >= 1 and 0.01 <= price <= 0.99
        yes_price = price if side == "yes" else round(1 - price, 4)
        body = {
            "ticker": ticker,
            "side": "bid" if side == "yes" else "ask",
            "count": f"{count:.2f}",
            "price": f"{yes_price:.4f}",
            "time_in_force": tif,
            "self_trade_prevention_type": "taker_at_cross",
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/portfolio/events/orders", json=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/events/orders/{order_id}")
