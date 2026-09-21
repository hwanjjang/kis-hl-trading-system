from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from kis_hl.assets import ResolvedAsset, resolve_hyperliquid_symbol
from kis_hl.config import HyperliquidConfig
from kis_hl.logging_utils import get_logger
from kis_hl.execution_lock import serialized_action
from kis_hl.trailing_storage import has_managed_position
from kis_hl.storage import has_recent_successful_trade_xyz_check
from kis_hl.trade_xyz_assets import is_trade_xyz_symbol_tradable, normalize_trade_symbol
from kis_hl.trading_hours import trading_session_decision_for_resolved_asset

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OrderSubmission:
    status: str
    dry_run: bool
    resolved: ResolvedAsset
    request: dict[str, Any]
    response: Any


class HyperliquidInfoClient:
    def __init__(self, config: HyperliquidConfig, *, timeout_seconds: float = 10) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def post_info(self, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/info",
            data=body,
            method="POST",
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as res:
                text = res.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8")
            try:
                payload = json.loads(text) if text else {}
            except json.JSONDecodeError:
                payload = {"raw": text}
            raise RuntimeError(f"Hyperliquid info request failed: HTTP {exc.code} {payload}") from exc

    def all_mids(self, *, dex: str | None = None) -> dict[str, str]:
        payload: dict[str, Any] = {"type": "allMids"}
        if dex:
            payload["dex"] = dex
        result = self.post_info(payload)
        if not isinstance(result, dict):
            raise RuntimeError("Hyperliquid allMids returned a non-object response")
        return {str(key): str(value) for key, value in result.items()}

    def spot_meta(self) -> dict[str, Any]:
        result = self.post_info({"type": "spotMeta"})
        if not isinstance(result, dict):
            raise RuntimeError("Hyperliquid spotMeta returned a non-object response")
        return result

    def meta_and_asset_ctxs(self, *, dex: str | None = None) -> list[Any]:
        payload: dict[str, Any] = {"type": "metaAndAssetCtxs"}
        if dex:
            payload["dex"] = dex
        result = self.post_info(payload)
        if not isinstance(result, list) or len(result) < 2:
            raise RuntimeError("Hyperliquid metaAndAssetCtxs returned an unexpected response")
        return result

    def l2_book(self, symbol: str, *, dex: str | None = None) -> Any:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        return self.post_info({"type": "l2Book", "coin": resolved.coin})

    def candle_snapshot(
        self,
        symbol: str,
        *,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        dex: str | None = None,
    ) -> Any:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        return self.post_info(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": resolved.coin,
                    "interval": interval,
                    "startTime": start_time_ms,
                    "endTime": end_time_ms,
                },
            }
        )

    def funding_history(
        self,
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
        dex: str | None = None,
    ) -> list[dict[str, Any]]:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        result = self.post_info(
            {
                "type": "fundingHistory",
                "coin": resolved.coin,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
            }
        )
        if not isinstance(result, list):
            raise RuntimeError("Hyperliquid fundingHistory returned a non-list response")
        return [item for item in result if isinstance(item, dict)]

    def clearinghouse_state(self, *, user: str | None = None, dex: str | None = None) -> Any:
        payload = {"type": "clearinghouseState", "user": self._resolve_user(user)}
        if dex:
            payload["dex"] = dex
        return self.post_info(payload)

    def frontend_open_orders(self, *, user: str | None = None, dex: str | None = None) -> list[dict[str, Any]]:
        payload = {"type": "frontendOpenOrders", "user": self._resolve_user(user)}
        if dex:
            payload["dex"] = dex
        return self._object_list(payload)

    def user_fills_by_time(self, *, start_time_ms: int, end_time_ms: int,
                           user: str | None = None) -> list[dict[str, Any]]:
        return self._object_list({"type": "userFillsByTime", "user": self._resolve_user(user),
                                  "startTime": start_time_ms, "endTime": end_time_ms,
                                  "aggregateByTime": False})

    def user_fills(self, *, user: str | None = None) -> list[dict[str, Any]]:
        return self._object_list({"type":"userFills", "user":self._resolve_user(user),
                                  "aggregateByTime":False})

    def user_funding(self, *, start_time_ms: int, end_time_ms: int,
                     user: str | None = None) -> list[dict[str, Any]]:
        return self._object_list({"type": "userFunding", "user": self._resolve_user(user),
                                  "startTime": start_time_ms, "endTime": end_time_ms})

    def order_status(self, *, oid: int | str, user: str | None = None) -> dict[str, Any]:
        result = self.post_info({"type": "orderStatus", "user": self._resolve_user(user), "oid": oid})
        if not isinstance(result, dict) or result.get("status") not in {"order", "unknownOid"}:
            raise RuntimeError("Hyperliquid orderStatus returned an unexpected response")
        return result

    def _object_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = self.post_info(payload)
        if not isinstance(result, list) or any(not isinstance(x, dict) for x in result):
            raise RuntimeError(f"Hyperliquid {payload['type']} returned an unexpected response")
        return result

    def spot_clearinghouse_state(self, *, user: str | None = None) -> Any:
        return self.post_info({"type": "spotClearinghouseState", "user": self._resolve_user(user)})

    def all_dexs_clearinghouse_state(self, *, user: str | None = None) -> Any:
        return self.post_info(
            {
                "type": "clearinghouseState",
                "user": self._resolve_user(user),
                "dex": "ALL_DEXES",
            }
        )

    def account_asset_info(
        self,
        *,
        user: str | None = None,
        include_spot: bool = True,
        include_all_dexs: bool = False,
        dexes: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        resolved_user = self._resolve_user(user)
        result: dict[str, Any] = {
            "user": resolved_user,
            "perp": self.clearinghouse_state(user=resolved_user),
        }
        if include_spot:
            result["spot"] = self.spot_clearinghouse_state(user=resolved_user)
        if include_all_dexs:
            result["all_dexs"] = self.all_dexs_clearinghouse_state(user=resolved_user)
        if dexes:
            result["dexes"] = {
                dex: self.clearinghouse_state(user=resolved_user, dex=dex)
                for dex in dexes
            }
        return result

    def _resolve_user(self, user: str | None) -> str:
        resolved = (user or self.config.account_address).strip()
        if not resolved:
            raise RuntimeError("Hyperliquid wallet address is required")
        return resolved


class HyperliquidTradingClient:
    def __init__(
        self,
        config: HyperliquidConfig,
        *,
        verification_db_path: str | Path | None = None,
        verification_max_age_hours: int = 24,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.verification_db_path = verification_db_path
        self.verification_max_age_ms = verification_max_age_hours * 60 * 60 * 1000
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sdk: tuple[Any, Any] | None = None

    @serialized_action
    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        size: Decimal,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        tpsl: str = "sl",
        reduce_only: bool = False,
        tif: str = "Gtc",
        slippage: Decimal = Decimal("0.05"),
        dex: str | None = None,
        dry_run: bool = True,
        allow_outside_session: bool = False,
        cloid: str | None = None,
        expires_after_ms: int | None = None,
    ) -> OrderSubmission:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        normalized_side = side.lower()
        normalized_type = order_type.lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if normalized_type not in {"limit", "market", "stop-market"}:
            raise ValueError("order_type must be limit, market, or stop-market")
        normalized_tpsl = tpsl.lower()
        if normalized_tpsl not in {"tp", "sl"}:
            raise ValueError("tpsl must be tp or sl")
        if not size.is_finite() or size <= 0:
            raise ValueError("size must be positive")
        if normalized_type == "limit" and (price is None or price <= 0):
            raise ValueError("limit orders require a positive price")
        if normalized_type == "stop-market":
            if trigger_price is None or trigger_price <= 0:
                raise ValueError("stop-market orders require a positive trigger_price")
            if not reduce_only:
                raise ValueError("stop-market stop-loss orders require reduce_only=True")
        if not slippage.is_finite() or not Decimal("0") < slippage < Decimal("1"):
            raise ValueError("slippage must be between zero and one")
        if normalized_type == "market" and reduce_only and resolved.kind != "perp":
            raise ValueError("reduce-only market exits require a perpetual position")
        if cloid is not None:
            import re
            if not re.fullmatch(r"0x[0-9a-fA-F]{32}", cloid):
                raise ValueError("cloid must be a 128-bit hex string")
        if expires_after_ms is not None and (not isinstance(expires_after_ms, int)
                                             or isinstance(expires_after_ms, bool) or expires_after_ms <= 0):
            raise ValueError("expires_after_ms must be a positive integer timestamp")
        execution_price = price if price is not None else trigger_price

        request = {
            "client_request_id": uuid4().hex,
            "cloid": cloid,
            "expires_after_ms": expires_after_ms,
            "symbol": symbol,
            "resolved_coin": resolved.coin,
            "order_coin": resolved.coin,
            "kind": resolved.kind,
            "side": normalized_side,
            "order_type": normalized_type,
            "size": str(size),
            "price": str(execution_price) if execution_price is not None else None,
            "trigger_price": str(trigger_price) if trigger_price is not None else None,
            "trigger_is_market": normalized_type == "stop-market",
            "tpsl": normalized_tpsl if normalized_type == "stop-market" else None,
            "reduce_only": reduce_only,
            "tif": tif,
            "base_url": self.config.base_url,
            "key_profile": self.config.key_profile,
            "allow_outside_session": allow_outside_session,
        }
        if dry_run:
            logger.info("hyperliquid_order_dry_run", extra={"resolved_coin": resolved.coin})
            return OrderSubmission("dry_run", True, resolved, request, {"skipped": "dry_run"})
        if not is_supported_live_asset(resolved):
            raise RuntimeError(
                "Live trading is limited to BTCUSDC spot, BTC/ETH perps and mapped tradable trade.xyz assets; "
                f"got {symbol}"
            )
        self._require_recent_verification(resolved)

        self._require_credentials()
        if not reduce_only:
            from kis_hl.journal_sync import Scope
            from kis_hl.managed_execution import guard_external_entry
            scope=Scope('hyperliquid','testnet' if 'testnet' in self.config.base_url else 'mainnet',self.config.account_address)
            guard_external_entry(self.verification_db_path,scope=scope.key,instrument_id='hl:'+resolved.coin,attempt_id=cloid)
            if has_managed_position(self.verification_db_path, network=self.config.base_url,
                                    account=self.config.account_address, coin=resolved.coin):
                raise RuntimeError("Managed trailing position blocks entries until cleanup completes")
            session_decision = trading_session_decision_for_resolved_asset(
                resolved,
                now=self._now(),
            )
            request["session"] = asdict(session_decision)
            logger.info(
                "hyperliquid_session_decision",
                extra={
                    "resolved_coin": resolved.coin,
                    "session_group": session_decision.session_group,
                    "allowed": session_decision.allowed,
                    "reason": session_decision.reason,
                    "allow_outside_session": allow_outside_session,
                },
            )
            if not session_decision.allowed and not allow_outside_session:
                raise RuntimeError(
                    "Underlying market session is closed for "
                    f"{resolved.coin}: {session_decision.reason}"
                )
        _info, exchange = self._load_sdk()
        order_coin = self._resolve_live_order_coin(resolved)
        request["order_coin"] = order_coin
        is_buy = normalized_side == "buy"
        order_kwargs = {"cloid": sdk_cloid(cloid)} if cloid else {}
        if expires_after_ms is not None:
            if int(time.time()*1000) >= expires_after_ms:
                raise TimeoutError("Order price expired before submission")
            exchange.set_expires_after(expires_after_ms)
        try:
            if normalized_type == "market":
                if reduce_only:
                    # market_open hardcodes reduce_only=False in the SDK.
                    public = HyperliquidInfoClient(self.config)
                    positions = public.clearinghouse_state(dex=resolved.dex)["assetPositions"]
                    current = next((Decimal(p["position"]["szi"]) for p in positions
                                    if p["position"]["coin"] == resolved.coin), Decimal(0))
                    if not current.is_finite() or current == 0 or (current > 0) == is_buy:
                        raise ValueError("Requested side cannot reduce the current position")
                    mid = Decimal(public.all_mids(dex=resolved.dex)[resolved.coin])
                    meta = public.meta_and_asset_ctxs(dex=resolved.dex)[0]["universe"]
                    decimals = int(next(m["szDecimals"] for m in meta if m["name"] == resolved.coin))
                    limit, quantity = prepare_perp_exit(price=mid, size=min(size, abs(current)),
                                                        sz_decimals=decimals, slippage=slippage,
                                                        is_buy=is_buy)
                    request.update(price=str(limit), size=str(quantity), tif="Ioc")
                    # Keep the requested side fixed even if another actor changes
                    # the position after our snapshot; exchange reduce-only wins.
                    response = exchange.order(order_coin, is_buy, float(quantity), float(limit),
                                              {"limit": {"tif": "Ioc"}}, True, **order_kwargs)
                else:
                    response = exchange.market_open(order_coin, is_buy, float(size), None,
                                                    float(slippage), **order_kwargs)
            else:
                if normalized_type == "stop-market":
                    order_payload = {
                        "trigger": {
                            "isMarket": True,
                            "triggerPx": _decimal_to_api_string(trigger_price),
                            "tpsl": normalized_tpsl,
                        }
                    }
                else:
                    order_payload = {"limit": {"tif": tif}}
                response = exchange.order(
                    order_coin,
                    is_buy,
                    float(size),
                    float(execution_price),
                    order_payload,
                    reduce_only,
                    **order_kwargs,
                )
        except Exception as exc:
            logger.error(
                "hyperliquid_order_failed",
                extra={"resolved_coin": resolved.coin, "order_coin": order_coin, "error": str(exc)},
            )
            raise
        finally:
            if expires_after_ms is not None:
                exchange.set_expires_after(None)
        statuses = response.get("response", {}).get("data", {}).get("statuses", []) if isinstance(response, dict) else []
        rejected = (isinstance(response, dict) and response.get("status") == "err") or any(
            isinstance(item, dict) and "error" in item for item in statuses)
        status = "rejected" if rejected else "submitted"
        logger.info("hyperliquid_order_result", extra={"resolved_coin": resolved.coin, "status": status,
                                                     "client_request_id": request["client_request_id"], "cloid": cloid})
        return OrderSubmission(status, False, resolved, request, response)

    def place_stop_loss_order(
        self,
        *,
        symbol: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        price: Decimal | None = None,
        dex: str | None = None,
        dry_run: bool = True,
    ) -> OrderSubmission:
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type="stop-market",
            size=size,
            price=price,
            trigger_price=trigger_price,
            tpsl="sl",
            reduce_only=True,
            dex=dex,
            dry_run=dry_run,
        )

    @serialized_action
    def cancel_order(self, *, symbol: str, oid: int, dex: str | None = None,
                     dry_run: bool = True) -> OrderSubmission:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        if not isinstance(oid, int) or isinstance(oid, bool) or oid <= 0:
            raise ValueError("oid must be a positive integer")
        request = {"resolved_coin": resolved.coin, "oid": oid, "action": "cancel"}
        if dry_run:
            return OrderSubmission("dry_run", True, resolved, request, {"skipped": "dry_run"})
        if not is_supported_live_asset(resolved):
            raise RuntimeError("Unsupported live asset")
        self._require_recent_verification(resolved)
        self._require_credentials()
        _, exchange = self._load_sdk()
        try:
            response = exchange.cancel(self._resolve_live_order_coin(resolved), oid)
        except Exception:
            logger.exception("hyperliquid_cancel_unknown", extra=request)
            raise
        logger.info("hyperliquid_cancel_submitted", extra=request)
        return OrderSubmission("submitted", False, resolved, request, response)

    def user_state(self) -> Any:
        self._require_credentials()
        info, _exchange = self._load_sdk()
        return info.user_state(self.config.account_address)

    def _load_sdk(self) -> tuple[Any, Any]:
        if self._sdk:
            return self._sdk
        try:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            from hyperliquid.info import Info
        except ImportError as exc:
            raise RuntimeError(
                "Install hyperliquid-python-sdk before sending live Hyperliquid orders"
            ) from exc

        wallet = Account.from_key(self.config.private_key)
        info = Info(base_url=self.config.base_url, skip_ws=True, perp_dexs=["", "xyz"])
        exchange = Exchange(
            wallet=wallet,
            base_url=self.config.base_url,
            account_address=self.config.account_address,
            perp_dexs=["", "xyz"],
        )
        self._sdk = (info, exchange)
        return self._sdk

    def _require_credentials(self) -> None:
        missing = []
        if not self.config.account_address:
            missing.append("wallet address")
        if not self.config.private_key:
            missing.append("private key")
        if missing:
            raise RuntimeError("Missing Hyperliquid " + " and ".join(missing))

    def _resolve_live_order_coin(self, resolved: ResolvedAsset) -> str:
        if resolved.kind != "spot" or resolved.coin.startswith("@"):
            return resolved.coin
        spot_meta = HyperliquidInfoClient(self.config).spot_meta()
        return resolve_spot_order_coin(spot_meta, resolved.coin)

    def _require_recent_verification(self, resolved: ResolvedAsset) -> None:
        if resolved.dex != "xyz":
            return
        if not self.verification_db_path:
            raise RuntimeError("Live trade.xyz orders require a verification database path")
        if not has_recent_successful_trade_xyz_check(
            self.verification_db_path,
            hyperliquid_coin=resolved.coin,
            max_age_ms=self.verification_max_age_ms,
        ):
            raise RuntimeError(f"{resolved.coin} is not recently verified in Hyperliquid metadata")


