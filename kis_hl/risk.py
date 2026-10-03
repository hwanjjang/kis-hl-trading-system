from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from typing import Any

DEFAULT_OPERATING_CAPITAL_MULTIPLE = Decimal("10")
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
) -> Decimal:
    portfolio_value = _to_decimal(portfolio_value_usdc)
    if portfolio_value < 0:
        raise ValueError("portfolio_value_usdc must be non-negative")
    multiple = _to_decimal(multiple)
    if multiple <= 0:
        raise ValueError("multiple must be positive")
    return portfolio_value * multiple


def calculate_risk_units(*, capital, entry, stop, units, quantity_step,
                         minimum_quantity="0", minimum_notional="0", side="long"):
    """Size against an explicit fixed stop; no market reads or execution authority."""
    values = {k: _to_decimal(v) for k, v in dict(
        capital=capital, entry=entry, stop=stop, units=units,
        quantity_step=quantity_step, minimum_quantity=minimum_quantity,
        minimum_notional=minimum_notional).items()}
    if any(values[k] <= 0 for k in ("capital", "entry", "stop", "units", "quantity_step")):
        raise ValueError("Capital, prices, units and quantity step must be positive")
    if min(values["minimum_quantity"], values["minimum_notional"]) < 0:
        raise ValueError("Market minimums must be non-negative")
    if side not in {"long", "short"}:
        raise ValueError("Side must be long or short")
    distance = (values["entry"] - values["stop"]) * (1 if side == "long" else -1)
    if distance <= 0:
        raise ValueError("Stop must be on the loss side of entry")
    budget = values["capital"] * DEFAULT_RISK_FRACTION * values["units"]
    step = values["quantity_step"]
    quantity = (budget / distance / step).to_integral_value(rounding=ROUND_DOWN) * step
    notional = quantity * values["entry"]
    return dict(quantity=quantity, notional=notional, risk=quantity * distance,
                risk_budget=budget, stop_distance=distance, units=values["units"],
                below_minimum=quantity <= 0 or quantity < values["minimum_quantity"]
                or notional < values["minimum_notional"])


def n_multiplier_for_asset_class(asset_class: str) -> Decimal:
    try:
        return DEFAULT_N_MULTIPLIERS[asset_class]
    except KeyError as exc:
        raise ValueError(f"unsupported asset_class: {asset_class}") from exc


def calculate_isolated_margin(*, quantity, entry, stop, leverage, allocated_margin,
                              margin_tiers, side="long", buffer="0"):
    """Allocation at proposed entry to meet initial and stop maintenance requirements.

    Zero buffer is the mathematical maintenance boundary, not an execution guarantee.
    Tiers use Hyperliquid metadata's lowerBound/maxLeverage fields.
    """
    q, entry, stop, leverage, allocated, buffer = map(
        _to_decimal, (quantity, entry, stop, leverage, allocated_margin, buffer))
    if min(q, entry, stop) <= 0 or leverage < 1 or leverage != leverage.to_integral_value():
        raise ValueError("Positive quantity/prices and integer leverage >= 1 required")
    if allocated < 0 or buffer < 0:
        raise ValueError("Allocated margin and buffer must be non-negative")
    if side not in {"long", "short"}:
        raise ValueError("Side must be long or short")
    loss = q * (entry - stop if side == "long" else stop - entry)
    if loss <= 0:
        raise ValueError("Stop must be on the loss side of entry")
    if not isinstance(margin_tiers, list) or not margin_tiers:
        raise ValueError("Complete margin tiers required")
    tiers = []
    for item in margin_tiers:
        if not isinstance(item, dict):
            raise ValueError("Invalid margin tier")
        lower, maximum = _to_decimal(item.get("lowerBound")), _to_decimal(item.get("maxLeverage"))
        if (lower < 0 or maximum < 1 or maximum != maximum.to_integral_value()
                or (not tiers and lower != 0)
                or (tiers and (lower <= tiers[-1][0] or maximum > tiers[-1][1]))):
            raise ValueError("Margin tiers must start at zero, increase bounds and not increase leverage")
        tiers.append((lower, maximum))
    stop_notional, entry_notional = q * stop, q * entry
    maintenance, entry_maximum = Decimal(0), tiers[0][1]
    for i, (lower, maximum) in enumerate(tiers):
        upper = tiers[i+1][0] if i+1 < len(tiers) else stop_notional
        if stop_notional > lower:
            maintenance += (min(stop_notional, upper) - lower) / (2 * maximum)
        if entry_notional >= lower:
            entry_maximum = maximum
    initial = entry_notional / leverage
    required = max(initial, loss + maintenance + buffer)
    return dict(initial_margin=initial, maintenance_at_stop=maintenance, loss_at_stop=loss,
                required_margin=required, allocated_margin=allocated,
                shortfall=max(Decimal(0), required-allocated), buffer=buffer,
                entry_notional=entry_notional, stop_notional=stop_notional,
                leverage=leverage, leverage_exceeds_market_max=leverage > entry_maximum)


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
    from kis_hl.journal_sync import decimal

    return decimal(value)
