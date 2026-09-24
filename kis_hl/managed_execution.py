"""Durable long-entry protection coordinated by one local account supervisor."""

from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from kis_hl.execution_lock import account_lock
from kis_hl.journal_sync import decimal, encode
from kis_hl.trailing import Trail
from kis_hl.hyperliquid.trailing import normalize_quote_retracement, wire_decimal

TERMINAL = {"filled", "canceled", "rejected", "expired"}
FINISHED = {"CLOSED", "REJECTED", "PREVIEWED"}
_entry_permit = ContextVar("managed_entry_permit", default=None)


@contextmanager
def entry_permit(scope, instrument_id, attempt_id):
    token = _entry_permit.set((scope, instrument_id, attempt_id))
    try:
        yield
    finally:
        _entry_permit.reset(token)


def guard_external_entry(path, *, scope, instrument_id, attempt_id=None):
    if path is None:
        return
    path = Path(path)
    if not path.exists():
        return
    with sqlite3.connect(path) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='managed_positions'"
        ).fetchone():
            return
        row = db.execute(
            "SELECT id FROM managed_positions WHERE scope=? AND instrument=? AND mode='live' AND state NOT IN ('CLOSED','REJECTED','PREVIEWED')",
            (scope, instrument_id),
        ).fetchone()
    if row and _entry_permit.get() != (scope, instrument_id, attempt_id):
        raise RuntimeError(
            "Managed position blocks external entry or enrollment until cleanup"
        )


def validate_plan(plan, now_ms):
    required = {
        "intent_id",
        "instrument",
        "signal_instrument",
        "strategy",
        "strategy_version",
        "quantity",
        "limit_price",
        "atr",
        "atr_multiple",
        "max_notional",
        "max_loss",
        "max_quote_age_ms",
        "protection_grace_ms",
        "max_exit_attempts",
        "exit_deadline_ms",
        "slippage",
        "allow_local_sl",
        "expires_ms",
        "exit_reprice_ms",
        "max_portfolio_notional",
        "max_correlated_notional",
        "max_spread_bps",
        "max_entry_deviation_bps",
    }
    if not isinstance(plan, dict) or not required <= plan.keys():
        raise ValueError("Trade plan is missing required risk or identity fields")
    for key in (
        "intent_id",
        "instrument",
        "signal_instrument",
        "strategy",
        "strategy_version",
    ):
        if not isinstance(plan[key], str) or not plan[key].strip():
            raise ValueError("Trade identity required")
    for key in (
        "quantity",
        "limit_price",
        "atr",
        "atr_multiple",
        "max_notional",
        "max_loss",
        "max_portfolio_notional",
        "max_correlated_notional",
        "max_spread_bps",
        "max_entry_deviation_bps",
    ):
        decimal(plan[key], positive=True)
    for key in (
        "max_quote_age_ms",
        "protection_grace_ms",
        "max_exit_attempts",
        "exit_deadline_ms",
        "expires_ms",
        "exit_reprice_ms",
    ):
        if type(plan[key]) is not int or plan[key] <= 0:
            raise ValueError("Positive integer risk budgets required")
    if type(plan["allow_local_sl"]) is not bool:
        raise ValueError("Local SL fallback must be explicit")
    if plan["instrument"].startswith("kis:"):
        if "verified_price_step" not in plan:
            raise ValueError("KIS plans require verified_price_step")
        decimal(plan["verified_price_step"], positive=True)
    if not 0 < decimal(plan["slippage"]) < 1:
        raise ValueError("Slippage must be between zero and one")
    if plan["expires_ms"] <= now_ms:
        raise ValueError("Trade plan has expired")
    quantity, price = decimal(plan["quantity"]), decimal(plan["limit_price"])
    distance = (price - decimal(plan["fixed_stop_price"], positive=True)
                if "fixed_stop_price" in plan
                else decimal(plan["atr"]) * decimal(plan["atr_multiple"]))
    if (
        distance <= 0 or distance >= price
        or quantity * distance > decimal(plan["max_loss"])
        or quantity * price > decimal(plan["max_notional"])
    ):
        raise ValueError(
            "Plan exceeds loss/notional limits or has an invalid initial stop"
        )
    for key in ("local_atr_multiple", "native_atr_multiple"):
        if key in plan:
            decimal(plan[key], positive=True)
    if decimal(plan["atr"]) * decimal(plan.get("local_atr_multiple", plan["atr_multiple"])) >= price:
        raise ValueError("Local trailing distance must leave a positive initial threshold")
    provider = plan.get("trailing_provider", "native" if plan["instrument"].startswith("hl:") else "local")
    if provider not in {"local", "native"}:
        raise ValueError("trailing_provider must be local or native")
    if provider == "native":
        from kis_hl.instruments import instrument
        asset = instrument(plan["instrument"])
        if asset.venue != "hyperliquid" or asset.market != "perp":
            raise ValueError("Native trailing is available only for Hyperliquid perpetuals")
    backup = plan.get("local_trailing_backup", provider == "native")
    if type(backup) is not bool or (backup and provider != "native"):
        raise ValueError("local_trailing_backup requires a native provider and a boolean")
    # No signal price is copied into execution pricing.
    return {**plan, "stop_distance": str(distance), "trailing_provider": provider, "local_trailing_backup": backup}


class ExecutionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS managed_positions(id TEXT PRIMARY KEY,scope TEXT NOT NULL,
                instrument TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,
                version INTEGER NOT NULL,snapshot TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS managed_owner ON managed_positions(scope,instrument,mode)
                WHERE state NOT IN ('CLOSED','REJECTED','PREVIEWED');
            CREATE TABLE IF NOT EXISTS managed_attempts(id TEXT PRIMARY KEY,position_id TEXT NOT NULL,
                kind TEXT NOT NULL,status TEXT NOT NULL,snapshot TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS managed_events(id INTEGER PRIMARY KEY,position_id TEXT NOT NULL,
                time_ms INTEGER NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS managed_supervisors(scope TEXT PRIMARY KEY,heartbeat_ms INTEGER,
                mode TEXT NOT NULL,entries_enabled INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS managed_intents(scope TEXT NOT NULL,mode TEXT NOT NULL,
                intent_id TEXT NOT NULL,position_id TEXT NOT NULL,PRIMARY KEY(scope,mode,intent_id));
            CREATE TABLE IF NOT EXISTS managed_tranches(id TEXT PRIMARY KEY,position_id TEXT NOT NULL,
                snapshot TEXT NOT NULL);
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

    def enqueue(self, scope, plan, *, live=False, now_ms, adoption=None):
        if plan.get("action") == "add" or plan.get("position_id"):
            raise ValueError("Use signal execute with bounded add authority")
        p = validate_plan(plan, now_ms)
        row = {
            "id": uuid4().hex,
            "scope": scope,
            "mode": "live" if live else "paper",
            "plan": p,
            "state": "QUEUED",
            "reason": "Awaiting supervisor preflight",
            "created_ms": now_ms,
            "version": 0,
            "trail": None,
            "first_fill_ms": None,
            "exit_requested_ms": None,
            "cancel_entry": False,
            "entry_filled": "0",
            "observed_size": "0",
            "covered_size": "0",
        }
        if adoption is not None:
            row.update(state="ADOPTING", reason="Awaiting supervisor handoff validation", adoption=adoption)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM managed_intents WHERE scope=? AND mode=? AND intent_id=?",
                (scope, row["mode"], p["intent_id"]),
            ).fetchone():
                raise RuntimeError("Duplicate intent is already owned or completed")
            try:
                db.execute(
                    "INSERT INTO managed_positions VALUES(?,?,?,?,?,?,?)",
                    (
                        row["id"],
                        scope,
                        p["instrument"],
                        row["mode"],
                        row["state"],
                        0,
                        encode(row),
                    ),
                )
            except sqlite3.IntegrityError:
                raise RuntimeError("Account instrument is already owned") from None
            db.execute(
                "INSERT INTO managed_intents VALUES(?,?,?,?)",
                (scope, row["mode"], p["intent_id"], row["id"]),
            )
        return row

    def tranches(self, position_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT snapshot FROM managed_tranches WHERE position_id=? ORDER BY rowid", (position_id,))]

    def save_tranche(self, tranche):
        with self.connect() as db:
            db.execute("UPDATE managed_tranches SET snapshot=? WHERE id=?", (encode(tranche), tranche["id"]))

    def enqueue_add(self, owner, plan, *, now_ms, sizing):
        tranche = dict(id=uuid4().hex, position_id=owner["id"], plan=plan,
                       status="QUEUED", created_ms=now_ms, filled="0", sizing=sizing)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT version FROM managed_positions WHERE id=?", (owner["id"],)).fetchone()
            if current is None or current[0] != owner["version"]:
                raise RuntimeError("Position changed before add authorization")
            if any(t["status"] in {"QUEUED", "SUBMITTED", "UNKNOWN"} for t in self.tranches(owner["id"])):
                raise ValueError("An add lifecycle is already pending")
            db.execute("INSERT INTO managed_intents VALUES(?,?,?,?)",
                       (owner["scope"], owner["mode"], plan["intent_id"], owner["id"]))
            db.execute("INSERT INTO managed_tranches VALUES(?,?,?)", (tranche["id"], owner["id"], encode(tranche)))
        return tranche

    def enqueue_adoption(self, scope, plan, *, entry_order_id, stop_order_id, live=False, now_ms):
        from kis_hl.instruments import instrument
        asset = instrument(plan["instrument"])
        if asset.venue != "hyperliquid" or asset.market != "perp":
            raise ValueError("Adoption supports Hyperliquid perpetuals only")
        if (any(type(x) is not int or x <= 0 for x in (entry_order_id, stop_order_id))
                or entry_order_id == stop_order_id or plan.get("signal_id") or plan.get("grant_id")):
            raise ValueError("Adoption requires distinct native IDs and direct management authority")
        return self.enqueue(scope, plan, live=live, now_ms=now_ms,
                            adoption={"entry_order_id":entry_order_id, "stop_order_id":stop_order_id})

    def complete_adoption(self, row, updates, attempts, now_ms):
        new = {**row, **updates, "version":row["version"]+1}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM managed_attempts WHERE position_id=?", (row["id"],)).fetchone():
                raise RuntimeError("Adoption already has owned attempts")
            owned_ids = {a["order_id"] for a in attempts}
            for prior in db.execute("SELECT a.snapshot FROM managed_attempts a JOIN managed_positions p ON p.id=a.position_id WHERE p.scope=? AND p.mode=?", (row["scope"],row["mode"])):
                if str(json.loads(prior[0]).get("order_id")) in owned_ids:
                    raise ValueError("Native order already belongs to another managed generation")
            changed = db.execute("UPDATE managed_positions SET state=?,version=?,snapshot=? WHERE id=? AND version=?",
                                 (new["state"],new["version"],encode(new),row["id"],row["version"]))
            if changed.rowcount != 1:
                raise RuntimeError("Adoption changed; reload before importing ownership")
            for a in attempts:
                db.execute("INSERT INTO managed_attempts VALUES(?,?,?,?,?)",
                           (a["id"],row["id"],a["kind"],a["status"],encode(a)))
            db.execute("INSERT INTO managed_events(position_id,time_ms,state,reason) VALUES(?,?,?,?)",
                       (row["id"],now_ms,new["state"],new["reason"]))
        row.update(new)

    def get(self, position_id):
        with self.connect() as db:
            r = db.execute(
                "SELECT snapshot FROM managed_positions WHERE id=?", (position_id,)
            ).fetchone()
        if not r:
            raise ValueError("Unknown managed position")
        return json.loads(r[0])

    def list(self, scope=None):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT snapshot FROM managed_positions"
                    + (" WHERE scope=?" if scope else ""),
                    (scope,) if scope else (),
                )
            ]

    def save(self, row, now_ms=0):
        new = {**row, "version": row["version"] + 1}
        with self.connect() as db:
            changed = db.execute(
                "UPDATE managed_positions SET state=?,version=?,snapshot=? WHERE id=? AND version=?",
                (new["state"], new["version"], encode(new), row["id"], row["version"]),
            )
            if changed.rowcount != 1:
                raise RuntimeError("Managed position changed; reload")
            db.execute(
                "INSERT INTO managed_events(position_id,time_ms,state,reason) VALUES(?,?,?,?)",
                (row["id"], now_ms, new["state"], new["reason"]),
            )
        row.update(new)

    def attempts(self, position_id):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT snapshot FROM managed_attempts WHERE position_id=? ORDER BY rowid",
                    (position_id,),
                )
            ]

    def attempt(self, row, kind, now_ms, **values):
        attempt = {
            "id": "0x" + uuid4().hex,
            "position_id": row["id"],
            "kind": kind,
            "status": "UNKNOWN",
            "created_ms": now_ms,
            **values,
        }
        with self.connect() as db:
            db.execute(
                "INSERT INTO managed_attempts VALUES(?,?,?,?,?)",
                (attempt["id"], row["id"], kind, "UNKNOWN", encode(attempt)),
            )
        return attempt

    def update_attempt(self, attempt, **values):
        attempt.update(values)
        with self.connect() as db:
            db.execute(
                "UPDATE managed_attempts SET status=?,snapshot=? WHERE id=?",
                (attempt["status"], encode(attempt), attempt["id"]),
            )

    def request_exit(self, position_id, now_ms, *, cancel_only=False):
        row = self.get(position_id)
        if row["state"] in FINISHED:
            return row
        if cancel_only:
            row["cancel_entry"] = True
        else:
            row["exit_requested_ms"] = row["exit_requested_ms"] or now_ms
        self.save(row, now_ms)
        return row

    def heartbeat(self, scope, now_ms, live):
        with self.connect() as db:
            db.execute(
                "INSERT INTO managed_supervisors(scope,heartbeat_ms,mode) VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET heartbeat_ms=excluded.heartbeat_ms,mode=excluded.mode",
                (scope, now_ms, "live" if live else "paper"),
            )

    def entries_enabled(self, scope):
        with self.connect() as db:
            r = db.execute(
                "SELECT entries_enabled FROM managed_supervisors WHERE scope=?",
                (scope,),
            ).fetchone()
        return r is None or bool(r[0])

    def set_entries(self, scope, enabled):
        with self.connect() as db:
            db.execute(
                "INSERT INTO managed_supervisors(scope,heartbeat_ms,mode,entries_enabled) VALUES(?,0,'paper',?) ON CONFLICT(scope) DO UPDATE SET entries_enabled=excluded.entries_enabled",
                (scope, int(enabled)),
            )