def submission_to_dict(submission: OrderSubmission) -> dict[str, Any]:
    return {
        "status": submission.status,
        "dry_run": submission.dry_run,
        "resolved": asdict(submission.resolved),
        "request": submission.request,
        "response": submission.response,
        "submitted_at_ms": int(time.time() * 1000),
    }


def extract_hyperliquid_order_id(response: Any) -> str | None:
    if isinstance(response, dict):
        for key in ("oid", "orderId", "order_id"):
            value = response.get(key)
            if value not in (None, ""):
                return str(value)
        for key in ("resting", "filled", "triggered", "response", "data", "statuses"):
            value = response.get(key)
            if value is None:
                continue
            found = extract_hyperliquid_order_id(value)
            if found is not None:
                return found
    if isinstance(response, list):
        for item in response:
            found = extract_hyperliquid_order_id(item)
            if found is not None:
                return found
    return None


def is_supported_live_asset(resolved: ResolvedAsset) -> bool:
    if resolved.kind == "spot" and resolved.coin == "UBTC/USDC":
        return True
    if resolved.kind == "perp" and resolved.coin in {"BTC", "ETH"} and resolved.dex is None:
        return True
    if resolved.dex != "xyz" or not resolved.coin.startswith("xyz:"):
        return False
    return is_trade_xyz_symbol_tradable(normalize_trade_symbol(resolved.coin))


