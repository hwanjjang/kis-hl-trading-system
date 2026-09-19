from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from kis_hl.config import BinanceConfig

logger = logging.getLogger(__name__)

KLINE_INTERVALS = (
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
)

_API_KEY_HEADER = "X-MBX-APIKEY"


def sign_query(secret: str, query: str) -> str:
    """HMAC-SHA256 hex digest over the exact query string, as Binance signed endpoints expect."""
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


class BinanceFuturesClient:
    """Read-only USD(S)-M futures client.

    Public reads need no credentials. Signed reads require both API key and secret and
    fail closed before any network call when either is missing. listenKey calls send only
    the API key header. This client places no orders.
    """

    def __init__(
        self,
        config: BinanceConfig,
        *,
        timeout_seconds: float = 10,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self.last_used_weight: int | None = None

    # ---- transport ---------------------------------------------------------------

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, str], str]:
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return (
                    int(response.status),
                    {k.lower(): v for k, v in response.headers.items()},
                    response.read().decode("utf-8"),
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return int(exc.code), {k.lower(): v for k, v in exc.headers.items()}, text

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        signed: bool = False,
        api_key_header: bool = False,
    ) -> Any:
        query_params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"Accept": "application/json"}
        if signed:
            self._require_credentials(need_secret=True)
            query_params["recvWindow"] = self.config.recv_window_ms
            query_params["timestamp"] = self._now_ms()
            query = urllib.parse.urlencode(query_params)
            query = f"{query}&signature={sign_query(self.config.api_secret, query)}"
        else:
            query = urllib.parse.urlencode(query_params)
        if signed or api_key_header:
            self._require_credentials(need_secret=signed)
            headers[_API_KEY_HEADER] = self.config.api_key

        url = f"{self.config.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        status, response_headers, text = self.send(method, url, headers, None)
        weight = response_headers.get("x-mbx-used-weight-1m")
        if weight is not None:
            try:
                self.last_used_weight = int(weight)
            except ValueError:
                pass
        payload = _parse_json(text)
        if status >= 400:
            code = payload.get("code") if isinstance(payload, dict) else None
            msg = payload.get("msg") if isinstance(payload, dict) else text
            logger.warning(
                "binance_request_failed",
                extra={"method": method, "path": path, "status": status, "code": code},
            )
            raise RuntimeError(f"Binance request failed: HTTP {status} {code}/{msg}")
        return payload

    def _require_credentials(self, *, need_secret: bool) -> None:
        if not self.config.api_key or (need_secret and not self.config.api_secret):
            raise RuntimeError(
                "Binance credentials are missing for the selected key profile; "
                "set BINANCE_APIKEY/BINANCE_SECRET or PRO_BINANCE_APIKEY/PRO_BINANCE_SECRET"
            )

    # ---- public market data ---------------------------------------------------------

    def server_time(self) -> int:
        payload = self._request("GET", "/fapi/v1/time")
        return int(payload["serverTime"])

    def exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": _normalize_symbol(symbol)} if symbol else None
        payload = self._request("GET", "/fapi/v1/exchangeInfo", params)
        if not isinstance(payload, dict):
            raise RuntimeError("Binance exchangeInfo returned an unexpected payload")
        return payload

    def symbol_filters(self, symbol: str) -> dict[str, Any]:
        wanted = _normalize_symbol(symbol)
        info = self.exchange_info(wanted)
        for entry in info.get("symbols", []):
            if entry.get("symbol") == wanted:
                return normalize_symbol_filters(entry)
        raise RuntimeError(f"Binance symbol {wanted} not found in exchangeInfo")

    def premium_index(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/premiumIndex", {"symbol": _normalize_symbol(symbol)})

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": _normalize_symbol(symbol)})

    def last_price(self, symbol: str) -> Decimal:
        """Latest traded (contract) price from ``/fapi/v1/ticker/price``."""
        payload = self._request("GET", "/fapi/v1/ticker/price", {"symbol": _normalize_symbol(symbol)})
        try:
            return Decimal(str(payload["price"]))
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise RuntimeError(f"Binance ticker/price for {symbol} did not include a usable price") from exc

    def klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        if interval not in KLINE_INTERVALS:
            raise ValueError(
                f"Unsupported Binance kline interval {interval!r}; valid: {', '.join(KLINE_INTERVALS)}"
            )
        rows = self._request(
            "GET",
            "/fapi/v1/klines",
            {
                "symbol": _normalize_symbol(symbol),
                "interval": interval,
                "limit": limit,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
            },
        )
        if not isinstance(rows, list):
            raise RuntimeError("Binance klines returned an unexpected payload")
        return [normalize_kline(row) for row in rows]

    # ---- signed read-only account data ---------------------------------------------

    def account(self) -> dict[str, Any]:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": _normalize_symbol(symbol)} if symbol else None
        return self._request("GET", "/fapi/v2/positionRisk", params, signed=True)

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": _normalize_symbol(symbol)} if symbol else None
        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    def open_algo_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Open conditional (algo) orders: STOP_MARKET, TRAILING_STOP_MARKET, and friends."""
        payload = self._request("GET", "/fapi/v1/algoOpenOrders", {"symbol": _normalize_symbol(symbol)}, signed=True)
        if isinstance(payload, dict):
            return list(payload.get("orders", []))
        return list(payload) if isinstance(payload, list) else []

    def algo_order_status(self, *, algo_id: int | None = None, client_algo_id: str | None = None) -> dict[str, Any]:
        if algo_id is None and not client_algo_id:
            raise ValueError("algo_order_status requires algo_id or client_algo_id")
        params: dict[str, Any] = {"clientAlgoId": client_algo_id} if client_algo_id else {"algoId": algo_id}
        return self._request("GET", "/fapi/v1/algoOrder", params, signed=True)

    def order_status(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        if order_id is None and not client_order_id:
            raise ValueError("order_status requires order_id or client_order_id")
        params: dict[str, Any] = {"symbol": _normalize_symbol(symbol)}
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            params["orderId"] = order_id
        return self._request("GET", "/fapi/v1/order", params, signed=True)

    # ---- user data stream listenKey --------------------------------------------------

    def create_listen_key(self) -> str:
        payload = self._request("POST", "/fapi/v1/listenKey", api_key_header=True)
        key = payload.get("listenKey") if isinstance(payload, dict) else None
        if not key:
            raise RuntimeError("Binance listenKey response did not include a listenKey")
        logger.info("binance_listen_key_created")
        return str(key)

    def keepalive_listen_key(self) -> None:
        self._request("PUT", "/fapi/v1/listenKey", api_key_header=True)
        logger.info("binance_listen_key_keepalive")

    def close_listen_key(self) -> None:
        self._request("DELETE", "/fapi/v1/listenKey", api_key_header=True)
        logger.info("binance_listen_key_closed")


def normalize_symbol_filters(entry: dict[str, Any]) -> dict[str, Any]:
    filters = {f.get("filterType"): f for f in entry.get("filters", []) if isinstance(f, dict)}
    price = filters.get("PRICE_FILTER", {})
    lot = filters.get("LOT_SIZE", {})
    market_lot = filters.get("MARKET_LOT_SIZE", {})
    notional = filters.get("MIN_NOTIONAL", {})
    return {
        "symbol": entry.get("symbol"),
        "status": entry.get("status"),
        "contract_type": entry.get("contractType"),
        "price_precision": int(entry.get("pricePrecision", 0)),
        "quantity_precision": int(entry.get("quantityPrecision", 0)),
        "tick_size": _decimal_or_none(price.get("tickSize")),
        "min_price": _decimal_or_none(price.get("minPrice")),
        "max_price": _decimal_or_none(price.get("maxPrice")),
        "step_size": _decimal_or_none(lot.get("stepSize")),
        "min_qty": _decimal_or_none(lot.get("minQty")),
        "max_qty": _decimal_or_none(lot.get("maxQty")),
        "market_max_qty": _decimal_or_none(market_lot.get("maxQty")),
        "min_notional": _decimal_or_none(notional.get("notional")),
        "order_types": list(entry.get("orderTypes", [])),
        "time_in_force": list(entry.get("timeInForce", [])),
    }


def normalize_kline(row: list[Any]) -> dict[str, Any]:
    if not isinstance(row, list) or len(row) < 7:
        raise RuntimeError("Binance kline row has an unexpected shape")
    return {
        "t": int(row[0]),
        "o": Decimal(str(row[1])),
        "h": Decimal(str(row[2])),
        "l": Decimal(str(row[3])),
        "c": Decimal(str(row[4])),
        "v": Decimal(str(row[5])),
        "T": int(row[6]),
        "quote_volume": Decimal(str(row[7])) if len(row) > 7 else None,
        "trades": int(row[8]) if len(row) > 8 else None,
    }


def _normalize_symbol(symbol: str | None) -> str:
    if not symbol or not symbol.strip():
        raise ValueError("symbol is required")
    return symbol.strip().upper()


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _parse_json(text: str) -> Any:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"msg": text}
