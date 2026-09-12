"""Account-wide execution facts and deferred, source-backed completed journals."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Iterable

from kis_hl.trade_journal import (
    calculate_trade_journal_stats,
    create_trade_journal_record,
)


def decimal(value, *, positive=False):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid decimal") from None
    if not n.is_finite() or (positive and n <= 0):
        raise ValueError(
            "Expected a finite positive decimal"
            if positive
            else "Expected a finite decimal"
        )
    return n


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Scope:
    venue: str
    environment: str
    account: str

    def __post_init__(self):
        if self.venue not in {"kis", "hyperliquid"} or not self.account.strip():
            raise ValueError("A supported venue and account are required")
        if self.environment not in (
            {"live", "sim"} if self.venue == "kis" else {"mainnet", "testnet"}
        ):
            raise ValueError("Explicit account environment required")

    @property
    def key(self):
        return hashlib.sha256(
            encode([self.venue, self.environment, self.account.lower()]).encode()
        ).hexdigest()


@dataclass(frozen=True)
class Fill:
    execution_id: str
    symbol: str
    time_ms: int
    side: str
    quantity: str
    price: str
    currency: str
    fee: str | None = None
    order_id: str = ""
    position_before: str | None = None
    strategy: str = "unassigned"
    origin: str = "unknown"
    strategy_version: str = ""
    harness: str = "unknown"
    signal_id: str = ""

    def validate(self):
        if any(
            not isinstance(x, str) or not x.strip()
            for x in [
                self.execution_id,
                self.symbol,
                self.currency,
                self.strategy,
                self.origin,
            ]
        ):
            raise ValueError("Execution identity, instrument and currency required")
        if self.side not in {"buy", "sell"}:
            raise ValueError("Invalid fill side")
        if type(self.time_ms) is not int or self.time_ms < 0:
            raise ValueError("Invalid execution timestamp")
        decimal(self.quantity, positive=True)
        decimal(self.price, positive=True)
        if self.fee is not None:
            decimal(self.fee)
        if self.position_before is not None:
            decimal(self.position_before)
        if self.origin not in {"agent", "HTS", "web", "other", "unknown"}:
            raise ValueError("Invalid evidenced origin")
        if not self.strategy:
            raise ValueError("Use unassigned for unknown strategy")


class JournalLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS journal_source_fills (
                scope TEXT NOT NULL, execution_id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, source TEXT NOT NULL, imported_ms INTEGER NOT NULL,
                PRIMARY KEY(scope, execution_id, revision));
            CREATE TABLE IF NOT EXISTS journal_sync_runs (
                id INTEGER PRIMARY KEY, scope TEXT NOT NULL, start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL, complete INTEGER NOT NULL, costs_complete INTEGER NOT NULL,
                source TEXT NOT NULL, reason TEXT NOT NULL, imported_ms INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS journal_cash_costs (
                scope TEXT NOT NULL, event_id TEXT NOT NULL, symbol TEXT NOT NULL,
                time_ms INTEGER NOT NULL, currency TEXT NOT NULL, amount TEXT NOT NULL,
                source TEXT NOT NULL, PRIMARY KEY(scope,event_id));
            CREATE TABLE IF NOT EXISTS journal_cycles (
                scope TEXT NOT NULL, cycle_key TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL, record_json TEXT NOT NULL,
                stats_json TEXT NOT NULL, created_ms INTEGER NOT NULL,
                PRIMARY KEY(scope,cycle_key,revision));
            CREATE TABLE IF NOT EXISTS journal_sync_schedule (
                scope TEXT PRIMARY KEY, interval_seconds INTEGER NOT NULL DEFAULT 10800,
                last_success_ms INTEGER, next_due_ms INTEGER NOT NULL DEFAULT 0);
            """
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def ingest(
        self,
        scope: Scope,
        fills: Iterable[Fill],
        *,
        start_ms: int,
        end_ms: int,
        source: str,
        complete: bool,
        costs_complete: bool,
        reason: str = "",
        costs: Iterable[dict] = (),
        allow_corrections: bool = False,
        allow_attribution_enrichment: bool = False,
    ):
        if (
            type(start_ms) is not int
            or type(end_ms) is not int
            or not 0 <= start_ms <= end_ms
        ):
            raise ValueError("Invalid history interval")
        if (
            not source.strip()
            or type(complete) is not bool
            or type(costs_complete) is not bool
        ):
            raise ValueError("Explicit source and coverage flags required")
        facts = list(fills)
        for fill in facts:
            fill.validate()
            if not start_ms <= fill.time_ms <= end_ms:
                raise ValueError("Execution falls outside the declared interval")
        now = int(time.time() * 1000)
        inserted = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for fill in facts:
                payload = encode(asdict(fill))
                old = db.execute(
                    "SELECT revision,payload FROM journal_source_fills WHERE scope=? AND execution_id=? ORDER BY revision DESC LIMIT 1",
                    (scope.key, fill.execution_id),
                ).fetchone()
                if old and allow_attribution_enrichment and not allow_corrections:
                    previous, incoming = json.loads(old["payload"]), asdict(fill)
                    unknown = {
                        "strategy": "unassigned",
                        "origin": "unknown",
                        "strategy_version": "",
                        "harness": "unknown",
                        "signal_id": "",
                    }
                    economic_fields = incoming.keys() - unknown.keys()
                    if all(previous[k] == incoming[k] for k in economic_fields):
                        compatible = all(
                            previous[k] == incoming[k]
                            or previous[k] == empty
                            or incoming[k] == empty
                            for k, empty in unknown.items()
                        )
                        if compatible:
                            for k, empty in unknown.items():
                                if incoming[k] == empty:
                                    incoming[k] = previous[k]
                            payload = encode(incoming)
                if old and old["payload"] == payload:
                    continue
                if (
                    old
                    and not allow_corrections
                    and not (
                        allow_attribution_enrichment
                        and all(previous[k] == incoming[k] for k in economic_fields)
                        and compatible
                    )
                ):
                    raise ValueError(
                        "Conflicting execution requires explicit correction import"
                    )
                rev = old["revision"] + 1 if old else 1
                db.execute(
                    "INSERT INTO journal_source_fills VALUES (?,?,?,?,?,?)",
                    (scope.key, fill.execution_id, rev, payload, source, now),
                )
                inserted += 1
            for cost in costs:
                for field in ["event_id", "symbol", "currency"]:
                    if not cost.get(field):
                        raise ValueError("Cost identity is required")
                if (
                    type(cost["time_ms"]) is not int
                    or not start_ms <= cost["time_ms"] <= end_ms
                ):
                    raise ValueError("Cost outside history interval")
                amount = str(decimal(cost["amount"]))
                values = (
                    scope.key,
                    cost["event_id"],
                    cost["symbol"],
                    cost["time_ms"],
                    cost["currency"],
                    amount,
                    source,
                )
                old = db.execute(
                    "SELECT symbol,time_ms,currency,amount FROM journal_cash_costs WHERE scope=? AND event_id=?",
                    values[:2],
                ).fetchone()
                if old and tuple(old) != values[2:6]:
                    raise ValueError(
                        "Conflicting cost needs a separately identified correction event"
                    )
                db.execute(
                    "INSERT OR IGNORE INTO journal_cash_costs VALUES (?,?,?,?,?,?,?)",
                    values,
                )
            db.execute(
                "INSERT INTO journal_sync_runs(scope,start_ms,end_ms,complete,costs_complete,source,reason,imported_ms) VALUES(?,?,?,?,?,?,?,?)",
                (
                    scope.key,
                    start_ms,
                    end_ms,
                    int(complete),
                    int(costs_complete),
                    source,
                    reason,
                    now,
                ),
            )
            self._reconcile(db, scope, now)
        return {"inserted_fills": inserted, **self.status(scope)}

    def _fills(self, db, scope):
        rows = db.execute(
            """SELECT f.payload FROM journal_source_fills f
            WHERE f.scope=? AND f.revision=(SELECT MAX(x.revision) FROM journal_source_fills x
            WHERE x.scope=f.scope AND x.execution_id=f.execution_id)""",
            (scope.key,),
        ).fetchall()
        return sorted((Fill(**json.loads(r[0])) for r in rows), key=lambda f: f.time_ms)

    @staticmethod
    def _ordered(events):
        """Equal timestamps need position continuity; identifiers are not sequences."""
        from itertools import groupby

        position = Decimal(0)
        for _, group in groupby(events, key=lambda f: f.time_ms):
            remaining = list(group)
            ambiguous = False
            while remaining:
                candidates = [
                    f
                    for f in remaining
                    if f.position_before is not None
                    and decimal(f.position_before) == position
                ]
                if len(remaining) > 1 and len(candidates) != 1:
                    ambiguous = True
                f = candidates[0] if len(candidates) == 1 else remaining[0]
                remaining.remove(f)
                yield f, (
                    "Ambiguous equal-time execution chronology" if ambiguous else ""
                )
                if f.position_before is not None:
                    position = decimal(f.position_before)
                position += decimal(f.quantity) * (1 if f.side == "buy" else -1)

    def _coverage(self, db, scope, *, costs=False):
        rows = db.execute(
            "SELECT start_ms,end_ms FROM journal_sync_runs WHERE scope=? AND complete=1"
            + (" AND costs_complete=1" if costs else "")
            + " ORDER BY start_ms,end_ms",
            (scope.key,),
        ).fetchall()
        merged = []
        for start, end in rows:
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        return merged

    def _reconcile(self, db, scope, now):
        fills = self._fills(db, scope)
        coverage = self._coverage(db, scope)
        cost_coverage = self._coverage(db, scope, costs=True)
        groups = {}
        for fill in fills:
            groups.setdefault((fill.symbol, fill.currency), []).append(fill)
        cycles = []
        for (symbol, currency), events in groups.items():
            pos = Decimal(0)
            cycle = None
            known = False
            broken = ""
            for f, ordering_reason in self._ordered(events):
                before = (
                    decimal(f.position_before)
                    if f.position_before is not None
                    else None
                )
                if before is not None:
                    if not known and before == 0:
                        if cycle:
                            cycle["reason"] = (
                                cycle["reason"] or "Missing opening history"
                            )
                            cycles.append(cycle)
                            cycle = None
                        known = True
                        broken = ""
                        pos = Decimal(0)
                    elif known and before != pos:
                        broken = "Position history discontinuity"
                if not known:
                    broken = "Missing opening history"
                if ordering_reason:
                    broken = ordering_reason
                signed = decimal(f.quantity) * (1 if f.side == "buy" else -1)
                remaining = abs(signed)
                fee_unit = decimal(f.fee) / remaining if f.fee is not None else None
                part = 0
                while remaining:
                    if pos == 0:
                        cycle = dict(
                            key=f.execution_id + ":" + str(part),
                            symbol=symbol,
                            currency=currency,
                            opened=f.time_ms,
                            closed=None,
                            direction=1 if signed > 0 else -1,
                            entry_q=Decimal(0),
                            entry_value=Decimal(0),
                            exit_q=Decimal(0),
                            exit_value=Decimal(0),
                            fees=Decimal(0),
                            strategies=set(),
                            missing_fee=False,
                            reason=broken,
                        )
                    adding = pos == 0 or (pos > 0) == (signed > 0)
                    qty = remaining if adding else min(abs(pos), remaining)
                    prefix = "entry" if adding else "exit"
                    cycle[prefix + "_q"] += qty
                    cycle[prefix + "_value"] += qty * decimal(f.price)
                    cycle["strategies"].add(f.strategy)
                    cycle["missing_fee"] |= fee_unit is None
                    if fee_unit is not None:
                        cycle["fees"] += qty * fee_unit
                    if broken:
                        cycle["reason"] = broken
                    pos += qty * (1 if signed > 0 else -1)
                    remaining -= qty
                    if pos == 0:
                        cycle["closed"] = f.time_ms
                        cycles.append(cycle)
                        cycle = None
                    part += 1
            if cycle:
                cycles.append(cycle)
        current_keys = set()
        prepared = []
        for c in cycles:
            key = hashlib.sha256(
                encode([c["symbol"], c["currency"], c["key"]]).encode()
            ).hexdigest()
            current_keys.add(key)
            reason = c["reason"]
            record = {}
            if c["closed"] is None:
                status = "OPEN" if not reason else "JOURNAL_PENDING"
                reason = reason or "Position remains open"
            else:
                covered = any(
                    a <= c["opened"] and b >= c["closed"] for a, b in coverage
                )
                costs_ok = any(
                    a <= c["opened"] and b >= c["closed"] for a, b in cost_coverage
                )
                if not covered:
                    reason = reason or "Incomplete execution coverage"
                if not costs_ok or c["missing_fee"]:
                    reason = reason or "Missing reconciled costs"
                if c["entry_q"] != c["exit_q"]:
                    reason = reason or "Quantity does not close"
                # Existing manual records need explicit operator linkage before automation.
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_journal_entries'"
                ).fetchone():
                    legacy = db.execute(
                        "SELECT 1 FROM trade_journal_entries WHERE symbol=? AND opened_at_ms<=? AND closed_at_ms>=? LIMIT 1",
                        (c["symbol"], c["closed"], c["opened"]),
                    ).fetchone()
                    if legacy:
                        reason = (
                            reason
                            or "Possible overlap with legacy manual journal; review required"
                        )
                status = "JOURNAL_PENDING" if reason else "FINALIZED"
                if not reason:
                    cash_costs = db.execute(
                        "SELECT currency,amount FROM journal_cash_costs WHERE scope=? AND symbol=? AND time_ms>? AND time_ms<=?",
                        (scope.key, c["symbol"], c["opened"], c["closed"]),
                    ).fetchall()
                    if any(r["currency"] != c["currency"] for r in cash_costs):
                        status, reason = (
                            "JOURNAL_PENDING",
                            "Cost currency needs explicit conversion",
                        )
                    else:
                        fees = c["fees"] + sum(
                            (decimal(r["amount"]) for r in cash_costs), Decimal(0)
                        )
                        strategies = c["strategies"]
                        strategy = (
                            next(iter(strategies)) if len(strategies) == 1 else "mixed"
                        )
                        record = asdict(
                            create_trade_journal_record(
                                venue=scope.venue,
                                symbol=c["symbol"],
                                strategy=strategy,
                                side="long" if c["direction"] > 0 else "short",
                                opened_at_ms=c["opened"],
                                closed_at_ms=c["closed"],
                                entry_price=c["entry_value"] / c["entry_q"],
                                exit_price=c["exit_value"] / c["exit_q"],
                                quantity=c["entry_q"],
                                fees=fees,
                                notes="Actual execution ledger; origin and strategy are not inferred.",
                            )
                        )
                        record.update(
                            currency=c["currency"],
                            account_scope=scope.key,
                            environment=scope.environment,
                        )
            body = encode(
                record
                or {
                    "symbol": c["symbol"],
                    "currency": c["currency"],
                    "opened_at_ms": c["opened"],
                }
            )
            prepared.append((key, status, reason, body, record))
        # Compute new snapshots from the entire effective replacement set, never old boundaries.
        for key, status, reason, body, record in prepared:
            old = db.execute(
                "SELECT * FROM journal_cycles WHERE scope=? AND cycle_key=? ORDER BY revision DESC LIMIT 1",
                (scope.key, key),
            ).fetchone()
            if old and (old["status"], old["reason"], old["record_json"]) == (
                status,
                reason,
                body,
            ):
                continue
            rev = old["revision"] + 1 if old else 1
            effective = [
                r
                for _, s, _, _, r in prepared
                if s == "FINALIZED"
                and r["strategy"] == record.get("strategy")
                and r["currency"] == record.get("currency")
            ]
            stats = asdict(calculate_trade_journal_stats(effective))
            db.execute(
                "INSERT INTO journal_cycles VALUES(?,?,?,?,?,?,?,?)",
                (scope.key, key, rev, status, reason, body, encode(stats), now),
            )
        # Corrections may remove a previously inferred cycle boundary: retain its old revision.
        rows = db.execute(
            "SELECT cycle_key,MAX(revision) AS revision FROM journal_cycles WHERE scope=? GROUP BY cycle_key",
            (scope.key,),
        ).fetchall()
        for row in rows:
            if row["cycle_key"] not in current_keys:
                old = db.execute(
                    "SELECT * FROM journal_cycles WHERE scope=? AND cycle_key=? AND revision=?",
                    (scope.key, row["cycle_key"], row["revision"]),
                ).fetchone()
                if old["status"] != "SUPERSEDED":
                    db.execute(
                        "INSERT INTO journal_cycles VALUES(?,?,?,?,?,?,?,?)",
                        (
                            scope.key,
                            row["cycle_key"],
                            row["revision"] + 1,
                            "SUPERSEDED",
                            "Source correction changed cycle boundary",
                            old["record_json"],
                            old["stats_json"],
                            now,
                        ),
                    )

    def _current(self, db, scope):
        return db.execute(
            """SELECT c.* FROM journal_cycles c WHERE c.scope=? AND c.revision=(
            SELECT MAX(x.revision) FROM journal_cycles x WHERE x.scope=c.scope AND x.cycle_key=c.cycle_key)""",
            (scope.key,),
        ).fetchall()

    def _entries(self, db, scope):
        return [
            {
                **json.loads(r["record_json"]),
                "cycle_key": r["cycle_key"],
                "revision": r["revision"],
                "stats_json": json.loads(r["stats_json"]),
            }
            for r in self._current(db, scope)
            if r["status"] == "FINALIZED"
        ]

    def entries(self, scope):
        with self.connect() as db:
            return self._entries(db, scope)

    def status(self, scope):
        with self.connect() as db:
            intervals = self._coverage(db, scope)
            rows = self._current(db, scope)
            costs = self._coverage(db, scope, costs=True)
            gaps = [
                dict(r)
                for r in db.execute(
                    "SELECT start_ms,end_ms,reason FROM journal_sync_runs WHERE scope=? AND (complete=0 OR costs_complete=0) ORDER BY id DESC",
                    (scope.key,),
                )
                if not any(a <= r["start_ms"] and b >= r["end_ms"] for a, b in costs)
            ]
            snapshots = 0
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='journal_source_snapshots'"
            ).fetchone():
                snapshots = db.execute(
                    "SELECT COUNT(*) FROM journal_source_snapshots WHERE scope=?",
                    (scope.key,),
                ).fetchone()[0]
            return {
                "account_scope": scope.key,
                "venue": scope.venue,
                "environment": scope.environment,
                "fill_count": len(self._fills(db, scope)),
                "coverage": intervals,
                "covered_until_ms": intervals[0][1] if intervals else None,
                "cost_coverage": costs,
                "reconciled_until_ms": costs[0][1] if costs else None,
                "unresolved_intervals": gaps,
                "source_snapshot_count": snapshots,
                "pending": [
                    {
                        "cycle_key": r["cycle_key"],
                        "status": r["status"],
                        "reason": r["reason"],
                        **json.loads(r["record_json"]),
                    }
                    for r in rows
                    if r["status"] in {"OPEN", "JOURNAL_PENDING"}
                ],
                "finalized_count": sum(r["status"] == "FINALIZED" for r in rows),
            }

    def report(self, scope, *, strategy=None):
        entries = [
            r
            for r in self.entries(scope)
            if strategy is None or r["strategy"] == strategy
        ]
        groups = {}
        for r in entries:
            groups.setdefault((r["currency"], r["strategy"]), []).append(r)
        return {
            "entries": entries,
            "groups": [
                {
                    "currency": currency,
                    "strategy": name,
                    "realized_pnl": str(
                        sum((decimal(x["realized_pnl"]) for x in records), Decimal(0))
                    ),
                    "statistics": asdict(calculate_trade_journal_stats(records)),
                }
                for (currency, name), records in groups.items()
            ],
            "sync": self.status(scope),
        }

    def reconcile_holdings(self, scope, holdings, *, now_ms):
        """Compare current quantities without inventing transfers or changing historical fills."""
        actual = {symbol: decimal(qty) for symbol, qty in holdings.items()}
        with self.connect() as db:
            expected = {}
            unknown = set()
            for f in self._fills(db, scope):
                if f.symbol not in expected:
                    expected[f.symbol] = (
                        decimal(f.position_before)
                        if f.position_before is not None
                        else Decimal(0)
                    )
                    if f.position_before is None:
                        unknown.add(f.symbol)
                if (
                    f.position_before is not None
                    and decimal(f.position_before) != expected[f.symbol]
                ):
                    unknown.add(f.symbol)
                expected[f.symbol] += decimal(f.quantity) * (
                    1 if f.side == "buy" else -1
                )
            rows = [
                {
                    "symbol": symbol,
                    "ledger_quantity": str(expected.get(symbol, 0)),
                    "venue_quantity": str(actual.get(symbol, 0)),
                    "matched": symbol not in unknown
                    and expected.get(symbol, 0) == actual.get(symbol, 0),
                }
                for symbol in sorted(set(actual) | set(expected))
            ]
            result = {
                "account_scope": scope.key,
                "observed_ms": now_ms,
                "positions": rows,
                "matched": all(x["matched"] for x in rows),
                "note": "Quantity agreement is not proof of complete history. Review transfers, corporate actions and gaps separately.",
            }
            db.execute(
                "CREATE TABLE IF NOT EXISTS journal_position_checks(id INTEGER PRIMARY KEY,scope TEXT,time_ms INTEGER,payload TEXT)"
            )
            db.execute(
                "INSERT INTO journal_position_checks(scope,time_ms,payload) VALUES(?,?,?)",
                (scope.key, now_ms, encode(result)),
            )
        return result