def resolve_spot_order_coin(spot_meta: dict[str, Any], pair: str) -> str:
    if pair.startswith("@"):
        return pair
    target = pair.upper()
    universe = spot_meta.get("universe")
    if not isinstance(universe, list):
        raise RuntimeError("spotMeta response is missing universe")

    token_names = _spot_token_names(spot_meta)
    for entry in universe:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        if index is None:
            continue
        name = str(entry.get("name", "")).upper()
        if name == target:
            return f"@{index}"
        token_pair = _spot_pair_from_token_ids(entry.get("tokens"), token_names)
        if token_pair == target:
            return f"@{index}"
    raise RuntimeError(f"Spot pair {pair} was not found in Hyperliquid spotMeta")


def _spot_token_names(spot_meta: dict[str, Any]) -> dict[int, str]:
    names: dict[int, str] = {}
    tokens = spot_meta.get("tokens")
    if not isinstance(tokens, list):
        return names
    for token in tokens:
        if not isinstance(token, dict) or "index" not in token:
            continue
        names[int(token["index"])] = str(token.get("name", "")).upper()
    return names


def _spot_pair_from_token_ids(raw_tokens: Any, token_names: dict[int, str]) -> str | None:
    if not isinstance(raw_tokens, list) or len(raw_tokens) != 2:
        return None
    base = token_names.get(int(raw_tokens[0]))
    quote = token_names.get(int(raw_tokens[1]))
    if not base or not quote:
        return None
    return f"{base}/{quote}"


