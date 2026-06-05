from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from kis_hl.assets import ResolvedAsset, resolve_hyperliquid_symbol
from kis_hl.config import HyperliquidConfig
from kis_hl.logging_utils import get_logger
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
        if size <= 0:
            raise ValueError("size must be positive")
        if normalized_type == "limit" and (price is None or price <= 0):
            raise ValueError("limit orders require a positive price")
        if normalized_type == "stop-market":
            if trigger_price is None or trigger_price <= 0:
                raise ValueError("stop-market orders require a positive trigger_price")
            if not reduce_only:
                raise ValueError("stop-market stop-loss orders require reduce_only=True")
        execution_price = price if price is not None else trigger_price

        request = {
            "client_request_id": uuid4().hex,
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
                "Live trading is limited to BTCUSDC spot and mapped tradable trade.xyz assets; "
                f"got {symbol}"
            )
        self._require_recent_verification(resolved)

        self._require_credentials()
        if not reduce_only:
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
        try:
            if normalized_type == "market":
                response = exchange.market_open(
                    order_coin,
                    is_buy,
                    float(size),
                    None,
                    float(slippage),
                )
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
                )
        except Exception as exc:
            logger.error(
                "hyperliquid_order_failed",
                extra={"resolved_coin": resolved.coin, "order_coin": order_coin, "error": str(exc)},
            )
            raise
        logger.info("hyperliquid_order_submitted", extra={"resolved_coin": resolved.coin})
        return OrderSubmission("submitted", False, resolved, request, response)

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
        info = Info(base_url=self.config.base_url, skip_ws=True)
        exchange = Exchange(
            wallet=wallet,
            base_url=self.config.base_url,
            account_address=self.config.account_address,
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
    if resolved.kind == "perp" and resolved.coin == "BTC" and resolved.dex is None:
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
