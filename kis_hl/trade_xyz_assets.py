from __future__ import annotations

from dataclasses import dataclass


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
        duplicate_group="japan_equity_beta",
        preferred_symbol="JP225",
        exclusion_reason="Duplicate Japan exposure; project trades JP225 instead.",
    ),
    TradeXyzAsset("TSLA", "xyz:TSLA", "stock", "Tesla, Inc.", "TSLA", "NASDAQ", "listed", True),
    TradeXyzAsset("NVDA", "xyz:NVDA", "stock", "NVIDIA Corporation", "NVDA", "NASDAQ", "listed", True),
    TradeXyzAsset("GOOGL", "xyz:GOOGL", "stock", "Alphabet Inc. Class A", "GOOGL", "NASDAQ", "listed", True),
    TradeXyzAsset("INTC", "xyz:INTC", "stock", "Intel Corporation", "INTC", "NASDAQ", "listed", True),
    TradeXyzAsset("MU", "xyz:MU", "stock", "Micron Technology, Inc.", "MU", "NASDAQ", "listed", True),
    TradeXyzAsset("PLTR", "xyz:PLTR", "stock", "Palantir Technologies Inc.", "PLTR", "NASDAQ", "listed", True),
    TradeXyzAsset("ORCL", "xyz:ORCL", "stock", "Oracle Corporation", "ORCL", "NYSE", "listed", True),
    TradeXyzAsset("MSTR", "xyz:MSTR", "stock", "Strategy Inc.", "MSTR", "NASDAQ", "listed", True),
    TradeXyzAsset("MSFT", "xyz:MSFT", "stock", "Microsoft Corporation", "MSFT", "NASDAQ", "listed", True),
    TradeXyzAsset("META", "xyz:META", "stock", "Meta Platforms, Inc.", "META", "NASDAQ", "listed", True),
    TradeXyzAsset("AMZN", "xyz:AMZN", "stock", "Amazon.com, Inc.", "AMZN", "NASDAQ", "listed", True),
    TradeXyzAsset("AMD", "xyz:AMD", "stock", "Advanced Micro Devices, Inc.", "AMD", "NASDAQ", "listed", True),
    TradeXyzAsset("AAPL", "xyz:AAPL", "stock", "Apple Inc.", "AAPL", "NASDAQ", "listed", True),
    TradeXyzAsset("COIN", "xyz:COIN", "stock", "Coinbase Global, Inc.", "COIN", "NASDAQ", "listed", True),
    TradeXyzAsset("HOOD", "xyz:HOOD", "stock", "Robinhood Markets, Inc.", "HOOD", "NASDAQ", "listed", True),
    TradeXyzAsset("NFLX", "xyz:NFLX", "stock", "Netflix, Inc.", "NFLX", "NASDAQ", "listed", True),
    TradeXyzAsset("CRCL", "xyz:CRCL", "stock", "Circle Internet Group, Inc.", "CRCL", "NYSE", "listed", True),
    TradeXyzAsset("SNDK", "xyz:SNDK", "stock", "Sandisk Corporation", "SNDK", "NASDAQ", "listed", True),
    TradeXyzAsset("RIVN", "xyz:RIVN", "stock", "Rivian Automotive, Inc.", "RIVN", "NASDAQ", "listed", True),
    TradeXyzAsset("USAR", "xyz:USAR", "stock", "USA Rare Earth, Inc.", "USAR", "NASDAQ", "listed", True),
    TradeXyzAsset("TSM", "xyz:TSM", "stock", "Taiwan Semiconductor Manufacturing Company ADR", "TSM", "NYSE", "listed", True),
    TradeXyzAsset(
        "SKHYNIX",
        "xyz:SKHYNIX",
        "stock",
        "SK hynix Inc.",
        "000660.KS",
        "KRX",
        "listed",
        True,
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
        aliases=("SMSN",),
    ),
    TradeXyzAsset("HYUNDAI", "xyz:HYUNDAI", "stock", "Hyundai Motor Company", "005380.KS", "KRX", "listed", True),
    TradeXyzAsset("BABA", "xyz:BABA", "stock", "Alibaba Group Holding Ltd. ADR", "BABA", "NYSE", "listed", True),
    TradeXyzAsset("CRWV", "xyz:CRWV", "stock", "CoreWeave, Inc.", "CRWV", "NASDAQ", "listed", True),
    TradeXyzAsset("DKNG", "xyz:DKNG", "stock", "DraftKings Inc.", "DKNG", "NASDAQ", "listed", True),
    TradeXyzAsset("HIMS", "xyz:HIMS", "stock", "Hims & Hers Health, Inc.", "HIMS", "NYSE", "listed", True),
    TradeXyzAsset("COST", "xyz:COST", "stock", "Costco Wholesale Corporation", "COST", "NASDAQ", "listed", True),
    TradeXyzAsset("LLY", "xyz:LLY", "stock", "Eli Lilly and Company", "LLY", "NYSE", "listed", True),
)


def get_trade_xyz_asset(symbol: str) -> TradeXyzAsset | None:
    normalized = normalize_trade_symbol(symbol)
    for asset in TRADE_XYZ_ASSETS:
        aliases = {normalize_trade_symbol(alias) for alias in asset.aliases}
        if normalize_trade_symbol(asset.trade_symbol) == normalized or normalized in aliases:
            return asset
    return None


def is_trade_xyz_symbol_tradable(symbol: str) -> bool:
    asset = get_trade_xyz_asset(symbol)
    return bool(asset and asset.tradable and asset.listing_status in {"listed", "not_applicable"})


def normalize_trade_symbol(symbol: str) -> str:
    raw = symbol.strip()
    if ":" in raw:
        _dex, raw = raw.split(":", 1)
    return raw.upper().replace("/", "").replace("-", "").replace("_", "")