def _decimal_to_api_string(value: Decimal | None) -> str:
    if value is None:
        raise ValueError("value is required")
    return format(value.normalize(), "f")


def sdk_cloid(value: str):
    from hyperliquid.utils.types import Cloid
    return Cloid.from_str(value)


def prepare_perp_exit(*, price: Decimal, size: Decimal, sz_decimals: int,
                      slippage: Decimal, is_buy: bool = False) -> tuple[Decimal, Decimal]:
    """Round inward (sell up, buy down) to preserve the IOC slippage budget."""
    if not 0 <= sz_decimals <= 6:
        raise ValueError("invalid perpetual size precision")
    for value in (price, size, slippage):
        if not value.is_finite() or value <= 0:
            raise ValueError("exit inputs must be finite and positive")
    if slippage >= 1:
        raise ValueError("slippage must be less than one")
    raw = price * (1 + slippage if is_buy else 1 - slippage)
    # Integers are always legal, even when they have more than five figures.
    exponent = max(-(6 - sz_decimals), min(0, raw.adjusted() - 4))
    limit = raw.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_DOWN if is_buy else ROUND_CEILING)
    if (not is_buy and limit > price) or (is_buy and limit < price) or limit <= 0:
        raise ValueError("No valid sell price within the slippage budget")
    quantity = size.quantize(Decimal(1).scaleb(-sz_decimals), rounding=ROUND_DOWN)
    if quantity <= 0:
        raise ValueError("residual dust is below the size increment")
    return limit, quantity
