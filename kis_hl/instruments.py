"""Explicit analysis and execution identities; aliases are never price conversions."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Instrument:
    id: str
    venue: str
    market: str
    symbol: str
    currency: str
    quote_exchange: str = ""
    order_exchange: str = ""
    underlying: str = ""
    status: str = "documented"


INSTRUMENTS = [
    Instrument(
        "index:KOSPI", "kis", "domestic_index", "0001", "KRW", underlying="KOSPI"
    ),
    Instrument(
        "index:KOSPI200", "kis", "domestic_index", "2001", "KRW", underlying="KOSPI200"
    ),
    Instrument("index:SPX", "kis", "overseas_index", "SPX", "USD", underlying="S&P500"),
    Instrument(
        "index:NDX", "kis", "overseas_index", "NDX", "USD", underlying="Nasdaq100"
    ),
    Instrument(
        "kis:069500", "kis", "domestic", "069500", "KRW", "J", "KRX", "KOSPI200"
    ),
    Instrument(
        "kis:122630", "kis", "domestic", "122630", "KRW", "J", "KRX", "KOSPI200"
    ),
    *[
        Instrument("kis:" + s, "kis", "overseas", s, "USD", quote, order, underlying)
        for s, quote, order, underlying in [
            ("SPY", "AMS", "AMEX", "S&P500"),
            ("UPRO", "AMS", "AMEX", "S&P500"),
            ("QQQ", "NAS", "NASD", "Nasdaq100"),
            ("TQQQ", "NAS", "NASD", "Nasdaq100"),
            ("GLD", "AMS", "AMEX", "gold"),
            ("QPUX", "NAS", "NASD", "quantum"),
        ]
    ],
    Instrument(
        "kis:DRAM",
        "kis",
        "overseas",
        "DRAM",
        "USD",
        "AMS",
        "AMEX",
        "memory",
        status="broker_metadata_observed",
    ),
    Instrument("hl:BTC", "hyperliquid", "perp", "BTC", "USDC", underlying="BTC"),
    Instrument("hl:ETH", "hyperliquid", "perp", "ETH", "USDC", underlying="ETH"),
    *[
        Instrument(
            "hl:xyz:" + s, "hyperliquid", "perp", "xyz:" + s, "USDC", underlying=u
        )
        for s, u in [
            ("SP500", "S&P500"),
            ("XYZ100", "Nasdaq100"),
            ("GOLD", "gold"),
            ("KORU", "Direxion Daily MSCI South Korea Bull 3X Shares"),
            ("DRAM", "memory_contract"),
        ]
    ],
]


def instrument(key):
    found = next((x for x in INSTRUMENTS if x.id == key), None)
    if not found:
        raise ValueError("Unknown explicit instrument ID; use instrument list")
    return found


def list_instruments():
    return [asdict(x) for x in INSTRUMENTS]


def capabilities(key):
    asset = instrument(key)
    if "index" in asset.market:
        return {
            "instrument": key,
            "execution": False,
            "stop_loss": "not_applicable",
            "trailing": "not_applicable",
        }
    return {
        "instrument": key,
        "execution": asset.status,
        "limit": "documented",
        "native_stop_loss": (
            "documented_requires_readback"
            if asset.venue == "hyperliquid"
            else "unverified"
        ),
        "native_trailing": ("documented_requires_readback" if asset.venue == "hyperliquid" else "unverified"),
        "native_trailing_policy": "continuous_mark" if asset.venue == "hyperliquid" else None,
        "local_stop_loss": asset.venue == "kis",
        "local_trailing": True,
        "session_and_account_verification_required": True,
    }
