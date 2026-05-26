from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from kis_hl.assets import ResolvedAsset, resolve_hyperliquid_symbol
from kis_hl.config import HyperliquidConfig
from kis_hl.logging_utils import get_logger

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
    def __init__(self, config: HyperliquidConfig) -> None:
        self.config = config
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

        self._require_credentials()
        _info, exchange = self._load_sdk()
        is_buy = normalized_side == "buy"
        if normalized_type == "market":
            response = exchange.market_open(
                resolved.coin,
                is_buy,
                float(size),
                None,
                float(slippage),
            )
        else:
            order_payload = {"limit": {"tif": tif}}
            response = exchange.order(
                resolved.coin,
                is_buy,
                float(size),
                float(price),
                order_payload,
                reduce_only,
            )
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


def submission_to_dict(submission: OrderSubmission) -> dict[str, Any]:
    return {
        "status": submission.status,
        "dry_run": submission.dry_run,
        "resolved": asdict(submission.resolved),
        "request": submission.request,
        "response": submission.response,
        "submitted_at_ms": int(time.time() * 1000),
    }

