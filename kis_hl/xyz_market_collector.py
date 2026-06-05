from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.storage import (
    get_latest_trade_xyz_universe_symbols,
    list_latest_trade_xyz_universe_assets,
    store_market_spread_snapshot,
    store_trade_xyz_universe_snapshot,
    upsert_market_funding_rates,
)
from kis_hl.trade_xyz_assets import TRADE_XYZ_ASSETS

HYPERLIQUID_SOURCE = "hyperliquid"
XYZ_DEX = "xyz"


def collect_xyz_universe(
    db_path: str | Path,
    *,
    client: Any,
    previous_symbols: Iterable[str] | None = None,
    store: bool = True,
    observed_at_ms: int | None = None,
) -> dict[str, Any]:
    observed_at = observed_at_ms or int(time.time() * 1000)
    response = client.meta_and_asset_ctxs(dex=XYZ_DEX)
    assets, asset_contexts = _extract_universe_response(response)
    current_symbols = sorted(str(asset["name"]) for asset in assets)

    curated_symbols = {asset.hyperliquid_coin for asset in TRADE_XYZ_ASSETS}
    if previous_symbols is None:
        previous = get_latest_trade_xyz_universe_symbols(db_path, dex=XYZ_DEX)
        if not previous:
            previous = curated_symbols
    else:
        previous = {_normalize_xyz_coin(symbol) for symbol in previous_symbols}
    new_symbols = sorted(set(current_symbols) - previous) if previous else []
    missing_symbols = sorted(previous - set(current_symbols)) if previous else []

    unmapped_symbols = sorted(set(current_symbols) - curated_symbols)

    snapshot_id = None
    if store:
        snapshot_id = store_trade_xyz_universe_snapshot(
            db_path,
            dex=XYZ_DEX,
            observed_at_ms=observed_at,
            assets=assets,
            asset_contexts=asset_contexts,
            new_symbols=new_symbols,
            missing_symbols=missing_symbols,
            raw={"response": response},
            source=HYPERLIQUID_SOURCE,
        )

    return {
        "db": str(db_path),
        "snapshot_id": snapshot_id,
        "asset_count": len(assets),
        "assets_with_open_interest": sum(
            1 for context in asset_contexts if context.get("openInterest") not in (None, "")
        ),
        "assets_with_day_base_volume": sum(
            1 for context in asset_contexts if context.get("dayBaseVlm") not in (None, "")
        ),
        "assets_with_day_notional_volume": sum(
            1 for context in asset_contexts if context.get("dayNtlVlm") not in (None, "")
        ),
        "new_symbols": new_symbols,
        "missing_symbols": missing_symbols,
        "unmapped_symbols": unmapped_symbols,
        "stored": store,
    }


