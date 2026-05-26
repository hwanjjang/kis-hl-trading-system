from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

MIN_STOCK_LISTING_AGE_WEEKS = 30


@dataclass(frozen=True, slots=True)
class TradeXyzAsset:
    trade_symbol: str
    hyperliquid_coin: str
    asset_class: str
    underlying_name: str
    underlying_symbol: str
    underlying_exchange: str
    listing_status: str
    tradable: bool
    listing_date: str | None = None
    min_listing_age_weeks: int = MIN_STOCK_LISTING_AGE_WEEKS
    aliases: tuple[str, ...] = ()
    duplicate_group: str | None = None
    preferred_symbol: str | None = None
    exclusion_reason: str | None = None
    source_url: str = "https://docs.trade.xyz/consolidated-resources/specification-index"
    notes: str = ""


TRADE_XYZ_ASSETS: tuple[TradeXyzAsset, ...] = (
    TradeXyzAsset(
        trade_symbol="SP500",
        hyperliquid_coin="xyz:SP500",
        asset_class="equity_index",
        underlying_name="S&P 500 Index",
        underlying_symbol="SPX",
        underlying_exchange="S&P Dow Jones Indices",
        listing_status="not_applicable",
        tradable=True,
        min_listing_age_weeks=0,
    ),
    TradeXyzAsset(
        trade_symbol="XYZ100",
        hyperliquid_coin="xyz:XYZ100",
        asset_class="equity_index",
        underlying_name="XYZ U.S. 100 Index",
        underlying_symbol="XYZ100",
        underlying_exchange="trade.xyz",
        listing_status="not_applicable",
        tradable=True,
        min_listing_age_weeks=0,
    ),
    TradeXyzAsset(
        trade_symbol="KR200",
        hyperliquid_coin="xyz:KR200",
        asset_class="equity_index",
        underlying_name="KOSPI 200 Index",
        underlying_symbol="KOSPI200",
        underlying_exchange="KRX",
        listing_status="not_applicable",
        tradable=True,
        min_listing_age_weeks=0,
        aliases=("Korea200",),
        duplicate_group="south_korea_equity_beta",
        preferred_symbol="KR200",
        source_url="project-rule",
        notes="Preferred over EWY for South Korea broad-market exposure.",
    ),
    TradeXyzAsset(
        trade_symbol="JP225",
        hyperliquid_coin="xyz:JP225",
        asset_class="equity_index",
        underlying_name="Nikkei 225 Index",
        underlying_symbol="NIKKEI225",
        underlying_exchange="Nikkei",
        listing_status="not_applicable",
        tradable=True,
        min_listing_age_weeks=0,
        aliases=("Japan225",),
        duplicate_group="japan_equity_beta",
        preferred_symbol="JP225",
        source_url="project-rule",
        notes="Preferred over EWJ for Japan broad-market exposure.",
    ),
    TradeXyzAsset(
        trade_symbol="URNM",
        hyperliquid_coin="xyz:URNM",
        asset_class="etf",
        underlying_name="Sprott Uranium Miners ETF",
        underlying_symbol="URNM",
        underlying_exchange="NYSE Arca",
        listing_status="listed",
        tradable=True,
        min_listing_age_weeks=0,
    ),
    TradeXyzAsset(
        trade_symbol="EWY",
        hyperliquid_coin="xyz:EWY",
        asset_class="etf",
        underlying_name="iShares MSCI South Korea ETF",
        underlying_symbol="EWY",
        underlying_exchange="NYSE Arca",
        listing_status="listed",
        tradable=False,
        min_listing_age_weeks=0,
        duplicate_group="south_korea_equity_beta",
        preferred_symbol="KR200",
        exclusion_reason="Duplicate South Korea exposure; project trades KR200 instead.",
    ),
    TradeXyzAsset(
        trade_symbol="EWJ",
        hyperliquid_coin="xyz:EWJ",
        asset_class="etf",
        underlying_name="iShares MSCI Japan ETF",
        underlying_symbol="EWJ",
        underlying_exchange="NYSE Arca",
        listing_status="listed",
        tradable=False,
        min_listing_age_weeks=0,
        duplicate_group="japan_equity_beta",
        preferred_symbol="JP225",
        exclusion_reason="Duplicate Japan exposure; project trades JP225 instead.",
    ),
    TradeXyzAsset("TSLA", "xyz:TSLA", "stock", "Tesla, Inc.", "TSLA", "NASDAQ", "listed", True, "2010-06-29"),
    TradeXyzAsset("NVDA", "xyz:NVDA", "stock", "NVIDIA Corporation", "NVDA", "NASDAQ", "listed", True, "1999-01-22"),
    TradeXyzAsset("GOOGL", "xyz:GOOGL", "stock", "Alphabet Inc. Class A", "GOOGL", "NASDAQ", "listed", True, "2004-08-19"),
    TradeXyzAsset("INTC", "xyz:INTC", "stock", "Intel Corporation", "INTC", "NASDAQ", "listed", True, "1971-10-13"),
    TradeXyzAsset("MU", "xyz:MU", "stock", "Micron Technology, Inc.", "MU", "NASDAQ", "listed", True, "1984-06-01"),
    TradeXyzAsset("PLTR", "xyz:PLTR", "stock", "Palantir Technologies Inc.", "PLTR", "NASDAQ", "listed", True, "2020-09-30"),
    TradeXyzAsset("ORCL", "xyz:ORCL", "stock", "Oracle Corporation", "ORCL", "NYSE", "listed", True, "1986-03-12"),
    TradeXyzAsset("MSTR", "xyz:MSTR", "stock", "Strategy Inc.", "MSTR", "NASDAQ", "listed", True, "1998-06-11"),
    TradeXyzAsset("MSFT", "xyz:MSFT", "stock", "Microsoft Corporation", "MSFT", "NASDAQ", "listed", True, "1986-03-13"),
    TradeXyzAsset("META", "xyz:META", "stock", "Meta Platforms, Inc.", "META", "NASDAQ", "listed", True, "2012-05-18"),
    TradeXyzAsset("AMZN", "xyz:AMZN", "stock", "Amazon.com, Inc.", "AMZN", "NASDAQ", "listed", True, "1997-05-15"),
    TradeXyzAsset("AMD", "xyz:AMD", "stock", "Advanced Micro Devices, Inc.", "AMD", "NASDAQ", "listed", True, "1972-09-27"),
    TradeXyzAsset("AAPL", "xyz:AAPL", "stock", "Apple Inc.", "AAPL", "NASDAQ", "listed", True, "1980-12-12"),
    TradeXyzAsset("COIN", "xyz:COIN", "stock", "Coinbase Global, Inc.", "COIN", "NASDAQ", "listed", True, "2021-04-14"),
    TradeXyzAsset("HOOD", "xyz:HOOD", "stock", "Robinhood Markets, Inc.", "HOOD", "NASDAQ", "listed", True, "2021-07-29"),
    TradeXyzAsset("NFLX", "xyz:NFLX", "stock", "Netflix, Inc.", "NFLX", "NASDAQ", "listed", True, "2002-05-23"),
    TradeXyzAsset("CRCL", "xyz:CRCL", "stock", "Circle Internet Group, Inc.", "CRCL", "NYSE", "listed", True, "2025-06-05"),
    TradeXyzAsset("SNDK", "xyz:SNDK", "stock", "Sandisk Corporation", "SNDK", "NASDAQ", "listed", True, "2025-02-24"),
    TradeXyzAsset("RIVN", "xyz:RIVN", "stock", "Rivian Automotive, Inc.", "RIVN", "NASDAQ", "listed", True, "2021-11-10"),
    TradeXyzAsset("USAR", "xyz:USAR", "stock", "USA Rare Earth, Inc.", "USAR", "NASDAQ", "listed", True, "2025-03-14"),
    TradeXyzAsset("TSM", "xyz:TSM", "stock", "Taiwan Semiconductor Manufacturing Company ADR", "TSM", "NYSE", "listed", True, "1997-10-08"),
    TradeXyzAsset(
        "SKHYNIX",
        "xyz:SKHYNIX",
        "stock",
        "SK hynix Inc.",
        "000660.KS",
        "KRX",
        "listed",
        True,
        "1996-12-26",
        aliases=("SKHX",),
    ),
    TradeXyzAsset(
        "SAMSUNG",
        "xyz:SAMSUNG",
        "stock",
        "Samsung Electronics Co., Ltd.",
        "005930.KS",
        "KRX",
        "listed",
        True,
        "1975-06-11",
        aliases=("SMSN",),
    ),
    TradeXyzAsset("HYUNDAI", "xyz:HYUNDAI", "stock", "Hyundai Motor Company", "005380.KS", "KRX", "listed", True, "1974-06-28"),
    TradeXyzAsset("BABA", "xyz:BABA", "stock", "Alibaba Group Holding Ltd. ADR", "BABA", "NYSE", "listed", True, "2014-09-19"),
    TradeXyzAsset("CRWV", "xyz:CRWV", "stock", "CoreWeave, Inc.", "CRWV", "NASDAQ", "listed", True, "2025-03-28"),
    TradeXyzAsset("DKNG", "xyz:DKNG", "stock", "DraftKings Inc.", "DKNG", "NASDAQ", "listed", True, "2020-04-24"),
    TradeXyzAsset("HIMS", "xyz:HIMS", "stock", "Hims & Hers Health, Inc.", "HIMS", "NYSE", "listed", True, "2021-01-21"),
    TradeXyzAsset("COST", "xyz:COST", "stock", "Costco Wholesale Corporation", "COST", "NASDAQ", "listed", True, "1985-12-05"),
    TradeXyzAsset("LLY", "xyz:LLY", "stock", "Eli Lilly and Company", "LLY", "NYSE", "listed", True, "1952-01-01"),
)


