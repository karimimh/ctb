from __future__ import annotations
import requests
from typing import Any, List
import time
import hmac
import hashlib
import urllib.parse

BASE_URL = "https://api.binance.com"

class BinanceClient:
    def __init__(self, timeout: int = 10, api_key: str | None = None, api_secret: str | None = None, sandbox: bool = False):
        self.timeout = timeout
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key or not self.api_secret:
            raise ValueError("Signed endpoint requires API key/secret")
        params = dict(params)
        params['timestamp'] = int(time.time() * 1000)
        qs = urllib.parse.urlencode(params, doseq=True)
        signature = hmac.new(self.api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
        url = f"{BASE_URL}{path}"
        headers = {}
        data = None
        if signed:
            params = self._sign_params(params or {})
            headers['X-MBX-APIKEY'] = self.api_key  # type: ignore[arg-type]
        if method == 'GET':
            r = requests.get(url, params=params, timeout=self.timeout, headers=headers)
        else:
            # For POST signed endpoints Binance expects application/x-www-form-urlencoded
            r = requests.post(url, data=params, timeout=self.timeout, headers=headers)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:  # noqa: BLE001
            # Attempt to extract error body
            try:
                err_json = r.json()
            except Exception:  # noqa: BLE001
                err_json = {'body': r.text}
            raise RuntimeError(f"Binance API error {r.status_code}: {err_json}") from e
        return r.json()

    def _get(self, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
        return self._request('GET', path, params=params, signed=signed)

    def fetch_symbols_usdc(self, limit: int | None = None) -> list[str]:
        data = self._get("/api/v3/exchangeInfo")
        symbols = []
        for s in data["symbols"]:
            if s.get("status") != "TRADING":
                continue
            # We interpret requirement as pairs with USDC as quote (e.g. BTCUSDC)
            if s.get("quoteAsset") == "USDC":
                symbols.append(s["symbol"])
        if limit:
            symbols = symbols[:limit]
        return symbols

    def fetch_klines(self, symbol: str, interval: str, limit: int = 500) -> list[list[Any]]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        return self._get("/api/v3/klines", params=params)

    def fetch_klines_range(self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int = 1000, sleep: float = 0.2) -> List[list[Any]]:
        """Fetch klines for a symbol/interval covering [start_ms, end_ms] inclusive.

        Binance returns up to 1000 candles per call. We paginate by advancing startTime to the
        open time of the last returned kline + 1 ms until we exceed end_ms.
        """
        all_kl: List[list[Any]] = []
        current_start = start_ms
        while current_start <= end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "startTime": current_start,
                "endTime": end_ms,
            }
            batch = self._get("/api/v3/klines", params=params)
            if not batch:
                break
            all_kl.extend(batch)
            last_open = batch[-1][0]
            # Prevent infinite loop if API returns same last candle repeatedly
            if last_open == current_start:
                break
            current_start = last_open + 1
            # Rate limit courtesy pause
            if sleep:
                time.sleep(sleep)
            # Safety: stop if we already passed end
            if last_open >= end_ms:
                break
        return all_kl

    # --- Trading / Account ---
    def get_price(self, symbol: str) -> float:
        data = self._get('/api/v3/ticker/price', params={'symbol': symbol})
        return float(data['price'])

    def place_order_market(self, symbol: str, side: str, quantity: float) -> Any:
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': self._format_quantity(quantity),
        }
        return self._request('POST', '/api/v3/order', params=params, signed=True)

    def _format_quantity(self, qty: float) -> str:
        # Simplistic formatting; in production we would query exchangeInfo for lot size filters
        return f"{qty:.6f}".rstrip('0').rstrip('.')
