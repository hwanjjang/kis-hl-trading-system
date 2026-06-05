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
KIS_MARKET_DOMESTIC_INDEX = "domestic_index"
KIS_MARKET_OVERSEAS_INDEX_TIME = "overseas_index_time"
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

_INDEX_ROUTES = {
    "KR200": {
        "kis_market": KIS_MARKET_DOMESTIC_INDEX,
        "kis_symbol": "2001",
        "kis_exchange_code": None,
        "kis_market_code": "U",
        "source": "kis_domestic_index_price",
        "notes": "Uses KIS domestic index current-price endpoint for KOSPI 200.",
    },
    "SP500": {
        "kis_market": KIS_MARKET_OVERSEAS_INDEX_TIME,
        "kis_symbol": "SPX",
        "kis_exchange_code": None,
        "kis_market_code": "N",
        "source": "kis_overseas_time_indexchartprice",
        "notes": "Uses KIS overseas index intraday chart endpoint for S&P 500 latest available data.",
    },
    "XYZ100": {
        "kis_market": KIS_MARKET_OVERSEAS_INDEX_TIME,
        "kis_symbol": "NDX",
        "kis_exchange_code": None,
        "kis_market_code": "N",
        "source": "kis_overseas_time_indexchartprice",
        "notes": "Uses KIS overseas index intraday chart endpoint for Nasdaq 100 latest available data.",
    },
    "JP225": {
        "kis_market": KIS_MARKET_OVERSEAS_INDEX_TIME,
        "kis_symbol": "JP#NI225",
        "kis_exchange_code": None,
        "kis_market_code": "N",
        "source": "kis_overseas_time_indexchartprice",
        "notes": "Uses KIS overseas index intraday chart endpoint for Nikkei 225 latest available data.",
    },
}

_REFERENCE_ONLY_ROUTES = {
    "BRENTOIL": {
        "kis_symbol": "BZ",
        "kis_exchange_code": "CME",
        "source": "kis_overseas_future_pending",
        "reason": "KIS overseas futures collection needs dynamic SRS_CD contract resolution.",
        "notes": "Reference root is CME Brent crude futures. Do not collect until ffcode.mst front-contract resolution is implemented.",
    },
    "WTIOIL": {
        "kis_symbol": "CL",
        "kis_exchange_code": "CME",
        "source": "kis_overseas_future_pending",
        "reason": "KIS overseas futures collection needs dynamic SRS_CD contract resolution.",
        "notes": "Reference root is CME WTI crude futures. Hyperliquid exposes the market as xyz:CL.",
    },
    "NATGAS": {
        "kis_symbol": "NG",
        "kis_exchange_code": "CME",
        "source": "kis_overseas_future_pending",
        "reason": "KIS overseas futures collection needs dynamic SRS_CD contract resolution.",
        "notes": "Reference root is CME Henry Hub natural gas futures. Do not collect until ffcode.mst front-contract resolution is implemented.",
    },
    "COPPER": {
        "kis_symbol": "HG",
        "kis_exchange_code": "CME",
        "source": "kis_overseas_future_pending",
        "reason": "KIS overseas futures collection needs dynamic SRS_CD contract resolution.",
        "notes": "Reference root is CME copper futures. Do not collect until ffcode.mst front-contract resolution is implemented.",
    },
    "GOLD": {
        "kis_symbol": "XAUUSD",
        "kis_exchange_code": None,
        "source": "pyth_spot_reference",
        "reason": "No exact KIS spot metal quote route is implemented.",
        "notes": "trade.xyz references XAU/USD spot; a KIS gold futures quote would be a proxy and is not enabled.",
    },
    "SILVER": {
        "kis_symbol": "XAGUSD",
        "kis_exchange_code": None,
        "source": "pyth_spot_reference",
        "reason": "No exact KIS spot metal quote route is implemented.",
        "notes": "trade.xyz references XAG/USD spot; a KIS silver futures quote would be a proxy and is not enabled.",
    },
    "PLATINUM": {
        "kis_symbol": "XPTUSD",
        "kis_exchange_code": None,
        "source": "pyth_spot_reference",
        "reason": "No exact KIS spot metal quote route is implemented.",
        "notes": "trade.xyz references XPT/USD spot; a KIS platinum futures quote would be a proxy and is not enabled.",
    },
    "PALLADIUM": {
        "kis_symbol": "XPDUSD",
        "kis_exchange_code": None,
        "source": "pyth_spot_reference",
        "reason": "No exact KIS spot metal quote route is implemented.",
        "notes": "trade.xyz references XPD/USD spot; a KIS palladium futures quote would be a proxy and is not enabled.",
    },
    "JPY": {
        "kis_symbol": "USDJPY",
        "kis_exchange_code": None,
        "source": "pyth_fx_reference",
        "reason": "No KIS FX quote route is implemented for trade.xyz FX references.",
        "notes": "trade.xyz references USD/JPY.",
    },
    "EUR": {
        "kis_symbol": "EURUSD",
        "kis_exchange_code": None,
        "source": "pyth_fx_reference",
        "reason": "No KIS FX quote route is implemented for trade.xyz FX references.",
        "notes": "trade.xyz references EUR/USD.",
    },
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

    if asset.asset_class == "equity_index" and asset.trade_symbol in _INDEX_ROUTES:
        route = _INDEX_ROUTES[asset.trade_symbol]
        return KisMarketDataMapping(
            trade_symbol=asset.trade_symbol,
            hyperliquid_coin=asset.hyperliquid_coin,
            asset_class=asset.asset_class,
            kis_market=str(route["kis_market"]),
            kis_symbol=str(route["kis_symbol"]),
            kis_exchange_code=route["kis_exchange_code"],
            kis_market_code=str(route["kis_market_code"]),
            status=eligibility_status,
            reason=eligibility_reason,
            source=str(route["source"]),
            notes=str(route["notes"]),
        )

    if asset.trade_symbol in _REFERENCE_ONLY_ROUTES:
        route = _REFERENCE_ONLY_ROUTES[asset.trade_symbol]
        return KisMarketDataMapping(
            trade_symbol=asset.trade_symbol,
            hyperliquid_coin=asset.hyperliquid_coin,
            asset_class=asset.asset_class,
            kis_market=KIS_MARKET_UNSUPPORTED,
            kis_symbol=str(route["kis_symbol"]),
            kis_exchange_code=route["kis_exchange_code"],
            kis_market_code=None,
            status=(
                KIS_MAPPING_UNSUPPORTED
                if eligibility_status == KIS_MAPPING_ACTIVE
                else KIS_MAPPING_EXCLUDED
            ),
            reason=eligibility_reason or str(route["reason"]),
            source=str(route["source"]),
            notes=str(route["notes"]),
        )

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
