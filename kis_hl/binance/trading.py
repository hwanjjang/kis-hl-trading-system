from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal, InvalidOperation
from typing import Any

from kis_hl.binance.client import BinanceFuturesClient
from kis_hl.config import BinanceConfig
from kis_hl.execution_lock import account_lock

logger = logging.getLogger(__name__)

ORDER_PATH = "/fapi/v1/order"
ORDER_TEST_PATH = "/fapi/v1/order/test"
# Conditional orders (STOP_MARKET, TRAILING_STOP_MARKET, ...) moved to the Algo Order API on
# 2025-12-09; /fapi/v1/order rejects them with -4120.
ALGO_ORDER_PATH = "/fapi/v1/algoOrder"
POSITION_MODE_PATH = "/fapi/v1/positionSide/dual"
# Order/algo states that mean nothing is (or will be) working on the exchange.
TERMINAL_FAILED_STATES = frozenset({"REJECTED", "CANCELED", "CANCELLED", "EXPIRED", "EXPIRED_IN_MATCH"})
# Algo states in which the exchange still holds the conditional order.
ACTIVE_ALGO_STATES = frozenset({"NEW", "TRIGGERING", "TRIGGERED"})
# States that confirm a cancel took effect.
CANCELED_STATES = frozenset({"CANCELED", "CANCELLED"})
# Outcomes Binance documents as "may have executed": 5xx, HTTP 408, code -1007 (timeout waiting for
# the backend, execution status unknown), and the generic "Unknown error" wording.
# The message format is "Binance request failed: HTTP <status> <code>/<msg>", so the code is
# matched as " -1007/" (no word boundary: space and '-' are both non-word characters).
UNKNOWN_OUTCOME_RE = re.compile(r"HTTP (?:5\d\d|408)\b|\s-1007/|Unknown error|status unknown", re.IGNORECASE)

SUPPORTED_LIVE_SYMBOLS = frozenset({"BTCUSDT"})
SIDES = ("BUY", "SELL")
ENTRY_TYPES = ("MARKET", "LIMIT")
TIME_IN_FORCE = ("GTC", "IOC", "FOK", "GTX")
WORKING_TYPES = ("MARK_PRICE", "CONTRACT_PRICE")
CLIENT_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,36}$")
CALLBACK_RATE_MIN = Decimal("0.1")
CALLBACK_RATE_MAX = Decimal("10")


def round_to_step(value: Decimal, step: Decimal, *, rounding: str = ROUND_DOWN) -> Decimal:
    """Quantize ``value`` to a multiple of ``step`` (tick or lot size)."""
    if step is None or step <= 0:
        raise ValueError("step must be a positive Decimal")
    units = (value / step).to_integral_value(rounding=rounding)
    return (units * step).quantize(step)


@dataclass(frozen=True, slots=True)
class BinanceOrderSubmission:
    status: str  # dry_run | exchange_test | submitted | rejected
    dry_run: bool
    symbol: str
    request: dict[str, Any]
    response: Any


def submission_to_dict(submission: BinanceOrderSubmission) -> dict[str, Any]:
    return {
        "status": submission.status,
        "dry_run": submission.dry_run,
        "symbol": submission.symbol,
        "request": submission.request,
        "response": submission.response,
        "submitted_at_ms": int(time.time() * 1000),
    }


def extract_binance_order_id(response: Any) -> str | None:
    """Order id for regular orders, algo id for conditional orders."""
    if isinstance(response, dict):
        for key in ("orderId", "algoId"):
            if response.get(key) is not None:
                return str(response[key])
    return None


