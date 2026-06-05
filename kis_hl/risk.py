from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

DEFAULT_OPERATING_CAPITAL_MULTIPLE = Decimal("20")
DEFAULT_OPERATING_CAPITAL_INCREMENT = Decimal("1000")
DEFAULT_RISK_FRACTION = Decimal("0.01")

DEFAULT_N_MULTIPLIERS: dict[str, Decimal] = {
    "equity_index": Decimal("2.0"),
    "etf": Decimal("2.5"),
    "commodity": Decimal("2.5"),
    "fx": Decimal("2.0"),
    "stock": Decimal("3.0"),
}


@dataclass(frozen=True, slots=True)
class PositionSize:
    operating_capital_usdc: Decimal
    risk_budget_usdc: Decimal
    atr: Decimal
    n: Decimal
    stop_distance: Decimal
    amount: Decimal
    entry_price: Decimal | None = None
    entry_notional_usdc: Decimal | None = None


@dataclass(frozen=True, slots=True)
class WeeklyEmaStatus:
    latest_close: Decimal
    ema: Decimal
    above: bool
    weekly_close_count: int


def calculate_operating_capital(
    portfolio_value_usdc: Decimal | str | int | float,
    *,
    multiple: Decimal = DEFAULT_OPERATING_CAPITAL_MULTIPLE,
    increment: Decimal = DEFAULT_OPERATING_CAPITAL_INCREMENT,
) -> Decimal:
    portfolio_value = _to_decimal(portfolio_value_usdc)
    if portfolio_value < 0:
        raise ValueError("portfolio_value_usdc must be non-negative")
    if multiple <= 0:
        raise ValueError("multiple must be positive")
    if increment <= 0:
        raise ValueError("increment must be positive")
    floored = (portfolio_value // increment) * increment
    return floored * multiple


def n_multiplier_for_asset_class(asset_class: str) -> Decimal:
    try:
        return DEFAULT_N_MULTIPLIERS[asset_class]
    except KeyError as exc:
        raise ValueError(f"unsupported asset_class: {asset_class}") from exc


def calculate_position_size(
    *,
    operating_capital_usdc: Decimal | str | int | float,
    atr: Decimal | str | int | float,
    n: Decimal | str | int | float,
    entry_price: Decimal | str | int | float | None = None,
    risk_fraction: Decimal = DEFAULT_RISK_FRACTION,
) -> PositionSize:
    operating_capital = _to_decimal(operating_capital_usdc)
    atr_value = _to_decimal(atr)
    multiplier = _to_decimal(n)
    if operating_capital <= 0:
        raise ValueError("operating_capital_usdc must be positive")
    if atr_value <= 0:
        raise ValueError("atr must be positive")
    if multiplier <= 0:
        raise ValueError("n must be positive")
    if risk_fraction <= 0:
        raise ValueError("risk_fraction must be positive")

    risk_budget = operating_capital * risk_fraction
    stop_distance = atr_value * multiplier
    amount = risk_budget / stop_distance
    parsed_entry_price = _to_decimal(entry_price) if entry_price is not None else None
    if parsed_entry_price is not None and parsed_entry_price <= 0:
        raise ValueError("entry_price must be positive")
    entry_notional = amount * parsed_entry_price if parsed_entry_price is not None else None
    return PositionSize(
        operating_capital_usdc=operating_capital,
        risk_budget_usdc=risk_budget,
        atr=atr_value,
        n=multiplier,
        stop_distance=stop_distance,
        amount=amount,
        entry_price=parsed_entry_price,
        entry_notional_usdc=entry_notional,
    )


def calculate_atr(
    daily_bars: Iterable[Mapping[str, Any]],
    *,
    periods: int = 10,
) -> Decimal:
    bars = _sorted_daily_bars(daily_bars)
    if periods <= 0:
        raise ValueError("periods must be positive")
    if len(bars) < periods + 1:
        raise ValueError(f"ATR({periods}) requires at least {periods + 1} daily bars")

    true_ranges: list[Decimal] = []
    previous_close = _bar_decimal(bars[0], "close", "close_price", "adj_close", "adj_close_price")
    for bar in bars[1:]:
        high = _bar_decimal(bar, "high", "high_price")
        low = _bar_decimal(bar, "low", "low_price")
        close = _bar_decimal(bar, "close", "close_price", "adj_close", "adj_close_price")
        if high < low:
            raise ValueError("daily bar high must be greater than or equal to low")
        true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = close

    return sum(true_ranges[-periods:], Decimal("0")) / Decimal(periods)


def calculate_atr_10d(daily_bars: Iterable[Mapping[str, Any]]) -> Decimal:
    return calculate_atr(daily_bars, periods=10)


def calculate_weekly_ema_status(
    daily_bars: Iterable[Mapping[str, Any]],
    *,
    periods: int = 30,
) -> WeeklyEmaStatus:
    bars = _sorted_daily_bars(daily_bars)
    if periods <= 0:
        raise ValueError("periods must be positive")
    weekly_closes = _weekly_closes(bars)
    if len(weekly_closes) < periods:
        raise ValueError(f"EMA({periods}W) requires at least {periods} weekly closes")

    ema = sum(weekly_closes[:periods], Decimal("0")) / Decimal(periods)
    smoothing = Decimal("2") / Decimal(periods + 1)
    for close in weekly_closes[periods:]:
        ema = (close - ema) * smoothing + ema
    latest_close = weekly_closes[-1]
    return WeeklyEmaStatus(
        latest_close=latest_close,
        ema=ema,
        above=latest_close > ema,
        weekly_close_count=len(weekly_closes),
    )


def calculate_30w_ema_status(daily_bars: Iterable[Mapping[str, Any]]) -> WeeklyEmaStatus:
    return calculate_weekly_ema_status(daily_bars, periods=30)


def _weekly_closes(bars: list[Mapping[str, Any]]) -> list[Decimal]:
    weekly: list[Decimal] = []
    current_week: tuple[int, int] | None = None
    current_close: Decimal | None = None
    for bar in bars:
        bar_date = _bar_date(bar)
        iso = bar_date.isocalendar()
        week_key = (iso.year, iso.week)
        if current_week is not None and week_key != current_week and current_close is not None:
            weekly.append(current_close)
        current_week = week_key
        current_close = _bar_decimal(bar, "close", "close_price", "adj_close", "adj_close_price")
    if current_close is not None:
        weekly.append(current_close)
    return weekly


def _sorted_daily_bars(daily_bars: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    bars = list(daily_bars)
    if not bars:
        raise ValueError("daily_bars must not be empty")
    return sorted(bars, key=_bar_date)


def _bar_date(bar: Mapping[str, Any]) -> date:
    raw = bar.get("date", bar.get("bar_date"))
    if raw is None:
        raise ValueError("daily bar is missing date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def _bar_decimal(bar: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = bar.get(key)
        if value not in (None, ""):
            return _to_decimal(value)
    raise ValueError(f"daily bar is missing one of: {', '.join(keys)}")


def _to_decimal(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
