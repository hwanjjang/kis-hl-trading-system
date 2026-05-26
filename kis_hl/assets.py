from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    original: str
    coin: str
    kind: str
    dex: str | None = None
    note: str = ""


def resolve_hyperliquid_symbol(symbol: str, *, dex: str | None = None) -> ResolvedAsset:
    raw = symbol.strip()
    if not raw:
        raise ValueError("symbol is required")

    explicit_dex, asset = _split_dex(raw)
    active_dex = explicit_dex or dex
    if active_dex:
        normalized = asset.upper().replace("/", "").replace("-", "")
        return ResolvedAsset(
            original=symbol,
            coin=f"{active_dex.lower()}:{normalized}",
            kind="perp",
            dex=active_dex.lower(),
            note="HIP-3 builder-deployed perp namespace",
        )

    compact = raw.upper().replace("-", "").replace("_", "").replace(" ", "")
    if compact in {"BTCUSDC", "BTC/USD", "BTC/USDC"} or raw.upper() == "BTC/USDC":
        return ResolvedAsset(
            original=symbol,
            coin="UBTC/USDC",
            kind="spot",
            note="Hyperliquid mainnet L1 remaps UI BTC/USDC to UBTC/USDC",
        )

    if "/" in raw:
        return ResolvedAsset(original=symbol, coin=raw.upper(), kind="spot")

    if compact in {"BTCPERP", "BTCPERPETUAL"}:
        return ResolvedAsset(original=symbol, coin="BTC", kind="perp")

    return ResolvedAsset(original=symbol, coin=compact, kind="perp")


def _split_dex(symbol: str) -> tuple[str | None, str]:
    if ":" not in symbol:
        return None, symbol
    left, right = symbol.split(":", 1)
    if not left or not right:
        raise ValueError("dex-qualified symbols must use the format dex:asset")
    return left, right