class BinanceTradingClient(BinanceFuturesClient):
    """Guarded USD(S)-M futures order placement.

    Every order method validates and rounds against exchange filters first, returns a
    dry-run submission by default without any signed call, and only with ``dry_run=False``
    walks the live guard chain: symbol allowlist -> credentials -> one-way position mode ->
    account lock -> signed request. ``exchange_test=True`` sends the same parameters to
    ``/fapi/v1/order/test``, which validates on the exchange without placing an order.
    """

    # ---- public order methods -------------------------------------------------------------

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        tif: str = "GTC",
        reduce_only: bool = False,
        client_order_id: str | None = None,
        dry_run: bool = True,
        exchange_test: bool = False,
        filters: dict[str, Any] | None = None,
        mark_price: Decimal | None = None,
    ) -> BinanceOrderSubmission:
        symbol = _symbol(symbol)
        side = _choice(side, SIDES, "side")
        order_type = _choice(order_type, ENTRY_TYPES, "order_type")
        tif = _choice(tif, TIME_IN_FORCE, "tif")
        quantity = _positive(quantity, "quantity")
        if order_type == "LIMIT" and price is None:
            raise ValueError("LIMIT orders require price")
        if order_type == "MARKET" and price is not None:
            raise ValueError("MARKET orders must not set price")
        if order_type == "MARKET" and tif != "GTC":
            raise ValueError("MARKET orders must not set time-in-force")
        client_order_id = _client_order_id(client_order_id)

        rules = filters or self.symbol_filters(symbol)
        qty = _round_quantity(quantity, rules, market=order_type == "MARKET")
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": _text(qty),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "RESULT",
        }
        if order_type == "LIMIT":
            limit_price = _round_price(_positive(price, "price"), rules, side=side)
            if not reduce_only:  # Binance exempts reduce-only exits from MIN_NOTIONAL.
                _require_notional(qty, limit_price, rules)
            params["price"] = _text(limit_price)
            params["timeInForce"] = tif
        elif not reduce_only:
            mark = mark_price if mark_price is not None else self._mark_price(symbol)
            _require_notional(qty, mark, rules)
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._submit(ORDER_PATH, params, symbol=symbol, dry_run=dry_run, exchange_test=exchange_test)

    def place_stop_market(
        self,
        *,
        symbol: str,
        side: str,
        stop_price: Decimal,
        quantity: Decimal | None = None,
        close_position: bool = True,
        working_type: str = "MARK_PRICE",
        client_order_id: str | None = None,
        dry_run: bool = True,
        exchange_test: bool = False,
        filters: dict[str, Any] | None = None,
        mark_price: Decimal | None = None,
    ) -> BinanceOrderSubmission:
        symbol = _symbol(symbol)
        side = _choice(side, SIDES, "side")
        working_type = _choice(working_type, WORKING_TYPES, "working_type")
        stop_price = _positive(stop_price, "stop_price")
        client_order_id = _client_order_id(client_order_id)
        if not close_position and quantity is None:
            raise ValueError("reduce-only STOP_MARKET requires quantity; use close_position=True to close the whole position")
        if close_position and quantity is not None:
            raise ValueError("close_position=True closes the whole position; do not pass quantity (use close_position=False for a sized reduce-only stop)")

        rules = filters or self.symbol_filters(symbol)
        reference = self._reference_price(symbol, working_type, mark_price)
        rounded_stop = _round_price(stop_price, rules, side=side)
        _require_stop_direction(side, rounded_stop, reference, working_type)
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "triggerPrice": _text(rounded_stop),
            "workingType": working_type,
            "clientAlgoId": client_order_id,
            "newOrderRespType": "RESULT",
        }
        if close_position:
            params["closePosition"] = "true"
        else:
            qty = _round_quantity(_positive(quantity, "quantity"), rules, market=True)
            params["quantity"] = _text(qty)
            params["reduceOnly"] = "true"
        return self._submit(ALGO_ORDER_PATH, params, symbol=symbol, dry_run=dry_run, exchange_test=exchange_test)

    def place_trailing_stop(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        callback_rate: Decimal,
        activation_price: Decimal | None = None,
        working_type: str = "MARK_PRICE",
        client_order_id: str | None = None,
        dry_run: bool = True,
        exchange_test: bool = False,
        filters: dict[str, Any] | None = None,
        mark_price: Decimal | None = None,
    ) -> BinanceOrderSubmission:
        symbol = _symbol(symbol)
        side = _choice(side, SIDES, "side")
        working_type = _choice(working_type, WORKING_TYPES, "working_type")
        quantity = _positive(quantity, "quantity")
        callback_rate = _callback_rate(callback_rate)
        client_order_id = _client_order_id(client_order_id)

        rules = filters or self.symbol_filters(symbol)
        qty = _round_quantity(quantity, rules, market=True)
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": "TRAILING_STOP_MARKET",
            "quantity": _text(qty),
            "callbackRate": _text(callback_rate),
            "reduceOnly": "true",
            "workingType": working_type,
            "clientAlgoId": client_order_id,
            "newOrderRespType": "RESULT",
        }
        if activation_price is not None:
            reference = self._reference_price(symbol, working_type, mark_price)
            activation = _round_price(_positive(activation_price, "activation_price"), rules, side=side)
            _require_activation_direction(side, activation, reference, working_type)
            params["activatePrice"] = _text(activation)
        return self._submit(ALGO_ORDER_PATH, params, symbol=symbol, dry_run=dry_run, exchange_test=exchange_test)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
        dry_run: bool = True,
    ) -> BinanceOrderSubmission:
        symbol = _symbol(symbol)
        if (order_id is None) == (not client_order_id):
            raise ValueError("cancel_order requires exactly one of order_id or client_order_id")
        params: dict[str, Any] = {"symbol": symbol}
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            params["orderId"] = int(order_id)  # type: ignore[arg-type]
        return self._submit(ORDER_PATH, params, symbol=symbol, dry_run=dry_run, exchange_test=False, method="DELETE")

    def cancel_algo_order(
        self,
        *,
        symbol: str,
        algo_id: int | None = None,
        client_algo_id: str | None = None,
        dry_run: bool = True,
    ) -> BinanceOrderSubmission:
        """Cancel a conditional (algo) order; the endpoint identifies it by algoId or clientAlgoId."""
        symbol = _symbol(symbol)
        if (algo_id is None) == (not client_algo_id):
            raise ValueError("cancel_algo_order requires exactly one of algo_id or client_algo_id")
        params: dict[str, Any] = {"clientAlgoId": client_algo_id} if client_algo_id else {"algoId": int(algo_id)}  # type: ignore[arg-type]
        if not dry_run:
            # The delete request carries no symbol, so the allowlist can only be enforced against the
            # order the id actually points to. Fail closed when it cannot be looked up.
            self._require_live_symbol(symbol)
            self._require_credentials(need_secret=True)
            try:
                current = self.algo_order_status(algo_id=algo_id, client_algo_id=client_algo_id)
            except Exception as exc:  # noqa: BLE001 - any lookup failure blocks the cancel
                raise RuntimeError(f"Binance algo order lookup failed; refusing to cancel blindly: {exc}") from exc
            actual = str(current.get("symbol", "")).upper() if isinstance(current, dict) else ""
            if actual != symbol:
                raise RuntimeError(f"Binance algo order belongs to {actual or 'an unknown symbol'}, not {symbol}; refusing to cancel")
        return self._submit(ALGO_ORDER_PATH, params, symbol=symbol, dry_run=dry_run, exchange_test=False, method="DELETE")

    def position_mode_is_hedge(self) -> bool:
        """Return True for hedge (dual-side) mode; fail closed when the answer is not explicit."""
        payload = self._request("GET", POSITION_MODE_PATH, signed=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("dualSidePosition"), bool):
            raise RuntimeError("Binance position mode could not be determined; refusing to place a live order")
        return payload["dualSidePosition"]

    # ---- guard chain ----------------------------------------------------------------------

    def _submit(
        self,
        path: str,
        params: dict[str, Any],
        *,
        symbol: str,
        dry_run: bool,
        exchange_test: bool,
        method: str = "POST",
    ) -> BinanceOrderSubmission:
        request = {
            "path": path,
            "method": method,
            "symbol": symbol,
            "params": params,
            "client_request_id": uuid.uuid4().hex,
            "base_url": self.config.base_url,
            "key_profile": self.config.key_profile,
        }
        if exchange_test:
            if method != "POST" or path != ORDER_PATH:
                raise ValueError("exchange_test is only available for regular order placement; the Algo Order API has no test endpoint")
            self._require_credentials(need_secret=True)
            try:
                response = self._request("POST", ORDER_TEST_PATH, params, signed=True)
            except RuntimeError as exc:
                logger.warning("binance_order_exchange_test_rejected", extra={"symbol": symbol, "error": str(exc)})
                return BinanceOrderSubmission("rejected", True, symbol, request, {"error": str(exc)})
            logger.info("binance_order_exchange_test", extra={"symbol": symbol, "type": params.get("type")})
            return BinanceOrderSubmission("exchange_test", True, symbol, request, response)
        if dry_run:
            logger.info("binance_order_dry_run", extra={"symbol": symbol, "type": params.get("type"), "method": method})
            return BinanceOrderSubmission("dry_run", True, symbol, request, {"skipped": "dry_run"})

        self._require_live_symbol(symbol)
        self._require_credentials(need_secret=True)
        if method == "POST":
            metadata = self.symbol_filters(symbol)
            if (metadata.get("symbol") != symbol or metadata.get("status") != "TRADING"
                    or metadata.get("contract_type") != "PERPETUAL" or metadata.get("underlying_type") != "COIN"):
                raise RuntimeError("Binance metadata must confirm a trading COIN perpetual before live placement")
        if method == "POST" and self.position_mode_is_hedge():
            raise RuntimeError("Binance account is in hedge (dual-side) position mode; live orders require one-way mode")
        with account_lock(self.config.base_url, self.config.api_key):
            if method == "POST" and path == ALGO_ORDER_PATH:
                positions = self.position_risk(symbol)
                matches = [p for p in positions if p.get("symbol") == symbol and p.get("positionSide") == "BOTH"] if isinstance(positions, list) else []
                amount = _optional_decimal(matches[0].get("positionAmt")) if len(matches) == 1 else None
                if amount is None or not amount.is_finite() or amount == 0 or (amount > 0) != (params["side"] == "SELL"):
                    raise RuntimeError("Protective order requires a matching nonzero one-way position")
                if "quantity" in params and Decimal(params["quantity"]) != abs(amount):
                    raise RuntimeError("Protective order quantity must match full position coverage")
                request["verified_position_amount"] = str(amount)
            try:
                response = self._request(method, path, params, signed=True)
            except RuntimeError as exc:
                if not UNKNOWN_OUTCOME_RE.search(str(exc)):
                    logger.warning("binance_order_rejected", extra={"symbol": symbol, "type": params.get("type"), "error": str(exc)})
                    return BinanceOrderSubmission("rejected", False, symbol, request, {"error": str(exc)})
                return self._resolve_unknown(path, params, request, symbol, str(exc))
            except Exception as exc:  # transport failure after the request may have been sent
                return self._resolve_unknown(path, params, request, symbol, f"{type(exc).__name__}: {exc}")
        logger.info(
            "binance_order_submitted",
            extra={"symbol": symbol, "type": params.get("type"), "order_id": extract_binance_order_id(response)},
        )
        status = "submitted"
        if method == "POST" and isinstance(response, dict):
            state = str(response.get("algoStatus") or response.get("status") or "").upper()
            executed = _optional_decimal(response.get("executedQty"))
            if state in TERMINAL_FAILED_STATES and not (executed is not None and executed > 0):
                status = "rejected"
        return BinanceOrderSubmission(status, False, symbol, request, response)

    def _resolve_unknown(
        self,
        path: str,
        params: dict[str, Any],
        request: dict[str, Any],
        symbol: str,
        error: str,
    ) -> BinanceOrderSubmission:
        """A 5xx/"Unknown error"/transport failure may have executed: look the order up before giving up.

        Regular orders are queried by ``newClientOrderId`` and algo orders by ``clientAlgoId``.
        A found order is reported as ``submitted`` (with ``request["outcome"]`` set); otherwise
        the submission stays ``unknown`` and must not be retried with a new client id blindly.
        """
        logger.warning("binance_order_outcome_unknown", extra={"symbol": symbol, "type": params.get("type"), "error": error})
        lookup: dict[str, Any] | None = None
        try:
            if path == ORDER_PATH and (params.get("newClientOrderId") or params.get("origClientOrderId")):
                lookup = self.order_status(symbol, client_order_id=str(params.get("newClientOrderId") or params.get("origClientOrderId")))
            elif path == ORDER_PATH and params.get("orderId") is not None:
                lookup = self.order_status(symbol, order_id=int(params["orderId"]))
            elif path == ALGO_ORDER_PATH and params.get("clientAlgoId"):
                lookup = self.algo_order_status(client_algo_id=str(params["clientAlgoId"]))
            elif path == ALGO_ORDER_PATH and params.get("algoId") is not None:
                lookup = self.algo_order_status(algo_id=int(params["algoId"]))
        except Exception as exc:  # noqa: BLE001 - reconciliation is best effort
            logger.warning("binance_order_reconcile_failed", extra={"symbol": symbol, "error": str(exc)})
            lookup = None
        if request["method"] == "DELETE" and isinstance(lookup, dict):
            state = str(lookup.get("algoStatus") or lookup.get("status") or "").upper()
            if state in CANCELED_STATES:
                request["outcome"] = "reconciled_cancel"
                logger.info("binance_cancel_reconciled", extra={"symbol": symbol, "state": state})
                return BinanceOrderSubmission("submitted", False, symbol, request, lookup)
        if request["method"] == "POST" and isinstance(lookup, dict) and extract_binance_order_id(lookup):
            state = str(lookup.get("algoStatus") or lookup.get("status") or "").upper()
            executed = _optional_decimal(lookup.get("executedQty"))
            if state in TERMINAL_FAILED_STATES and executed is not None and executed > 0:
                # e.g. an IOC that partially filled and then expired: a position exists.
                request["outcome"] = "reconciled_partial_fill"
                logger.warning("binance_order_reconciled_partial_fill", extra={"symbol": symbol, "state": state, "executed_qty": str(executed)})
                return BinanceOrderSubmission("submitted", False, symbol, request, lookup)
            if state in TERMINAL_FAILED_STATES:
                request["outcome"] = "reconciled_terminal"
                logger.warning("binance_order_reconciled_terminal", extra={"symbol": symbol, "state": state})
                return BinanceOrderSubmission("rejected", False, symbol, request, lookup)
            request["outcome"] = "reconciled_after_unknown"
            logger.info("binance_order_reconciled", extra={"symbol": symbol, "order_id": extract_binance_order_id(lookup), "state": state})
            return BinanceOrderSubmission("submitted", False, symbol, request, lookup)
        return BinanceOrderSubmission("unknown", False, symbol, request, {"error": error, "lookup": lookup})

    def _reference_price(self, symbol: str, working_type: str, mark_price: Decimal | None) -> Decimal:
        """Price the exchange will compare a trigger against: mark price or last (contract) price."""
        if working_type == "CONTRACT_PRICE":
            return self.last_price(symbol)
        return mark_price if mark_price is not None else self._mark_price(symbol)

    def _require_live_symbol(self, symbol: str) -> None:
        if symbol not in SUPPORTED_LIVE_SYMBOLS:
            raise RuntimeError(f"Live Binance symbol {symbol} is not supported by BINANCE_LIVE_SYMBOLS; supported symbols: {sorted(SUPPORTED_LIVE_SYMBOLS)}")
        if symbol not in self.config.live_symbols:
            raise RuntimeError(
                f"Live Binance orders are limited to BINANCE_LIVE_SYMBOLS {list(self.config.live_symbols)}; got {symbol}"
            )

    def _mark_price(self, symbol: str) -> Decimal:
        payload = self.premium_index(symbol)
        try:
            return Decimal(str(payload["markPrice"]))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise RuntimeError(f"Binance premiumIndex for {symbol} did not include a usable markPrice") from exc