def get_trade_xyz_asset(symbol: str) -> TradeXyzAsset | None:
    normalized = normalize_trade_symbol(symbol)
    for asset in TRADE_XYZ_ASSETS:
        aliases = {normalize_trade_symbol(alias) for alias in asset.aliases}
        if normalize_trade_symbol(asset.trade_symbol) == normalized or normalized in aliases:
            return asset
    return None


def is_trade_xyz_symbol_tradable(symbol: str, *, as_of: date | None = None) -> bool:
    asset = get_trade_xyz_asset(symbol)
    return bool(asset and is_asset_tradable(asset, as_of=as_of))


def is_asset_tradable(asset: TradeXyzAsset, *, as_of: date | None = None) -> bool:
    if not asset.tradable or asset.listing_status not in {"listed", "not_applicable"}:
        return False
    return has_minimum_listing_age(asset, as_of=as_of)


def has_minimum_listing_age(asset: TradeXyzAsset, *, as_of: date | None = None) -> bool:
    if asset.asset_class != "stock":
        return True
    if not asset.listing_date:
        return False
    listed_on = parse_listing_date(asset.listing_date)
    current_date = as_of or date.today()
    min_age = timedelta(weeks=asset.min_listing_age_weeks)
    return current_date - listed_on >= min_age


def parse_listing_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_trade_symbol(symbol: str) -> str:
    raw = symbol.strip()
    if ":" in raw:
        _dex, raw = raw.split(":", 1)
    return raw.upper().replace("/", "").replace("-", "").replace("_", "")
