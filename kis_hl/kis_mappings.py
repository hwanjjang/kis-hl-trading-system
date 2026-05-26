from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from kis_hl.trade_xyz_assets import (
    TRADE_XYZ_ASSETS,
    TradeXyzAsset,
    get_trade_xyz_asset,
    has_minimum_listing_age,
    is_asset_tradable,
)

KIS_MAPPING_ACTIVE = "active"
KIS_MAPPING_EXCLUDED = "excluded"
KIS_MAPPING_UNSUPPORTED = "unsupported"

KIS_MARKET_DOMESTIC = "domestic"
KIS_MARKET_OVERSEAS = "overseas"
KIS_MARKET_UNSUPPORTED = "unsupported"

KIS_DOMESTIC_STOCK_MARKET_CODE = "J"

_OVERSEAS_PRICE_EXCHANGE_CODES = {
    "NASDAQ": "NAS",
    "NASD": "NAS",
    "NAS": "NAS",
    "NYSE": "NYS",
    "NYS": "NYS",
    "NYSE ARCA": "AMS",
    "NYSEARCA": "AMS",
    "AMEX": "AMS",
    "AMS": "AMS",
}


@dataclass(frozen=True, slots=True)
class KisMarketDataMapping:
    trade_symbol: str
    hyperliquid_coin: str
    asset_class: str
    kis_market: str
    kis_symbol: str | None
    kis_exchange_code: str | None
    kis_market_code: str | None
    status: str
    reason: str | None
    source: str
    notes: str


def build_trade_xyz_kis_mappings(
    *,
    assets: Iterable[TradeXyzAsset] = TRADE_XYZ_ASSETS,
    as_of: date | None = None,
) -> tuple[KisMarketDataMapping, ...]:
    return tuple(build_trade_xyz_kis_mapping(asset, as_of=as_of) for asset in assets)


def get_trade_xyz_kis_mapping(
    symbol: str,
    *,
    as_of: date | None = None,
) -> KisMarketDataMapping | None:
    asset = get_trade_xyz_asset(symbol)
    if asset is None:
        return None
    return build_trade_xyz_kis_mapping(asset, as_of=as_of)


def build_trade_xyz_kis_mapping(
    asset: TradeXyzAsset,
    *,
    as_of: date | None = None,
) -> KisMarketDataMapping:
    eligibility_status = (
        KIS_MAPPING_ACTIVE if is_asset_tradable(asset, as_of=as_of) else KIS_MAPPING_EXCLUDED
    )
    eligibility_reason = None if eligibility_status == KIS_MAPPING_ACTIVE else _exclusion_reason(asset, as_of)

    if asset.asset_class == "stock" and asset.underlying_exchange.upper() == "KRX":
        return KisMarketDataMapping(
            trade_symbol=asset.trade_symbol,
            hyperliquid_coin=asset.hyperliquid_coin,
            asset_class=asset.asset_class,
            kis_market=KIS_MARKET_DOMESTIC,
            kis_symbol=_strip_krx_suffix(asset.underlying_symbol),
            kis_exchange_code=None,
            kis_market_code=KIS_DOMESTIC_STOCK_MARKET_CODE,
            status=eligibility_status,
            reason=eligibility_reason,
            source="kis_domestic_inquire_price",
            notes="Uses the KIS domestic stock inquire-price endpoint.",
        )

    normalized_exchange = asset.underlying_exchange.strip().upper()
    exchange_code = map_kis_overseas_price_exchange(asset.underlying_exchange)
    if asset.asset_class in {"stock", "etf"} and exchange_code:
        notes = "Uses the KIS overseas price endpoint."
        if normalized_exchange in {"NYSE ARCA", "NYSEARCA"}:
            notes = (
                "Uses KIS overseas price code AMS for NYSE Arca ETF routing; "
                "confirm with a live KIS quote before trading new ETF symbols."
            )
        return KisMarketDataMapping(
            trade_symbol=asset.trade_symbol,
            hyperliquid_coin=asset.hyperliquid_coin,
            asset_class=asset.asset_class,
            kis_market=KIS_MARKET_OVERSEAS,
            kis_symbol=asset.underlying_symbol,
            kis_exchange_code=exchange_code,
            kis_market_code=None,
            status=eligibility_status,
            reason=eligibility_reason,
            source="kis_overseas_price",
            notes=notes,
        )

    return KisMarketDataMapping(
        trade_symbol=asset.trade_symbol,
        hyperliquid_coin=asset.hyperliquid_coin,
        asset_class=asset.asset_class,
        kis_market=KIS_MARKET_UNSUPPORTED,
        kis_symbol=None,
        kis_exchange_code=None,
        kis_market_code=None,
        status=(
            KIS_MAPPING_UNSUPPORTED
            if eligibility_status == KIS_MAPPING_ACTIVE
            else KIS_MAPPING_EXCLUDED
        ),
        reason=eligibility_reason or "KIS quote endpoint is not implemented for this trade.xyz asset.",
        source="manual_review_required",
        notes="Add a dedicated KIS index or alternative market-data endpoint before using this route.",
    )


def map_kis_overseas_price_exchange(exchange: str) -> str | None:
    return _OVERSEAS_PRICE_EXCHANGE_CODES.get(exchange.strip().upper())


def _strip_krx_suffix(symbol: str) -> str:
    return symbol.split(".", 1)[0]


def _exclusion_reason(asset: TradeXyzAsset, as_of: date | None) -> str:
    if asset.exclusion_reason:
        return asset.exclusion_reason
    if asset.listing_status not in {"listed", "not_applicable"}:
        return "Asset is not listed on a public securities exchange."
    if asset.asset_class == "stock" and not has_minimum_listing_age(asset, as_of=as_of):
        return f"Stock has been listed for less than {asset.min_listing_age_weeks} weeks."
    return "Asset is excluded by project eligibility rules."
