from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from kis_hl.reference_mappings import REFERENCE_PROVIDER_YAHOO
from kis_hl.storage import (
    list_trade_xyz_assets,
    list_trade_xyz_reference_mappings,
    seed_trade_xyz_assets,
    seed_trade_xyz_reference_mappings,
    store_market_daily_bars,
)
from kis_hl.trade_xyz_assets import normalize_trade_symbol


@dataclass(frozen=True, slots=True)
class DailyBarRoute:
    trade_symbol: str
    hyperliquid_coin: str
    asset_class: str
    provider: str
    provider_symbol: str
    provider_market: str | None
    source: str


def collect_trade_xyz_daily_bars(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None = None,
    asset_class: str | None = None,
    days: int = 365,
    date_to: date | None = None,
    store: bool = True,
    delay_ms: int = 0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("days must be positive")
    seed_trade_xyz_assets(db_path)
    seed_trade_xyz_reference_mappings(db_path)
    end_date = date_to or (date.today() + timedelta(days=1))
    start_date = end_date - timedelta(days=days)
    routes = _resolve_daily_routes(db_path, symbols=symbols, asset_class=asset_class)
    results: list[dict[str, Any]] = []
    for index, route in enumerate(routes):
        if index and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        try:
            response = client.chart_daily_bars(
                ticker=route.provider_symbol,
                date_from=start_date,
                date_to=end_date,
            )
            bars = [
                {
                    **bar,
                    "provider_symbol": route.provider_symbol,
                    "hyperliquid_coin": route.hyperliquid_coin,
                }
                for bar in response.bars
            ]
            stored = 0
            if store:
                stored = store_market_daily_bars(
                    db_path,
                    source=route.provider,
                    market=f"trade_xyz_daily_{route.provider}",
                    symbol=route.trade_symbol,
                    exchange_code=route.provider_market,
                    bars=bars,
                    observed_at_ms=response.observed_at_ms,
                )
            results.append(
                {
                    "trade_symbol": route.trade_symbol,
                    "hyperliquid_coin": route.hyperliquid_coin,
                    "status": "success",
                    "provider": route.provider,
                    "provider_symbol": route.provider_symbol,
                    "bar_count": len(bars),
                    "stored": stored,
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                }
            )
        except Exception as exc:
            if fail_fast:
                raise
            results.append(
                {
                    "trade_symbol": route.trade_symbol,
                    "hyperliquid_coin": route.hyperliquid_coin,
                    "status": "failed",
                    "provider": route.provider,
                    "provider_symbol": route.provider_symbol,
                    "error": str(exc),
                }
            )

    return {
        "requested": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "stored_bars": sum(int(item.get("stored", 0)) for item in results),
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "results": results,
    }


def _resolve_daily_routes(
    db_path: str | Path,
    *,
    symbols: Iterable[str] | None,
    asset_class: str | None,
) -> list[DailyBarRoute]:
    assets = list_trade_xyz_assets(db_path, tradable_only=True, asset_class=asset_class)
    references = {
        item["trade_symbol"]: item
        for item in list_trade_xyz_reference_mappings(
            db_path,
            provider=REFERENCE_PROVIDER_YAHOO,
            status="active",
        )
    }
    selected = _filter_assets(assets, symbols)
    return [_daily_route_for_asset(asset, references.get(asset["trade_symbol"])) for asset in selected]


def _filter_assets(
    assets: list[dict[str, Any]],
    symbols: Iterable[str] | None,
) -> list[dict[str, Any]]:
    if not symbols:
        return assets
    normalized_symbols = {normalize_trade_symbol(symbol) for symbol in symbols}
    selected = []
    for asset in assets:
        aliases = {normalize_trade_symbol(alias) for alias in asset.get("aliases", [])}
        candidates = {
            normalize_trade_symbol(asset["trade_symbol"]),
            normalize_trade_symbol(asset["hyperliquid_coin"]),
            normalize_trade_symbol(asset["underlying_symbol"]),
            *aliases,
        }
        if candidates & normalized_symbols:
            selected.append(asset)
    return selected


def _daily_route_for_asset(
    asset: dict[str, Any],
    reference: dict[str, Any] | None,
) -> DailyBarRoute:
    if reference:
        return DailyBarRoute(
            trade_symbol=asset["trade_symbol"],
            hyperliquid_coin=asset["hyperliquid_coin"],
            asset_class=asset["asset_class"],
            provider=reference["provider"],
            provider_symbol=reference["provider_symbol"],
            provider_market=reference["provider_market"],
            source="reference_mapping",
        )
    return DailyBarRoute(
        trade_symbol=asset["trade_symbol"],
        hyperliquid_coin=asset["hyperliquid_coin"],
        asset_class=asset["asset_class"],
        provider=REFERENCE_PROVIDER_YAHOO,
        provider_symbol=asset["underlying_symbol"],
        provider_market=asset["underlying_exchange"],
        source="underlying_symbol",
    )
