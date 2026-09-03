from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

DAY_MS = Decimal("86400000")


@dataclass(frozen=True, slots=True)
class TradeJournalRecord:
    venue: str
    symbol: str
    strategy: str
    side: str
    opened_at_ms: int
    closed_at_ms: int
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    fees: Decimal
    holding_days: Decimal
    outcome: str
    # Legacy operator classification retained for stored-row compatibility only.
    # Required review statistics always use the realized net PnL outcome.
    adjusted_outcome: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class TradeJournalStats:
    trade_count: int
    average_profit: Decimal | None
    average_loss: Decimal | None
    success_count: int
    failure_count: int
    breakeven_count: int
    success_failure_ratio: str | None
    win_rate_pct: Decimal | None
    adjusted_success_failure_ratio: str | None
    max_profit: Decimal | None
    max_loss: Decimal | None
    average_profit_holding_days: Decimal | None
    average_loss_holding_days: Decimal | None


def create_trade_journal_record(
    *,
    venue: str,
    symbol: str,
    strategy: str,
    side: str,
    opened_at_ms: int,
    closed_at_ms: int,
    entry_price: Decimal | str | int | float,
    exit_price: Decimal | str | int | float,
    quantity: Decimal | str | int | float,
    fees: Decimal | str | int | float = Decimal("0"),
    realized_pnl: Decimal | str | int | float | None = None,
    adjusted_outcome: str | None = None,
    notes: str = "",
) -> TradeJournalRecord:
    normalized_side = side.lower()
    if normalized_side not in {"long", "short", "buy", "sell"}:
        raise ValueError("side must be long, short, buy, or sell")
    entry = _to_decimal(entry_price)
    exit_ = _to_decimal(exit_price)
    qty = _to_decimal(quantity)
    fee_value = _to_decimal(fees)
    if entry <= 0:
        raise ValueError("entry_price must be positive")
    if exit_ <= 0:
        raise ValueError("exit_price must be positive")
    if qty <= 0:
        raise ValueError("quantity must be positive")
    if closed_at_ms < opened_at_ms:
        raise ValueError("closed_at_ms must be greater than or equal to opened_at_ms")

    pnl = _to_decimal(realized_pnl) if realized_pnl is not None else _calculate_pnl(
        side=normalized_side,
        entry_price=entry,
        exit_price=exit_,
        quantity=qty,
        fees=fee_value,
    )
    notional = entry * qty
    pnl_pct = (pnl / notional) * Decimal("100")
    holding_days = Decimal(closed_at_ms - opened_at_ms) / DAY_MS
    outcome = outcome_from_pnl(pnl)
    normalized_adjusted = _normalize_optional_outcome(adjusted_outcome)
    return TradeJournalRecord(
        venue=venue,
        symbol=symbol,
        strategy=strategy,
        side=normalized_side,
        opened_at_ms=opened_at_ms,
        closed_at_ms=closed_at_ms,
        entry_price=entry,
        exit_price=exit_,
        quantity=qty,
        realized_pnl=pnl,
        realized_pnl_pct=pnl_pct,
        fees=fee_value,
        holding_days=holding_days,
        outcome=outcome,
        adjusted_outcome=normalized_adjusted,
        notes=notes,
    )


def calculate_trade_journal_stats(
    entries: Iterable[TradeJournalRecord | Mapping[str, Any]],
) -> TradeJournalStats:
    records = [_coerce_record(entry) for entry in entries]
    profits = [record for record in records if record.realized_pnl > 0]
    losses = [record for record in records if record.realized_pnl < 0]
    success_count = len(profits)
    failure_count = len(losses)
    breakeven_count = len(records) - success_count - failure_count
    decisive_count = success_count + failure_count
    average_profit = _average([record.realized_pnl_pct for record in profits])
    average_loss = _average([record.realized_pnl_pct for record in losses])
    return TradeJournalStats(
        trade_count=len(records),
        average_profit=average_profit,
        average_loss=average_loss,
        success_count=success_count,
        failure_count=failure_count,
        breakeven_count=breakeven_count,
        success_failure_ratio=_return_ratio(average_profit, average_loss),
        win_rate_pct=(
            (Decimal(success_count) / Decimal(decisive_count)) * Decimal("100")
            if decisive_count
            else None
        ),
        adjusted_success_failure_ratio=_adjusted_return_ratio(
            average_profit=average_profit,
            average_loss=average_loss,
            success_count=success_count,
            failure_count=failure_count,
        ),
        max_profit=max((record.realized_pnl_pct for record in profits), default=None),
        max_loss=min((record.realized_pnl_pct for record in losses), default=None),
        average_profit_holding_days=_average([record.holding_days for record in profits]),
        average_loss_holding_days=_average([record.holding_days for record in losses]),
    )