def collect_xyz_funding_rates(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None = None,
    lookback_hours: int = 24,
    end_time_ms: int | None = None,
    store: bool = True,
    delay_ms: int = 0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    end_time = end_time_ms or int(time.time() * 1000)
    start_time = end_time - lookback_hours * 60 * 60 * 1000
    resolved_symbols = _resolve_collection_symbols(db_path, client=client, symbols=symbols)
    results: list[dict[str, Any]] = []

    for index, symbol in enumerate(resolved_symbols):
        if index and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        try:
            rows = client.funding_history(
                symbol,
                start_time_ms=start_time,
                end_time_ms=end_time,
                dex=XYZ_DEX,
            )
            stored_rows = (
                upsert_market_funding_rates(
                    db_path,
                    dex=XYZ_DEX,
                    symbol=symbol,
                    rows=rows,
                    observed_at_ms=end_time,
                    source=HYPERLIQUID_SOURCE,
                )
                if store
                else 0
            )
            latest = rows[-1] if rows else None
            results.append(
                {
                    "symbol": symbol,
                    "status": "success",
                    "rows": len(rows),
                    "stored_rows": stored_rows,
                    "latest_funding_rate": latest.get("fundingRate") if latest else None,
                    "latest_premium": latest.get("premium") if latest else None,
                }
            )
        except Exception as exc:
            if fail_fast:
                raise
            results.append({"symbol": symbol, "status": "failed", "error": str(exc)})

    return {
        "db": str(db_path),
        "lookback_hours": lookback_hours,
        "requested": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "stored_rows": sum(int(item.get("stored_rows", 0)) for item in results),
        "results": results,
    }


def collect_xyz_spreads(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None = None,
    store: bool = True,
    observed_at_ms: int | None = None,
    delay_ms: int = 0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    observed_at = observed_at_ms or int(time.time() * 1000)
    resolved_symbols = _resolve_collection_symbols(db_path, client=client, symbols=symbols)
    results: list[dict[str, Any]] = []

    for index, symbol in enumerate(resolved_symbols):
        if index and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        try:
            request_symbol = symbol.split(":", 1)[1] if ":" in symbol else symbol
            book = client.l2_book(request_symbol, dex=XYZ_DEX)
            snapshot = calculate_spread_snapshot(book, fallback_symbol=symbol, observed_at_ms=observed_at)
            stored_id = (
                store_market_spread_snapshot(
                    db_path,
                    dex=XYZ_DEX,
                    symbol=snapshot["symbol"],
                    observed_at_ms=snapshot["observed_at_ms"],
                    best_bid=snapshot["best_bid"],
                    best_ask=snapshot["best_ask"],
                    mid_price=snapshot["mid_price"],
                    spread_abs=snapshot["spread_abs"],
                    spread_bps=snapshot["spread_bps"],
                    bid_size=snapshot["bid_size"],
                    ask_size=snapshot["ask_size"],
                    raw=book,
                    source=HYPERLIQUID_SOURCE,
                )
                if store
                else None
            )
            results.append({"status": "success", "stored_id": stored_id, **snapshot})
        except Exception as exc:
            if fail_fast:
                raise
            results.append({"symbol": symbol, "status": "failed", "error": str(exc)})

    return {
        "db": str(db_path),
        "requested": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "stored": sum(1 for item in results if item.get("stored_id") is not None),
        "results": results,
    }


def calculate_spread_snapshot(
    book: dict[str, Any],
    *,
    fallback_symbol: str,
    observed_at_ms: int,
) -> dict[str, Any]:
    levels = book.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        raise RuntimeError("l2Book response is missing bid/ask levels")
    bids = levels[0]
    asks = levels[1]
    if not bids or not asks:
        raise RuntimeError("l2Book response has empty bid or ask levels")
    best_bid = bids[0]
    best_ask = asks[0]
    bid_px = Decimal(str(best_bid["px"]))
    ask_px = Decimal(str(best_ask["px"]))
    if ask_px < bid_px:
        raise RuntimeError("l2Book best ask is below best bid")
    mid = (bid_px + ask_px) / Decimal("2")
    spread = ask_px - bid_px
    spread_bps = Decimal("0") if mid == 0 else (spread / mid) * Decimal("10000")
    return {
        "symbol": str(book.get("coin") or fallback_symbol),
        "observed_at_ms": int(book.get("time") or observed_at_ms),
        "best_bid": str(bid_px),
        "best_ask": str(ask_px),
        "mid_price": str(mid),
        "spread_abs": str(spread),
        "spread_bps": str(spread_bps),
        "bid_size": _optional_level_size(best_bid),
        "ask_size": _optional_level_size(best_ask),
    }


def _resolve_collection_symbols(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None,
) -> list[str]:
    if symbols:
        return [_normalize_xyz_coin(symbol) for symbol in symbols]
    latest_assets = list_latest_trade_xyz_universe_assets(db_path, dex=XYZ_DEX)
    if latest_assets:
        return [item["symbol"] for item in latest_assets]
    response = client.meta_and_asset_ctxs(dex=XYZ_DEX)
    assets, _contexts = _extract_universe_response(response)
    return [str(asset["name"]) for asset in assets]


def _extract_universe_response(response: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(response) < 2 or not isinstance(response[0], dict) or not isinstance(response[1], list):
        raise RuntimeError("metaAndAssetCtxs response is missing universe or asset contexts")
    raw_assets = response[0].get("universe")
    if not isinstance(raw_assets, list):
        raise RuntimeError("metaAndAssetCtxs response is missing universe")
    assets = [asset for asset in raw_assets if isinstance(asset, dict) and "name" in asset]
    contexts = [ctx for ctx in response[1] if isinstance(ctx, dict)]
    return assets, contexts


def _normalize_xyz_coin(symbol: str) -> str:
    return resolve_hyperliquid_symbol(symbol, dex=XYZ_DEX).coin


def _optional_level_size(level: dict[str, Any]) -> str | None:
    value = level.get("sz")
    return str(value) if value not in (None, "") else None
