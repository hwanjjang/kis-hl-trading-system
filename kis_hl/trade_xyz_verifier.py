from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from kis_hl.storage import (
    list_trade_xyz_assets,
    seed_trade_xyz_assets,
    store_trade_xyz_asset_check,
)


def verify_trade_xyz_assets(
    db_path: str | Path,
    *,
    mids: dict[str, str],
    tradable_only: bool = True,
    asset_class: str | None = None,
    checked_at_ms: int | None = None,
) -> list[dict[str, Any]]:
    seed_trade_xyz_assets(db_path)
    checked_at = checked_at_ms or int(time.time() * 1000)
    assets = list_trade_xyz_assets(db_path, tradable_only=tradable_only, asset_class=asset_class)
    checks: list[dict[str, Any]] = []
    for asset in assets:
        mid, source_key = find_mid_for_coin(mids, asset["hyperliquid_coin"])
        available = mid is not None
        failure_reason = None if available else "missing_from_hyperliquid_all_mids"
        check = {
            "trade_symbol": asset["trade_symbol"],
            "hyperliquid_coin": asset["hyperliquid_coin"],
            "dex": "xyz",
            "available": available,
            "last_mid": mid,
            "mid_source_key": source_key,
            "checked_at_ms": checked_at,
            "failure_reason": failure_reason,
        }
        check["id"] = store_trade_xyz_asset_check(
            db_path,
            trade_symbol=asset["trade_symbol"],
            hyperliquid_coin=asset["hyperliquid_coin"],
            dex="xyz",
            available=available,
            last_mid=mid,
            mid_source_key=source_key,
            checked_at_ms=checked_at,
            failure_reason=failure_reason,
            raw={"mid": mid, "source_key": source_key},
        )
        checks.append(check)
    return checks


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    available = sum(1 for check in checks if check["available"])
    return {
        "checked": len(checks),
        "available": available,
        "unavailable": len(checks) - available,
    }


def find_mid_for_coin(mids: dict[str, str], hyperliquid_coin: str) -> tuple[str | None, str | None]:
    candidates = [hyperliquid_coin]
    if ":" in hyperliquid_coin:
        _dex, symbol = hyperliquid_coin.split(":", 1)
        candidates.append(symbol)
    normalized_mids = {normalize_mid_key(key): (key, value) for key, value in mids.items()}
    for candidate in candidates:
        found = normalized_mids.get(normalize_mid_key(candidate))
        if found:
            return str(found[1]), found[0]
    return None, None


def normalize_mid_key(value: str) -> str:
    return value.upper().replace("/", "").replace("-", "").replace("_", "")