def trade_journal_report(record: TradeJournalRecord, stats: TradeJournalStats) -> dict[str, Any]:
    return {
        "entry": asdict(record),
        "statistics": asdict(stats),
        "required_statistics": {
            "average_profit": stats.average_profit,
            "average_loss": stats.average_loss,
            "success_failure_ratio": stats.success_failure_ratio,
            "win_rate_pct": stats.win_rate_pct,
            "adjusted_success_failure_ratio": stats.adjusted_success_failure_ratio,
            "max_profit": stats.max_profit,
            "max_loss": stats.max_loss,
            "average_profit_holding_days": stats.average_profit_holding_days,
            "average_loss_holding_days": stats.average_loss_holding_days,
        },
    }


def outcome_from_pnl(realized_pnl: Decimal) -> str:
    if realized_pnl > 0:
        return "success"
    if realized_pnl < 0:
        return "failure"
    return "breakeven"


def _calculate_pnl(
    *,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    fees: Decimal,
) -> Decimal:
    if side in {"long", "buy"}:
        return (exit_price - entry_price) * quantity - fees
    return (entry_price - exit_price) * quantity - fees


def _normalize_optional_outcome(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    normalized = value.lower()
    if normalized not in {"success", "failure", "breakeven"}:
        raise ValueError("adjusted_outcome must be success, failure, or breakeven")
    return normalized


def _coerce_record(record: TradeJournalRecord | Mapping[str, Any]) -> TradeJournalRecord:
    if isinstance(record, TradeJournalRecord):
        return record
    return TradeJournalRecord(
        venue=str(record["venue"]),
        symbol=str(record["symbol"]),
        strategy=str(record["strategy"]),
        side=str(record["side"]),
        opened_at_ms=int(record["opened_at_ms"]),
        closed_at_ms=int(record["closed_at_ms"]),
        entry_price=_to_decimal(record["entry_price"]),
        exit_price=_to_decimal(record["exit_price"]),
        quantity=_to_decimal(record["quantity"]),
        realized_pnl=_to_decimal(record["realized_pnl"]),
        realized_pnl_pct=_to_decimal(record["realized_pnl_pct"]),
        fees=_to_decimal(record["fees"]),
        holding_days=_to_decimal(record["holding_days"]),
        outcome=str(record["outcome"]),
        adjusted_outcome=record.get("adjusted_outcome"),
        notes=str(record.get("notes", "")),
    )


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _return_ratio(
    average_profit: Decimal | None,
    average_loss: Decimal | None,
) -> str | None:
    if average_profit is None or average_loss is None or average_loss == 0:
        return None
    return _format_ratio(average_profit / abs(average_loss))


def _adjusted_return_ratio(
    *,
    average_profit: Decimal | None,
    average_loss: Decimal | None,
    success_count: int,
    failure_count: int,
) -> str | None:
    if (
        average_profit is None
        or average_loss is None
        or average_loss == 0
        or success_count == 0
        or failure_count == 0
    ):
        return None
    weighted_profit = average_profit * Decimal(success_count)
    weighted_loss = abs(average_loss) * Decimal(failure_count)
    return _format_ratio(weighted_profit / weighted_loss)


def _format_ratio(value: Decimal) -> str:
    return f"{format(value.normalize(), 'f')}:1"


def _to_decimal(value: Decimal | str | int | float | Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
