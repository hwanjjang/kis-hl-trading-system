from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from kis_hl.trade_xyz_assets import (
    TRADE_XYZ_ASSETS,
    TradeXyzAsset,
    get_trade_xyz_asset,
    is_asset_tradable,
)

REFERENCE_MAPPING_ACTIVE = "active"
REFERENCE_MAPPING_EXCLUDED = "excluded"

REFERENCE_PROVIDER_YAHOO = "yahoo_finance"

_YAHOO_ROUTES = {
    "KR200": {
        "provider_symbol": "^KS200",
        "provider_market": "KSC",
        "provider_instrument_type": "INDEX",
        "notes": "Yahoo Finance KOSPI 200 index fallback. KIS remains the primary source.",
    },
    "SP500": {
        "provider_symbol": "^GSPC",
        "provider_market": "SNP",
        "provider_instrument_type": "INDEX",
        "notes": "Yahoo Finance S&P 500 index fallback. KIS remains the primary source.",
    },
    "XYZ100": {
        "provider_symbol": "^NDX",
        "provider_market": "NIM",
        "provider_instrument_type": "INDEX",
        "notes": "Yahoo Finance Nasdaq 100 index fallback for trade.xyz XYZ100.",
    },
    "JP225": {
        "provider_symbol": "^N225",
        "provider_market": "OSA",
        "provider_instrument_type": "INDEX",
        "notes": "Yahoo Finance Nikkei 225 index fallback. KIS remains the primary source.",
    },
    "BRENTOIL": {
        "provider_symbol": "BZ=F",
        "provider_market": "NYM",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous Brent crude futures reference.",
    },
    "WTIOIL": {
        "provider_symbol": "CL=F",
        "provider_market": "NYM",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous WTI crude futures reference for the Hyperliquid xyz:CL market.",
    },
    "NATGAS": {
        "provider_symbol": "NG=F",
        "provider_market": "NYM",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous Henry Hub natural gas futures reference.",
    },
    "COPPER": {
        "provider_symbol": "HG=F",
        "provider_market": "CMX",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous high-grade copper futures reference.",
    },
    "GOLD": {
        "provider_symbol": "GC=F",
        "provider_market": "CMX",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous gold futures proxy; trade.xyz reference is spot-style.",
    },
    "SILVER": {
        "provider_symbol": "SI=F",
        "provider_market": "CMX",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous silver futures proxy; trade.xyz reference is spot-style.",
    },
    "PLATINUM": {
        "provider_symbol": "PL=F",
        "provider_market": "NYM",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous platinum futures proxy; trade.xyz reference is spot-style.",
    },
    "PALLADIUM": {
        "provider_symbol": "PA=F",
        "provider_market": "NYM",
        "provider_instrument_type": "FUTURE",
        "notes": "Yahoo Finance continuous palladium futures proxy; trade.xyz reference is spot-style.",
    },
    "EUR": {
        "provider_symbol": "EURUSD=X",
        "provider_market": "CCY",
        "provider_instrument_type": "CURRENCY",
        "notes": "Yahoo Finance EUR/USD FX reference.",
    },
    "JPY": {
        "provider_symbol": "JPY=X",
        "provider_market": "CCY",
        "provider_instrument_type": "CURRENCY",
        "notes": "Yahoo Finance USD/JPY FX reference.",
    },
}


@dataclass(frozen=True, slots=True)
class ReferenceMarketDataMapping:
    trade_symbol: str
    hyperliquid_coin: str
    asset_class: str
    provider: str
    provider_symbol: str
    provider_market: str
    provider_instrument_type: str
    status: str
    reason: str | None
    source: str
    notes: str


def build_trade_xyz_reference_mappings(
    *,
    assets: Iterable[TradeXyzAsset] = TRADE_XYZ_ASSETS,
    as_of: date | None = None,
) -> tuple[ReferenceMarketDataMapping, ...]:
    mappings = []
    for asset in assets:
        mapping = build_trade_xyz_reference_mapping(asset, as_of=as_of)
        if mapping:
            mappings.append(mapping)
    return tuple(mappings)


def get_trade_xyz_reference_mapping(
    symbol: str,
    *,
    as_of: date | None = None,
) -> ReferenceMarketDataMapping | None:
    asset = get_trade_xyz_asset(symbol)
    if asset is None:
        return None
    return build_trade_xyz_reference_mapping(asset, as_of=as_of)


def build_trade_xyz_reference_mapping(
    asset: TradeXyzAsset,
    *,
    as_of: date | None = None,
) -> ReferenceMarketDataMapping | None:
    route = _YAHOO_ROUTES.get(asset.trade_symbol)
    if route is None:
        return None
    active = is_asset_tradable(asset, as_of=as_of)
    return ReferenceMarketDataMapping(
        trade_symbol=asset.trade_symbol,
        hyperliquid_coin=asset.hyperliquid_coin,
        asset_class=asset.asset_class,
        provider=REFERENCE_PROVIDER_YAHOO,
        provider_symbol=str(route["provider_symbol"]),
        provider_market=str(route["provider_market"]),
        provider_instrument_type=str(route["provider_instrument_type"]),
        status=REFERENCE_MAPPING_ACTIVE if active else REFERENCE_MAPPING_EXCLUDED,
        reason=None if active else asset.exclusion_reason or "Asset is excluded by project eligibility rules.",
        source="yahoo_finance_chart",
        notes=str(route["notes"]),
    )
