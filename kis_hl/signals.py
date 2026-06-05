from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from kis_hl.assets import resolve_hyperliquid_symbol

BTCUSDC_FUTURES_SYMBOL = "BTCUSDC-PERP"
BTCUSDC_FUTURES_INTERVAL = "3h"


@dataclass(frozen=True, slots=True)
class BreakoutSignal:
    strategy: str
    symbol: str
    resolved_coin: str
    interval: str
    side: str
    should_enter: bool
    reason: str
    current_close: Decimal
    breakout_level: Decimal
    lookback_candles: int
    entry_price: Decimal | None
    current_candle_start_ms: int | None
    current_candle_end_ms: int | None
    reference_candle_start_ms: int | None
    reference_candle_end_ms: int | None


@dataclass(frozen=True, slots=True)
class NormalizedCandle:
    start_ms: int | None
    end_ms: int | None
    high: Decimal
    close: Decimal
    raw: Mapping[str, Any]


def evaluate_btcusdc_futures_3h_breakout(
    candles: Iterable[Mapping[str, Any]],
    *,
    symbol: str = BTCUSDC_FUTURES_SYMBOL,
    lookback_candles: int = 1,
) -> BreakoutSignal:
    return evaluate_previous_high_close_breakout(
        candles,
        symbol=symbol,
        interval=BTCUSDC_FUTURES_INTERVAL,
        lookback_candles=lookback_candles,
        strategy="btc_3h_previous_high_close_breakout",
    )


def evaluate_previous_high_close_breakout(
    candles: Iterable[Mapping[str, Any]],
    *,
    symbol: str,
    interval: str,
    lookback_candles: int = 1,
    strategy: str = "previous_high_close_breakout",
) -> BreakoutSignal:
    if lookback_candles <= 0:
        raise ValueError("lookback_candles must be positive")
    normalized = _normalize_candles(candles)
    required = lookback_candles + 1
    if len(normalized) < required:
        raise ValueError(f"breakout evaluation requires at least {required} closed candles")

    current = normalized[-1]
    reference_window = normalized[-required:-1]
    reference = max(reference_window, key=lambda candle: candle.high)
    breakout_level = reference.high
    should_enter = current.close > breakout_level
    resolved = resolve_hyperliquid_symbol(symbol)
    return BreakoutSignal(
        strategy=strategy,
        symbol=symbol,
        resolved_coin=resolved.coin,
        interval=interval,
        side="buy",
        should_enter=should_enter,
        reason="close_above_previous_high" if should_enter else "close_not_above_previous_high",
        current_close=current.close,
        breakout_level=breakout_level,
        lookback_candles=lookback_candles,
        entry_price=current.close if should_enter else None,
        current_candle_start_ms=current.start_ms,
        current_candle_end_ms=current.end_ms,
        reference_candle_start_ms=reference.start_ms,
        reference_candle_end_ms=reference.end_ms,
    )


def _normalize_candles(candles: Iterable[Mapping[str, Any]]) -> list[NormalizedCandle]:
    normalized = [_normalize_candle(candle) for candle in candles]
    if not normalized:
        raise ValueError("candles must not be empty")
    if all(candle.start_ms is not None for candle in normalized):
        return sorted(normalized, key=lambda candle: int(candle.start_ms))
    return normalized


def _normalize_candle(candle: Mapping[str, Any]) -> NormalizedCandle:
    return NormalizedCandle(
        start_ms=_optional_int(candle, "t", "start_time_ms", "startTime", "start"),
        end_ms=_optional_int(candle, "T", "end_time_ms", "endTime", "end"),
        high=_required_decimal(candle, "h", "high", "high_price"),
        close=_required_decimal(candle, "c", "close", "close_price"),
        raw=candle,
    )


def _required_decimal(candle: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = candle.get(key)
        if value not in (None, ""):
            return Decimal(str(value))
    raise ValueError(f"candle is missing one of: {', '.join(keys)}")


def _optional_int(candle: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = candle.get(key)
        if value not in (None, ""):
            return int(value)
    return None