# ---- validation helpers ---------------------------------------------------------------------


def _symbol(symbol: str) -> str:
    if not symbol or not symbol.strip():
        raise ValueError("symbol is required")
    return symbol.strip().upper()


def _choice(value: str, allowed: tuple[str, ...], name: str) -> str:
    upper = str(value).strip().upper()
    if upper not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return upper


def _positive(value: Decimal | None, name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return decimal_value


def _client_order_id(value: str | None) -> str:
    if value is None or value == "":
        return "kh" + uuid.uuid4().hex[:30]
    if not CLIENT_ORDER_ID_RE.fullmatch(value):
        raise ValueError("client_order_id must match ^[A-Za-z0-9._:/-]{1,36}$")
    return value


def _callback_rate(value: Decimal) -> Decimal:
    rate = _positive(value, "callback_rate")
    if rate < CALLBACK_RATE_MIN or rate > CALLBACK_RATE_MAX:
        raise ValueError("callback_rate must be between 0.1 and 10 (percent)")
    if rate != rate.quantize(Decimal("0.1")):
        raise ValueError("callback_rate supports at most one decimal place")
    return rate.quantize(Decimal("0.1"))


def _round_quantity(quantity: Decimal, rules: dict[str, Any], *, market: bool) -> Decimal:
    step = rules.get("step_size")
    qty = round_to_step(quantity, step) if step else quantity
    min_qty = rules.get("min_qty")
    if min_qty is not None and qty < min_qty:
        raise ValueError(f"quantity {qty} is below minQty {min_qty} after rounding to step {step}")
    max_qty = rules.get("market_max_qty") if market and rules.get("market_max_qty") is not None else rules.get("max_qty")
    if max_qty is not None and qty > max_qty:
        raise ValueError(f"quantity {qty} exceeds maxQty {max_qty}")
    return qty


def _round_price(price: Decimal, rules: dict[str, Any], *, side: str) -> Decimal:
    """Round to tick so a BUY price moves down and a SELL price moves up.

    For entries this never makes the order more aggressive than requested. For stops the
    same rule makes a SELL stop (protecting a long) trigger slightly earlier and a BUY stop
    (protecting a short) trigger slightly earlier, which is the conservative direction.
    """
    tick = rules.get("tick_size")
    rounded = round_to_step(price, tick, rounding=ROUND_DOWN if side == "BUY" else ROUND_UP) if tick else price
    for key, violates in (("min_price", lambda bound: rounded < bound), ("max_price", lambda bound: rounded > bound)):
        bound = rules.get(key)
        if bound is not None and bound > 0 and violates(bound):
            raise ValueError(f"price {rounded} violates {key} {bound}")
    return rounded


def _require_notional(qty: Decimal, price: Decimal, rules: dict[str, Any]) -> None:
    min_notional = rules.get("min_notional")
    if min_notional is None:
        return
    notional = qty * price
    if notional < min_notional:
        raise ValueError(f"notional {notional} is below MIN_NOTIONAL {min_notional} (quantity {qty} x price {price})")


def _require_stop_direction(side: str, stop_price: Decimal, reference: Decimal, working_type: str) -> None:
    label = "mark price" if working_type == "MARK_PRICE" else "last price"
    if side == "SELL" and stop_price >= reference:
        raise ValueError(f"SELL stop {stop_price} must be below the {label} {reference}; it would trigger immediately")
    if side == "BUY" and stop_price <= reference:
        raise ValueError(f"BUY stop {stop_price} must be above the {label} {reference}; it would trigger immediately")


def _require_activation_direction(side: str, activation: Decimal, reference: Decimal, working_type: str) -> None:
    # Binance: SELL trailing stops need activatePrice above the current price, BUY below.
    label = "mark price" if working_type == "MARK_PRICE" else "last price"
    if side == "SELL" and activation <= reference:
        raise ValueError(f"SELL trailing activation {activation} must be above the {label} {reference}")
    if side == "BUY" and activation >= reference:
        raise ValueError(f"BUY trailing activation {activation} must be below the {label} {reference}")


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _text(value: Decimal) -> str:
    return format(value, "f")
