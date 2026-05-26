from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from kis_hl.assets import ResolvedAsset, resolve_hyperliquid_symbol
from kis_hl.config import HyperliquidConfig
from kis_hl.logging_utils import get_logger
from kis_hl.storage import has_recent_successful_trade_xyz_check
from kis_hl.trade_xyz_assets import is_trade_xyz_symbol_tradable, normalize_trade_symbol

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


class HyperliquidTradingClient:
    def __init__(
        self,
        config: HyperliquidConfig,
        *,
        verification_db_path: str | Path | None = None,
        verification_max_age_hours: int = 24,
    ) -> None:
        self.config = config
        self.verification_db_path = verification_db_path
        self.verification_max_age_ms = verification_max_age_hours * 60 * 60 * 1000
        self._sdk: tuple[Any, Any] | None = None

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        size: Decimal,
        price: Decimal | None = None,
        reduce_only: bool = False,
        tif: str = "Gtc",
        slippage: Decimal = Decimal("0.05"),
        dex: str | None = None,
        dry_run: bool = True,
    ) -> OrderSubmission:
        resolved = resolve_hyperliquid_symbol(symbol, dex=dex)
        normalized_side = side.lower()
        normalized_type = order_type.lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if normalized_type not in {"limit", "market"}:
            raise ValueError("order_type must be limit or market")
        if size <= 0:
            raise ValueError("size must be positive")
        if normalized_type == "limit" and (price is None or price <= 0):
            raise ValueError("limit orders require a positive price")

        request = {
            "client_request_id": uuid4().hex,
            "symbol": symbol,
            "resolved_coin": resolved.coin,
            "order_coin": resolved.coin,
            "kind": resolved.kind,
            "side": normalized_side,
            "order_type": normalized_type,
            "size": str(size),
            "price": str(price) if price is not None else None,
            "reduce_only": reduce_only,
            "tif": tif,
            "base_url": self.config.base_url,
            "key_profile": self.config.key_profile,
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
                order_payload = {"limit": {"tif": tif}}
                response = exchange.order(
                    order_coin,
                    is_buy,
                    float(size),
                    float(price),
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


def is_supported_live_asset(resolved: ResolvedAsset) -> bool:
    if resolved.kind == "spot" and resolved.coin == "UBTC/USDC":
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