class SyncSchedule:
    def __init__(self, store: JournalLedger, scope: Scope):
        self.store, self.scope = store, scope
        with store.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO journal_sync_schedule(scope) VALUES(?)",
                (scope.key,),
            )

    def settings(self):
        with self.store.connect() as db:
            return dict(
                db.execute(
                    "SELECT * FROM journal_sync_schedule WHERE scope=?",
                    (self.scope.key,),
                ).fetchone()
            )

    def configure(self, seconds: int, *, now_ms: int):
        if type(seconds) is not int or seconds <= 0:
            raise ValueError("Sync interval must be a positive integer in seconds")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT last_success_ms FROM journal_sync_schedule WHERE scope=?",
                (self.scope.key,),
            ).fetchone()[0]
            due = (old + seconds * 1000) if old is not None else now_ms
            db.execute(
                "UPDATE journal_sync_schedule SET interval_seconds=?,next_due_ms=? WHERE scope=?",
                (seconds, due, self.scope.key),
            )
        return self.settings()

    def due(self, now_ms):
        return now_ms >= self.settings()["next_due_ms"]

    def success(self, now_ms):
        with self.store.connect() as db:
            db.execute(
                "UPDATE journal_sync_schedule SET last_success_ms=?,next_due_ms=?+interval_seconds*1000 WHERE scope=?",
                (now_ms, now_ms, self.scope.key),
            )