class Supervisor:
    def __init__(self, store, gateway, *, live=False):
        self.store, self.gateway, self.live = store, gateway, live
        self.seen = set()

    def _state(self, row, state, reason, now, *, preserve_native_intervention=False):
        if state == "INTERVENTION" and not preserve_native_intervention:
            row.pop("native_trailing_intervention", None)
        row.update(state=state, reason=reason)
        self.store.save(row, now)

    def _send(self, row, kind, now, **values):
        # Persist triggering decisions before any external effect, including cancellations.
        self.store.save(row, now)
        a = self.store.attempt(row, kind, now, **values)
        if kind in {"entry", "add"} and not self.store.entries_enabled(row["scope"]):
            self.store.update_attempt(
                a, status="REJECTED", reason="Entries disabled before transmission"
            )
            if kind == "entry":
                self._state(row, "REJECTED", "Entry kill switch applied before transmission", now)
            return a
        try:
            result = (
                self.gateway.cancel(row, a)
                if kind == "cancel"
                else self.gateway.submit(row, a)
            )
            status = {"rejected": "REJECTED", "unknown": "UNKNOWN"}.get(result.get("status"), "SUBMITTED")
            self.store.update_attempt(
                a,
                status=status,
                order_id=result.get("order_id"),
                organization_id=result.get("organization_id", ""),
            )
        except Exception:
            # The persisted UNKNOWN remains authoritative, including process death before acknowledgement.
            pass
        return a

    def step(self, position_id, now_ms):
        with account_lock(self.gateway.network, self.gateway.account):
            self.store.heartbeat(self.gateway.scope, now_ms, self.live)
            row = self.store.get(position_id)
            if (
                row["scope"] != self.gateway.scope
                or (row["mode"] == "live") != self.live
            ):
                raise ValueError("Supervisor account/mode mismatch")
            if row["state"] in FINISHED:
                return row
            if position_id not in self.seen:
                if row["trail"]:
                    trail = Trail.from_dict(row["trail"])
                    trail.disconnect()
                    row["trail"] = trail.to_dict()
                self.seen.add(position_id)
            try:
                self._step(row, now_ms)
            except (
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                OSError,
                IndexError,
                StopIteration,
            ):
                current = self.store.get(position_id)
                if current["version"] == row["version"]:
                    row.pop("read_failure_exit", None)
                    row.pop("native_trailing_intervention", None)
                    self._state(
                        row,
                        "INTERVENTION",
                        "Preflight or reconciliation failed; inspect source state",
                        now_ms,
                    )
                # Concurrent control requests win; reload on the next supervisor iteration.
            return self.store.get(position_id)

    def _step(self, row, now):
        p = row["plan"]
        attempts = self.store.attempts(row["id"])
        native_trailing = p.get("trailing_provider", "local") == "native"
        if row.get("adoption") and not row.get("adopted_ms"):
            if row["cancel_entry"] or row["exit_requested_ms"] is not None:
                self._state(row, "CLOSED", "Handoff canceled; external position and orders unchanged", now)
                return
            if row["state"] != "ADOPTING":
                return
            validate_plan(p, now)
            if not self.live:
                self._state(row, "PREVIEWED", "Paper handoff; no account reads or ownership imported", now)
                return
            from kis_hl.manual_adoption import verify_adoption
            try:
                updates, imported = verify_adoption(self.gateway, row, now)
            except ValueError as exc:
                if str(exc).startswith("migration-required:"):
                    self._state(row, "INTERVENTION", str(exc), now)
                    return
                raise
            self.store.complete_adoption(row, updates, imported, now)
            return
        if row["state"] == "ENTERING" and not attempts:
            # Every network write is preceded by an attempt commit; none means unsent.
            self._state(
                row,
                "QUEUED",
                "Restart found no submitted attempt; preflight must run again",
                now,
            )
        if row["state"] == "QUEUED":
            if row["cancel_entry"] or row["exit_requested_ms"] is not None:
                self._state(
                    row, "CLOSED", "Queued entry canceled before submission", now
                )
                return
            validate_plan(p, now)
            if not self.live:
                self._state(
                    row,
                    "PREVIEWED",
                    "Paper plan; no assumed execution or realized journal",
                    now,
                )
                return
            if not self.store.entries_enabled(row["scope"]):
                return
            if any(
                x["id"] != row["id"]
                and x["mode"] == row["mode"]
                and x["state"] not in FINISHED | {"QUEUED", "PROTECTED"}
                for x in self.store.list(row["scope"])
            ):
                self._state(
                    row,
                    "QUEUED",
                    "Other account exposure needs reconciliation before another entry",
                    now,
                )
                return
            snap = self.gateway.preflight(p, now)
            now = int(snap.get("observed_now_ms", now))
            validate_plan(p, now)
            size, price = decimal(p["quantity"]), decimal(p["limit_price"])
            fresh = 0 <= now - int(snap["time_ms"]) <= p["max_quote_age_ms"]
            if (
                not fresh
                or not snap["eligible"]
                or not snap["session_open"]
                or decimal(snap["position"]) != 0
                or snap["open_orders"]
            ):
                raise ValueError("Entry preflight not ready")
            if size * price > decimal(snap["available_notional"]):
                raise ValueError("Insufficient available funds")
            if size * price + decimal(snap["portfolio_notional"]) > decimal(
                p["max_portfolio_notional"]
            ):
                raise ValueError("Portfolio notional limit exceeded")
            if size * price + decimal(snap["correlated_notional"]) > decimal(
                p["max_correlated_notional"]
            ):
                raise ValueError("Correlated notional limit exceeded")
            bid, ask = decimal(snap["price"], positive=True), decimal(
                snap["ask"], positive=True
            )
            if ask < bid or (ask - bid) / bid * 10000 > decimal(p["max_spread_bps"]):
                raise ValueError("Execution spread limit exceeded")
            if abs(price - ask) / ask * 10000 > decimal(p["max_entry_deviation_bps"]):
                raise ValueError("Entry limit is outside the quote band")
            if abs(decimal(snap["atr"]) - decimal(p["atr"])) > decimal(
                p["atr"]
            ) * Decimal("0.000001"):
                raise ValueError(
                    "Plan ATR differs from current execution-instrument history"
                )
            if snap["atr_source"]["instrument"] != p["instrument"]:
                raise ValueError("ATR instrument mismatch")
            if size % decimal(snap["quantity_step"], positive=True) or price % decimal(
                snap["price_step"], positive=True
            ):
                raise ValueError("Invalid order lot/tick")
            if not self.gateway.native_sl and not p["allow_local_sl"]:
                raise ValueError("No protective provider available")
            if native_trailing and not getattr(self.gateway, "native_trailing", False):
                raise ValueError("Native trailing provider unavailable")
            if native_trailing:
                row["native_trailing_distance"] = wire_decimal(normalize_quote_retracement(
                    decimal(p["atr"]) * decimal(p.get("native_atr_multiple", p["atr_multiple"])),
                    decimal(snap["trailing_price_step"])))
            row["baseline"] = snap.get("baseline", {})
            row["baseline_start_ms"] = snap.get("baseline_start_ms", row["created_ms"])
            row["atr_source"] = snap["atr_source"]
            row["providers"] = {
                "stop_loss": "native" if self.gateway.native_sl else "local",
                "trailing": "native" if native_trailing else "local",
                "local_trailing_backup": p.get("local_trailing_backup", False),
            }
            if p.get("signal_id") or p.get("grant_id"):
                from kis_hl.strategy_signals import Signals

                Signals(self.store).check_authority(row, now_ms=now)
            if not self.store.entries_enabled(row["scope"]):
                self._state(row, "QUEUED", "Entries disabled during preflight", now)
                return
            self._state(
                row, "ENTERING", "Intent persisted; fill/protection unconfirmed", now
            )
            self._send(row, "entry", now, quantity=str(size), price=str(price))
            return
        try:
            snap = self.gateway.snapshot(row, attempts, now)
        except (RuntimeError, OSError) as exc:
            row["read_failures"] = row.get("read_failures", 0) + 1
            row.setdefault("read_failure_since_ms", now)
            existing_intervention = row["state"] == "INTERVENTION" and not row.get(
                "read_failure_exit"
            )
            exhausted = (
                row["read_failures"] >= 3
                or now - row["read_failure_since_ms"] >= p["protection_grace_ms"]
            )
            if exhausted and not existing_intervention:
                row["exit_requested_ms"] = row["exit_requested_ms"] or now
                row["read_failure_exit"] = True
            self._state(
                row,
                "INTERVENTION" if existing_intervention or exhausted else "DEGRADED",
                f"Account snapshot unavailable ({type(exc).__name__}); consecutive failures={row['read_failures']}; awaiting readback",
                now,
                preserve_native_intervention=bool(row.get("native_trailing_intervention")),
            )
            return
        row["read_failures"] = 0
        row.pop("read_failure_since_ms", None)
        if row.pop("read_failure_exit", False):
            row["state"] = "EXITING"
        now = int(snap.get("observed_now_ms", now))
        if not snap["consistent"] or snap["foreign_add"]:
            raise ValueError("External ownership or inconsistent exposure")
        size = decimal(snap["size"])
        entry_filled = decimal(snap["entry_filled"])
        added_fills = sum((decimal(snap.get("fills_by_attempt", {}).get(a["id"], "0"))
                          for a in attempts if a["kind"] == "add"), Decimal(0))
        total_authorized = decimal(p["quantity"]) + sum(
            (decimal(a["quantity"]) for a in attempts if a["kind"] == "add"), Decimal(0))
        if (
            size < 0
            or entry_filled < decimal(row["entry_filled"])
            or entry_filled > total_authorized
        ):
            raise ValueError("Unexpected position generation")
        fresh = 0 <= now - int(snap["time_ms"]) <= p["max_quote_age_ms"]
        if not fresh:
            if row["trail"]:
                trail = Trail.from_dict(row["trail"])
                trail.disconnect()
                row["trail"] = trail.to_dict()
        row.update(observed_size=str(size), entry_filled=str(entry_filled))
        protective_filled = decimal(snap.get("protective_filled", "0"))
        if protective_filled > decimal(row.get("protective_filled", "0")):
            row["exit_requested_ms"] = row["exit_requested_ms"] or now
        row["protective_filled"] = str(protective_filled)
        previous_observation = row.get("last_observed_ms", now)
        row["last_observed_ms"] = now
        if (
            size > 0
            and not self.gateway.native_sl
            and now - previous_observation >= p["protection_grace_ms"]
        ):
            row["exit_requested_ms"] = row["exit_requested_ms"] or now
        orders = snap["orders"]
        for a in attempts:
            observed = orders.get(a.get("order_id") or a["id"], {})
            state = observed.get("status")
            if observed.get("native_id") and not a.get("order_id"):
                self.store.update_attempt(a, order_id=observed["native_id"])
            if state in TERMINAL:
                self.store.update_attempt(a, status=state.upper())
            elif state == "open" and a["status"] == "UNKNOWN":
                self.store.update_attempt(a, status="SUBMITTED")
        # An acknowledgement of cancel is not terminal evidence for the original order.
        attempts = self.store.attempts(row["id"])
        for tranche in self.store.tranches(row["id"]):
            attempt = next((a for a in attempts if a.get("tranche_id") == tranche["id"]), None)
            if attempt:
                filled = decimal(snap.get("fills_by_attempt", {}).get(attempt["id"], "0"))
                if filled < decimal(tranche["filled"]) or filled > decimal(attempt["quantity"]):
                    raise ValueError("Inconsistent add tranche fills")
                tranche.update(filled=str(filled), status=attempt["status"], attempt_id=attempt["id"])
                self.store.save_tranche(tranche)
        entry_attempts = [a for a in attempts if a["kind"] in {"entry", "add"}]
        entry_active = [
            a for a in entry_attempts if a["status"].lower() not in TERMINAL
        ]
        stops = [
            a
            for a in attempts
            if a["kind"] in {"stop", "trailing"} and a["status"].lower() not in TERMINAL
        ]
        exits = [a for a in attempts if a["kind"] == "exit"]
        unresolved_exits = [a for a in exits if a["status"].lower() not in TERMINAL]
        if row["state"] == "INTERVENTION" and not (
            native_trailing and row.get("native_trailing_intervention")
        ):
            if size == 0 and not entry_active and not stops and not unresolved_exits:
                self._state(
                    row,
                    "CLOSED",
                    "Reconciliation confirms flat and all owned orders terminal",
                    now,
                )
                return
            if size != 0:
                self.store.save(row, now)
                return
            # Once flat, known owned orders can be canceled even after an exit deadline.
        if size == 0 and entry_filled > 0:
            row["cancel_entry"] = True
        if size == 0 and entry_filled == 0:
            if entry_attempts and not entry_active:
                self._state(row, "CLOSED", "Entry ended without exposure", now)
                return
            if now >= p["expires_ms"]:
                row["cancel_entry"] = True
        if size > 0:
            if row["first_fill_ms"] is None:
                row["first_fill_ms"] = int(snap.get("first_fill_time_ms") or now)
                if not row["created_ms"] <= row["first_fill_ms"] <= now:
                    raise ValueError("Invalid execution time")
            if row["trail"] is None:
                row["trail"] = Trail.create(
                    entry=decimal(snap["entry_price"], positive=True),
                    atr=decimal(p["atr"]),
                    multiple=decimal(p.get("local_atr_multiple", p["atr_multiple"])),
                    opened_ms=now,
                ).to_dict()
            trail = Trail.from_dict(row["trail"])
            # Additional fills may tighten the risk floor but never reset a ratchet.
            fixed_floor = (decimal(row["add_fixed_stop_price"]) if "add_fixed_stop_price" in row
                           else decimal(p["fixed_stop_price"]) if "fixed_stop_price" in p
                           else max(trail.entry, decimal(snap["entry_price"])) - decimal(p["stop_distance"]))
            trail.threshold = max(
                trail.threshold, decimal(snap["entry_price"]) - trail.distance
            )
            if (not native_trailing or p.get("local_trailing_backup", False)) and fresh and trail.tick(
                now,
                decimal(snap["price"], positive=True),
                max_gap_ms=p["max_quote_age_ms"],
            ):
                row["exit_requested_ms"] = row["exit_requested_ms"] or now
            row["trail"] = trail.to_dict()
            if (not self.gateway.native_sl and p["allow_local_sl"] and fresh
                    and decimal(snap["price"], positive=True) <= fixed_floor):
                row["exit_requested_ms"] = row["exit_requested_ms"] or now
            if self.gateway.native_sl:
                covered = Decimal(0)
                for a in stops:
                    if a["kind"] != "stop":
                        continue
                    order = orders.get(a.get("order_id") or a["id"], {})
                    if (
                        order.get("status") == "open"
                        and order.get("kind") == "stop"
                        and order.get("side") == "sell"
                        and order.get("reduce_only") is True
                        and order.get("trigger_type") == "sl"
                        and decimal(order.get("trigger_price", "0"))
                        >= fixed_floor
                    ):
                        covered += decimal(order["size"], positive=True)
                        if a.get("coverage_recorded") != order:
                            from kis_hl.capabilities import CapabilityEvidence

                            CapabilityEvidence(self.store.path).record(
                                row["scope"],
                                p["instrument"],
                                "native_stop_loss",
                                "verified",
                                now_ms=now,
                                expires_ms=now + p["max_quote_age_ms"],
                                evidence="Hyperliquid orderStatus readback",
                                details=order,
                            )
                            self.store.update_attempt(a, coverage_recorded=order)
                row["covered_size"] = str(min(size, covered))
                if covered < size:
                    row.setdefault("unprotected_since_ms", max(row["first_fill_ms"], now)
                                   if added_fills > 0 else row["first_fill_ms"])
                else:
                    row.pop("unprotected_since_ms", None)
                pending_stops = any(
                    not orders.get(a.get("order_id") or a["id"]) for a in stops if a["kind"] == "stop"
                )
                if covered < size and (
                    now - row.get("unprotected_since_ms", row["first_fill_ms"]) >= p["protection_grace_ms"]
                    or len([a for a in attempts if a["kind"] == "stop"
                            and a["created_ms"] >= row.get("unprotected_since_ms", row["first_fill_ms"])])
                    >= p["max_exit_attempts"]
                ):
                    row["exit_requested_ms"] = row["exit_requested_ms"] or now
                if (
                    fresh
                    and covered < size
                    and not pending_stops
                    and not row["exit_requested_ms"]
                ):
                    trigger = (
                        fixed_floor
                        / decimal(snap["price_step"])
                    ).to_integral_value(rounding=ROUND_UP) * decimal(snap["price_step"])
                    execution_price = (
                        trigger
                        * (1 - decimal(p["slippage"]))
                        / decimal(snap["price_step"])
                    ).to_integral_value(rounding=ROUND_UP) * decimal(snap["price_step"])
                    self.store.save(row, now)
                    self._send(
                        row,
                        "stop",
                        now,
                        quantity=str(size - covered),
                        price=str(execution_price),
                        trigger_price=str(trigger),
                    )
                    return
                protected = covered >= size
            else:
                protected = fresh and p["allow_local_sl"] and bool(snap["session_open"])
                row["covered_size"] = str(size if protected else 0)
            row["local_trailing_covered_size"] = str(size if fresh and (
                not native_trailing or p.get("local_trailing_backup", False)) else 0)
            if not protected and now - row.get("unprotected_since_ms", row["first_fill_ms"]) >= p["protection_grace_ms"]:
                row["exit_requested_ms"] = row["exit_requested_ms"] or now
            if native_trailing:
                trails = [a for a in attempts if a["kind"] == "trailing"]
                row["trailing_covered_size"] = "0"
                waiting = False
                terminated_trail = False
                row.pop("native_trailing_intervention", None)
                for a in trails:
                    order = orders.get(a.get("order_id"), {})
                    if not a.get("order_id"):
                        row["native_trailing_intervention"] = True
                        row["state"], row["reason"] = "INTERVENTION", "Native trailing rejected or outcome unknown; retain fixed SL and reconcile manually"
                        continue
                    if a["status"].lower() in TERMINAL:
                        if a["status"].lower() == "filled":
                            row["exit_requested_ms"] = row["exit_requested_ms"] or now
                        else:
                            terminated_trail = True
                        continue
                    if order.get("trailing_readback_error"):
                        row["native_trailing_intervention"] = True
                        row["state"], row["reason"] = "INTERVENTION", "Native trailing condition unverified; retain fixed SL and await valid readback"
                        continue
                    if (order.get("status") == "open" and order.get("kind") == "trailing"
                          and order.get("side") == "sell" and order.get("reduce_only") is True
                          and order.get("retracement_unit") == "quote"
                          and decimal(order.get("retracement", "0")) == decimal(a["retracement"])):
                        order_size = decimal(order["size"], positive=True)
                        waiting |= order.get("active") is False and order_size >= size
                        if order.get("active") is True:
                            row["trailing_covered_size"] = str(max(decimal(row["trailing_covered_size"]), min(size, order_size)))
                # An older terminated trail need not force an exit when another
                # owned, active native trail still covers the entire residual.
                if terminated_trail and decimal(row["trailing_covered_size"]) < size:
                    row["exit_requested_ms"] = row["exit_requested_ms"] or now
                if row["exit_requested_ms"]:
                    row.pop("native_trailing_intervention", None)
                # Keep every prior native order/watermark. Add one full-size overlay
                # only after owned add fills terminate; inherited local TS covers
                # the full position throughout partial fills and overlay activation.
                needs_overlay = (bool(trails) and added_fills > 0
                    and all(decimal(a["quantity"]) < size for a in trails)
                    and p.get("local_trailing_backup", False))
                if (not trails or needs_overlay) and protected and fresh and not entry_active and not row["exit_requested_ms"] and not row.get("native_trailing_intervention"):
                    distance = normalize_quote_retracement(
                        decimal(row.get("native_trailing_distance",
                            decimal(p["atr"]) * decimal(p.get("native_atr_multiple", p["atr_multiple"])))),
                        decimal(snap["trailing_price_step"]))
                    row["native_trailing_distance"] = wire_decimal(distance)
                    self._state(row, "PROTECTING", "Fixed SL verified; awaiting full-position native trailing readback", now)
                    self._send(row, "trailing", now, quantity=str(size), price="0", retracement=str(distance))
                    return
                if (trails and not row.get("native_trailing_intervention") and not waiting
                        and not entry_active and not needs_overlay
                        and decimal(row["trailing_covered_size"]) < size
                        and now - trails[-1]["created_ms"] >= p["protection_grace_ms"]):
                    row["exit_requested_ms"] = row["exit_requested_ms"] or now
                protected = (protected and decimal(row["trailing_covered_size"]) >= size
                             and not row.get("native_trailing_intervention"))
                if not protected and not row["exit_requested_ms"] and not row.get("native_trailing_intervention"):
                    row["state"], row["reason"] = "PROTECTING", "Await entry terminality and verified native trailing coverage"
            if protected and fresh and not row["exit_requested_ms"]:
                row["state"], row["reason"] = (
                    "PROTECTED",
                    "Coverage verified; native trailing active" if native_trailing else "Coverage verified; local trailing active",
                )
        if any(a["kind"] in {"stop", "trailing"} and a["status"] == "FILLED" for a in attempts):
            row["exit_requested_ms"] = row["exit_requested_ms"] or now
        expired_entries = [a for a in entry_active if now >= a.get("expires_ms", p["expires_ms"])]
        if row["cancel_entry"] or row["exit_requested_ms"] or expired_entries:
            row["cancel_started_ms"] = row.get("cancel_started_ms") or now
            for a in entry_active:
                if not (row["cancel_entry"] or row["exit_requested_ms"]) and a not in expired_entries:
                    continue
                target = a.get("order_id")
                if not target:
                    self._state(
                        row,
                        "INTERVENTION",
                        "Entry outcome unknown; competing action blocked",
                        now,
                    )
                    return
                prior = [
                    x
                    for x in attempts
                    if x["kind"] == "cancel" and x.get("target_id") == target
                ]
                if (
                    now - row["cancel_started_ms"] > p["exit_deadline_ms"]
                    or len(prior) >= p["max_exit_attempts"]
                ):
                    self._state(
                        row,
                        "INTERVENTION",
                        "Entry cancellation budget exhausted; reconcile original order",
                        now,
                    )
                    return
                if not prior or prior[-1]["status"] == "REJECTED":
                    self._send(
                        row,
                        "cancel",
                        now,
                        target_id=target,
                        quantity=orders.get(target, {}).get("size", a["quantity"]),
                        price="0",
                        organization_id=a.get("organization_id", ""),
                    )
            if entry_active:
                self._state(
                    row,
                    "EXIT_PENDING" if row["exit_requested_ms"] else "ENTERING",
                    "Await entry cancellation and fills",
                    now,
                )
                return
        if row["exit_requested_ms"] and size > 0:
            if now - row["exit_requested_ms"] > p["exit_deadline_ms"]:
                self._state(
                    row,
                    "INTERVENTION",
                    "Exit attempt or deadline budget exhausted",
                    now,
                )
                return
            if not fresh:
                self._state(
                    row,
                    "DEGRADED",
                    "Exit requested; fresh execution price required",
                    now,
                )
                return
            if not snap["session_open"]:
                self._state(
                    row,
                    "EXIT_PENDING",
                    "Execution session closed; residual exposure remains",
                    now,
                )
                return
            for a in unresolved_exits:
                # Resting KIS limits must terminate before a bounded repriced replacement.
                target = a.get("order_id")
                if (
                    target
                    and orders.get(target, {}).get("status") == "open"
                    and now - a["created_ms"] >= p.get("exit_reprice_ms", 5000)
                ):
                    prior = [
                        x
                        for x in attempts
                        if x["kind"] == "cancel" and x.get("target_id") == target
                    ]
                    if len(prior) < p["max_exit_attempts"] and (
                        not prior or prior[-1]["status"] == "REJECTED"
                    ):
                        self._send(
                            row,
                            "cancel",
                            now,
                            target_id=target,
                            quantity=orders[target]["size"],
                            price="0",
                            organization_id=a.get("organization_id", ""),
                        )
            if not unresolved_exits:
                if len(exits) >= p["max_exit_attempts"]:
                    self._state(
                        row,
                        "INTERVENTION",
                        "Exit attempt budget exhausted with residual exposure",
                        now,
                    )
                    return
                qty = min(size, decimal(snap["sellable"]))
                step = decimal(snap["quantity_step"], positive=True)
                qty = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
                if qty <= 0:
                    raise ValueError("No executable sellable quantity")
                tick = decimal(snap["price_step"], positive=True)
                price = (
                    decimal(snap["price"]) * (1 - decimal(p["slippage"])) / tick
                ).to_integral_value(rounding=ROUND_UP) * tick
                if price <= 0:
                    raise ValueError("Invalid bounded exit price")
                self.store.save(row, now)
                self._send(row, "exit", now, quantity=str(qty), price=str(price))
            self._state(row, "EXIT_PENDING", "Reconcile exit before any retry", now)
            return
        if size == 0 and entry_filled > 0 and not entry_active:
            cleanup = stops + unresolved_exits
            for a in cleanup:
                target = a.get("order_id")
                if not target:
                    raise ValueError("Unknown owned order still needs cleanup")
                prior = [
                    x
                    for x in attempts
                    if x["kind"] == "cancel" and x.get("target_id") == target
                ]
                if len(prior) >= p["max_exit_attempts"]:
                    self._state(
                        row,
                        "INTERVENTION",
                        "Owned-order cleanup cancellation budget exhausted",
                        now,
                    )
                    return
                if not prior or prior[-1]["status"] == "REJECTED":
                    self._send(
                        row,
                        "cancel",
                        now,
                        target_id=target,
                        quantity=str(decimal(orders[target]["size"], positive=True)),
                        price="0",
                        organization_id=a.get("organization_id", ""),
                    )
            if cleanup:
                self._state(row, "CLEANUP", "Flat; awaiting owned-order terminality", now)
            else:
                self._state(
                    row,
                    "CLOSED",
                    "Flat and owned orders terminal; journal sync is independent",
                    now,
                )
            return
        if not fresh:
            self._state(
                row,
                "DEGRADED",
                "Stale market data; reconcile fills and retain native protection",
                now,
            )
        else:
            self.store.save(row, now)
        if (row["state"] == "PROTECTED" and not entry_active and not unresolved_exits
                and not row["exit_requested_ms"] and not row["cancel_entry"]):
            self._try_add(row, now)

    def _try_add(self, row, now):
        from kis_hl.conditional_add import preflight_add
        from kis_hl.hyperliquid.client import TransientInfoError
        for tranche in self.store.tranches(row["id"]):
            if tranche["status"] != "QUEUED":
                continue
            if any(a.get("tranche_id") == tranche["id"] for a in self.store.attempts(row["id"])):
                continue  # Durable attempt, including UNKNOWN, is never resent.
            try:
                if not self.store.entries_enabled(row["scope"]):
                    raise ValueError("Entries disabled; add cannot enable account-wide entries")
                if any(x["id"] != row["id"] and x["mode"] == row["mode"]
                       and x["state"] not in FINISHED | {"PROTECTED"}
                       for x in self.store.list(row["scope"])):
                    raise ValueError("Other account exposure needs reconciliation")
                sizing, now = preflight_add(self.gateway, self.store, row, tranche, now)
            except TransientInfoError as exc:
                tranche["reason"] = str(exc)
                self.store.save_tranche(tranche)
                continue  # No durable send attempt: revalidate within expiry next tick.
            except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                tranche.update(status="REJECTED", reason=str(exc))
                self.store.save_tranche(tranche)
                continue
            tranche["submission_sizing"] = sizing
            self.store.save_tranche(tranche)
            p = tranche["plan"]
            row["add_fixed_stop_price"] = p["fixed_stop_price"]
            a = self._send(row, "add", now, quantity=p["quantity"], price=p["limit_price"],
                           tranche_id=tranche["id"], expires_ms=p["expires_ms"])
            tranche.update(status=a["status"], attempt_id=a["id"])
            self.store.save_tranche(tranche)
