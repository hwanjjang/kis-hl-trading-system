"""Durable long-entry protection coordinated by one local account supervisor."""

from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
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
    if "entry_route" in plan and (
        plan["entry_route"] != "limit" or not plan["instrument"].startswith("hl:")
    ):
        raise ValueError("Only Hyperliquid limit-only entry routing is supported")
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
    if "native_trailing_percent" in plan:
        from kis_hl.hyperliquid.trailing import retracement_wire
        retracement_wire(decimal(plan["native_trailing_percent"], positive=True), "percent")
        if provider != "native" or plan.get("local_trailing_backup") is not False:
            raise ValueError("Percentage tranches require native trailing and explicitly disabled ATR backup")
        if "fixed_stop_price" not in plan:
            raise ValueError("Percentage tranches require an explicit position-level fixed stop")
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
            CREATE TABLE IF NOT EXISTS managed_notifications(id INTEGER PRIMARY KEY,position_id TEXT NOT NULL,
                scope TEXT NOT NULL,mode TEXT NOT NULL,kind TEXT NOT NULL,episode_ms INTEGER NOT NULL,
                created_ms INTEGER NOT NULL,payload TEXT NOT NULL,delivered_ms INTEGER,
                delivery_attempts INTEGER NOT NULL DEFAULT 0,last_attempt_ms INTEGER,
                UNIQUE(position_id,kind,episode_ms));
            """
            )
            # Serialize legacy migrations across CLI/supervisor processes.
            db.execute("BEGIN IMMEDIATE")
            if "details" not in {r["name"] for r in db.execute("PRAGMA table_info(managed_events)")}:
                db.execute("ALTER TABLE managed_events ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")

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
        if "native_trailing_percent" in plan and (not adoption or not adoption.get("trailing_order_id")):
            from kis_hl.percentage_entry import check_authority
            check_authority(scope, "live" if live else "paper", plan, now_ms)
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

    def enqueue_percentage_new_entry(self, scope, plan, *, manual, authorized_ms,
                                     decision_expires_ms, units, now_ms, live=False):
        """Manual once-intent NEW admission, never adoption or a strategy grant."""
        from kis_hl.percentage_entry import check_authority
        fields = ('fixed_stop_price', 'native_trailing_percent', 'max_notional',
                  'max_portfolio_notional', 'max_correlated_notional', 'max_spread_bps',
                  'max_quote_age_ms', 'slippage', 'protection_grace_ms', 'max_exit_attempts',
                  'exit_deadline_ms', 'exit_reprice_ms')
        authority = {k: plan.get(k) for k in fields}
        authority.update(manual=manual, scope=scope, mode='live' if live else 'paper',
                         instrument=plan['instrument'], intent_id=plan['intent_id'],
                         authorized_ms=authorized_ms, expires_ms=decision_expires_ms, units=str(units))
        p = dict(plan, percentage_entry_authorization=authority)
        check_authority(scope, authority['mode'], p, now_ms)
        return self.enqueue(scope, p, live=live, now_ms=now_ms)

    def tranches(self, position_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT snapshot FROM managed_tranches WHERE position_id=? ORDER BY rowid", (position_id,))]

    def save_tranche(self, tranche):
        with self.connect() as db:
            db.execute("UPDATE managed_tranches SET snapshot=? WHERE id=?", (encode(tranche), tranche["id"]))

    def retire_unsent_adds(self, position_id, now_ms):
        # Read-only pre-check: no retirement transaction or attempt scan unless a tranche is QUEUED.
        if not any(t["status"] == "QUEUED" for t in self.tranches(position_id)):
            return
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute("SELECT state FROM managed_positions WHERE id=?", (position_id,)).fetchone()
            if owner:
                self._retire_unsent(db, position_id, owner["state"], now_ms)

    @staticmethod
    def _retire_unsent(db, position_id, owner_state, now_ms):
        """Close QUEUED tranches with no durable attempt: all once the owner is
        finished, otherwise only those whose approval has expired."""
        finished = owner_state in FINISHED
        attempted = {json.loads(r[0]).get("tranche_id") for r in db.execute(
            "SELECT snapshot FROM managed_attempts WHERE position_id=?", (position_id,))}
        for record in db.execute("SELECT snapshot FROM managed_tranches WHERE position_id=?", (position_id,)).fetchall():
            tranche = json.loads(record[0])
            if tranche["status"] != "QUEUED" or tranche["id"] in attempted:
                continue
            if finished:
                tranche.update(status="CANCELED", reason=f"Owner {owner_state}; unsent add retired")
            elif now_ms >= tranche["plan"]["expires_ms"]:
                tranche.update(status="EXPIRED", reason=f"Approval expired while owner {owner_state}; unsent add retired")
            else:
                continue
            tranche["retired_ms"] = now_ms
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

    def enqueue_intraday_add(self, position_id, *, intent_id, units, expires_ms,
                             authorized_ms, now_ms, manual=False, risk_limits=None):
        """Queue explicit once-only intraday authority; never fabricate a weekly signal."""
        from kis_hl.intraday_add import check_intraday_authority
        owner = self.get(position_id)
        limits = risk_limits or {}
        allowed = {"max_loss", "max_notional", "max_portfolio_notional", "max_correlated_notional",
                   "max_spread_bps", "max_entry_deviation_bps"}
        if not isinstance(limits, dict) or not set(limits) <= allowed:
            raise ValueError("Unsupported intraday risk limit override")
        p = {**owner["plan"], **limits, "intent_id":intent_id, "action":"add",
             "position_id":position_id, "units":str(units), "expires_ms":expires_ms,
             "expected_size":owner["observed_size"], "expected_entry_filled":owner["entry_filled"],
             "intraday_authorization":dict(manual=manual, scope=owner["scope"], mode=owner["mode"],
                 position_id=position_id, units=str(units), authorized_ms=authorized_ms, expires_ms=expires_ms)}
        # Prior entry signals are not authority for this directly approved exception.
        p.pop("signal_id", None); p.pop("grant_id", None)
        p = validate_plan(p, now_ms)
        check_intraday_authority(owner, p, now_ms)
        return self.enqueue_add(owner, p, now_ms=now_ms,
                                sizing={"pending": "New completed UTC nine-minute high breakout"})

    def enqueue_adoption(self, scope, plan, *, entry_order_id, stop_order_id, live=False, now_ms,
                         entry_since_ms=None, trailing_order_id=None):
        from kis_hl.instruments import instrument
        asset = instrument(plan["instrument"])
        if asset.venue == "kis":
            # KIS order numbers are zero-padded strings; there is no native stop to import.
            if (asset.market != "domestic" or not isinstance(entry_order_id, str)
                    or not entry_order_id.isdigit() or stop_order_id is not None
                    or type(entry_since_ms) is not int or not 0 < entry_since_ms <= now_ms
                    or plan.get("signal_id") or plan.get("grant_id")):
                raise ValueError("KIS adoption requires a domestic listing, the buy order number, "
                                 "its fill time and direct management authority")
            return self.enqueue(scope, plan, live=live, now_ms=now_ms,
                                adoption={"venue": "kis", "entry_order_id": entry_order_id,
                                          "entry_since_ms": entry_since_ms})
        if asset.venue != "hyperliquid" or asset.market != "perp":
            raise ValueError("Adoption supports Hyperliquid perpetuals and KIS domestic listings only")
        if (any(type(x) is not int or x <= 0 for x in (entry_order_id, stop_order_id))
                or entry_order_id == stop_order_id or plan.get("signal_id") or plan.get("grant_id")):
            raise ValueError("Adoption requires distinct native IDs and direct management authority")
        request = {"entry_order_id":entry_order_id, "stop_order_id":stop_order_id}
        if trailing_order_id is not None:
            if (type(trailing_order_id) is not int or trailing_order_id <= 0
                    or trailing_order_id in {entry_order_id, stop_order_id}
                    or "native_trailing_percent" not in plan):
                raise ValueError("External trailing adoption requires a distinct exact ID and percentage policy")
            request["trailing_order_id"] = trailing_order_id
        return self.enqueue(scope, plan, live=live, now_ms=now_ms, adoption=request)

    def prepare_external_percentage_adoption(self, position_id, *, entry_order_id,
                                            stop_order_id, trailing_order_id, percent, now_ms,
                                            admission_expires_ms=None):
        """Explicit percentage-policy handoff; use generic reconciliation for quote owners."""
        return self.prepare_external_protection_adoption(position_id,
            entry_order_id=entry_order_id, stop_order_id=stop_order_id,
            trailing_order_id=trailing_order_id, percent=percent, now_ms=now_ms,
            admission_expires_ms=admission_expires_ms)

    def prepare_external_protection_adoption(self, position_id, *, entry_order_id,
                                            stop_order_id, trailing_order_id, now_ms,
                                            admission_expires_ms=None, percent=None):
        """Requeue the same intervention owner; no exchange mutations."""
        row = self.get(position_id)
        existing = self.attempts(position_id)
        if (row["state"] != "INTERVENTION"
                or row.get("exit_requested_ms") or row.get("cancel_entry")
                or any(a["kind"] not in {"entry", "stop", "trailing"} or not a.get("order_id")
                       or a["status"] == "UNKNOWN" for a in existing)):
            raise ValueError("Migration requires an intervention owner with exact known IDs and no competing lifecycle")
        ids = (entry_order_id, stop_order_id, trailing_order_id)
        if any(type(x) is not int or x <= 0 for x in ids) or len(set(ids)) != 3:
            raise ValueError("Migration requires distinct exact native IDs")
        request = row.get("adoption", {})
        for key, value, kind in (("entry_order_id", entry_order_id, "entry"),
                                 ("stop_order_id", stop_order_id, "stop"),
                                 ("trailing_order_id", trailing_order_id, "trailing")):
            if key in request and request[key] != value:
                raise ValueError("Migration must preserve original exact IDs")
            if any(a["kind"] == kind and str(a["order_id"]) != str(value) for a in existing):
                raise ValueError("Migration cannot replace an existing owned order")
        if self.tranches(position_id):
            raise ValueError("Migration with an existing add history is unsupported")
        p = dict(row["plan"])
        if percent is not None:
            if any(a["kind"] == "trailing" and a.get("retracement_unit", "quote") != "percent"
                   for a in existing):
                raise ValueError("Migration cannot change an owned trailing unit")
            p.update(native_trailing_percent=str(percent),
                     trailing_provider="native", local_trailing_backup=False)
        if p.get("trailing_provider") != "native":
            raise ValueError("Exact-ID reconciliation requires the authorized native trailing policy")
        expiry = p["expires_ms"] if admission_expires_ms is None else admission_expires_ms
        original_expiry = p["expires_ms"]
        p = validate_plan(dict(p, expires_ms=expiry), now_ms)
        p["expires_ms"] = original_expiry  # Never renew the original entry authority.
        row.update(plan=p, percentage_migration_pending=True, admission_expires_ms=expiry,
                   adoption=dict(entry_order_id=entry_order_id, stop_order_id=stop_order_id,
                                 trailing_order_id=trailing_order_id),
                   state="ADOPTING", reason="Exact-ID protection migration awaiting read-only verification")
        self.save(row, now_ms)
        return row


    def complete_adoption(self, row, updates, attempts, now_ms):
        new = {**row, **updates, "version":row["version"]+1}
        new.pop("percentage_migration_pending", None)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = [json.loads(r[0]) for r in db.execute(
                "SELECT snapshot FROM managed_attempts WHERE position_id=?", (row["id"],))]
            if existing and not row.get("percentage_migration_pending"):
                raise RuntimeError("Adoption already has owned attempts")
            for old in existing:
                match = next((a for a in attempts if a["kind"] == old["kind"]
                              and a["order_id"] == str(old.get("order_id"))), None)
                if (match is None or old["status"] == "UNKNOWN"
                        or decimal(old["quantity"]) != decimal(match["quantity"])):
                    raise ValueError("Migration evidence does not match existing exact ownership")
                refreshed = {**old, "status":match["status"]}
                if old["kind"] == "trailing":
                    if (old.get("retracement_unit", "quote") != match["retracement_unit"]
                            or decimal(old["retracement"]) != decimal(match["retracement"])):
                        raise ValueError("Migration cannot change owned trailing parameters")
                    refreshed.update(retracement=match["retracement"], retracement_unit=match["retracement_unit"],
                                     adopted_readback=match["adopted_readback"])
                db.execute("UPDATE managed_attempts SET status=?,snapshot=? WHERE id=?",
                           (refreshed["status"], encode(refreshed), old["id"]))
                attempts.remove(match)
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

    def save(self, row, now_ms):
        outbox = row.pop("pending_notifications", [])
        new = {**row, "version": row["version"] + 1}
        # The current blocker is kept apart from the first cause; polling with an
        # unchanged reason keeps its original time.
        if new["state"] == "INTERVENTION":
            blocker = new.get("intervention_blocker")
            if not blocker or blocker.get("reason") != new["reason"]:
                new["intervention_blocker"] = {"reason": new["reason"], "since_ms": now_ms}
        else:
            new.pop("intervention_blocker", None)
        with self.connect() as db:
            changed = db.execute(
                "UPDATE managed_positions SET state=?,version=?,snapshot=? WHERE id=? AND version=?",
                (new["state"], new["version"], encode(new), row["id"], row["version"]),
            )
            if changed.rowcount != 1:
                raise RuntimeError("Managed position changed; reload")
            db.execute(
                "INSERT INTO managed_events(position_id,time_ms,state,reason,details) VALUES(?,?,?,?,?)",
                (row["id"], now_ms, new["state"], new["reason"], encode({
                    label: new[key] for label, key in (("error", "last_error"),
                        ("first_intervention", "first_intervention"), ("read_health", "read_health")) if key in new
                })),
            )
            if outbox:
                # Same transaction as the state: one row per owner/kind/episode,
                # whatever polling, restarts or version races occur.
                attempts = [json.loads(r[0]) for r in db.execute(
                    "SELECT snapshot FROM managed_attempts WHERE position_id=? ORDER BY rowid", (row["id"],))]
                for note in outbox:
                    prefix = new["plan"]["instrument"].split(":")[0]
                    payload = {"venue": {"hl": "hyperliquid"}.get(prefix, prefix),
                               "instrument": new["plan"]["instrument"], "state": new["state"],
                               "reason": new["reason"], "read_health": new.get("read_health"),
                               **supervision_summary(new, attempts)}
                    db.execute(
                        "INSERT OR IGNORE INTO managed_notifications(position_id,scope,mode,kind,episode_ms,"
                        "created_ms,payload) VALUES(?,?,?,?,?,?,?)",
                        (row["id"], new["scope"], new["mode"], note["kind"], note["episode_ms"],
                         now_ms, encode(payload)))
            if new["state"] in FINISHED:
                # Same transaction: a terminal owner never persists with unsent adds.
                self._retire_unsent(db, row["id"], new["state"], now_ms)
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
        elif not row["exit_requested_ms"]:
            row["exit_requested_ms"] = now_ms
            row["exit_request_source"] = {"kind": "operator", "requested_ms": now_ms}
        self.save(row, now_ms)
        return row

    def notifications(self, scope=None, mode=None, *, include_delivered=False):
        """Outbox rows for Hermes delivery; listing never marks delivery."""
        query = "SELECT * FROM managed_notifications WHERE 1=1"
        args = []
        for column, value in (("scope", scope), ("mode", mode)):
            if value is not None:
                query += f" AND {column}=?"
                args.append(value)
        if not include_delivered:
            query += " AND delivered_ms IS NULL"
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(query + " ORDER BY id", args)]
        result = []
        for r in rows:
            note = {k: r[k] for k in ("id", "position_id", "mode", "kind", "episode_ms", "created_ms",
                                      "delivered_ms", "delivery_attempts", "last_attempt_ms")}
            note["payload"] = json.loads(r["payload"])
            note["message"] = notification_message(note)
            result.append(note)
        return result

    def record_notification_result(self, notification_id, *, delivered, now_ms):
        """Record a Hermes delivery outcome; never touches execution state."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT delivered_ms FROM managed_notifications WHERE id=?",
                             (notification_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown notification")
            if row["delivered_ms"] is not None:
                raise ValueError("Notification already delivered")
            db.execute(
                "UPDATE managed_notifications SET delivery_attempts=delivery_attempts+1,last_attempt_ms=?,"
                "delivered_ms=? WHERE id=?", (now_ms, now_ms if delivered else None, notification_id))
        return next(n for n in self.notifications(include_delivered=True) if n["id"] == notification_id)

    def recovery_blockers(self, row, attempts, now_ms):
        """Explain budgets that unchanged-budget recovery cannot resolve."""
        p = row["plan"]
        blockers = []
        residual = decimal(row.get("observed_size", "0")) > 0
        requested = row.get("exit_requested_ms")
        provenance = exit_provenance(self, row)
        if row.get("read_failure_exit") and residual:
            blockers.append("A legacy read-outage exit latch is still pending; the current policy never "
                            "executes it automatically.")
        if requested is not None and residual:
            exits = [a for a in attempts if a["kind"] == "exit"]
            unresolved = [a for a in exits if a["status"].lower() not in TERMINAL]
            if now_ms - requested > p["exit_deadline_ms"]:
                blockers.append(
                    f"Exit deadline budget exhausted: the exit request at {requested} ms had "
                    f"exit_deadline_ms={p['exit_deadline_ms']} and expired at {requested + p['exit_deadline_ms']} ms. "
                    "Recovery keeps budgets unchanged, so the supervisor would return to INTERVENTION immediately.")
            elif len(exits) >= p["max_exit_attempts"] and not unresolved:
                blockers.append(
                    f"Exit attempt budget exhausted: {len(exits)} of max_exit_attempts={p['max_exit_attempts']} "
                    "used with residual exposure. Recovery keeps budgets unchanged.")
        if blockers:
            kind = provenance["kind"] if provenance else "read_outage_latch"
            if kind == "read_outage_latch":
                blockers.append(
                    f"Exit provenance: read_outage_latch ({(provenance or {}).get('evidence', 'flag')}). Only under "
                    "separate explicit authorization, withdraw exactly this request with "
                    f"`order withdraw-read-exit --id {row['id']} --exit-requested-ms {requested}` and then run "
                    "`order recover`.")
            else:
                blockers.append(
                    f"Exit provenance: {kind}. Manage the residual exposure under a separately authorized "
                    "procedure; recovery cannot renew budgets.")
        return blockers

    def recover_intervention(self, position_id, now_ms):
        row = self.get(position_id)
        if row["state"] != "INTERVENTION":
            raise ValueError("Only an intervention state can be recovered")
        blockers = self.recovery_blockers(row, self.attempts(position_id), now_ms)
        if blockers:
            raise ValueError("Recovery refused. " + " ".join(blockers))
        row.update(
            state="ADOPTING" if row.get("adoption") and not row.get("adopted_ms") else "ENTERING",
            reason="Explicit recovery requested; budgets and ownership unchanged",
        )
        self.save(row, now_ms)
        return row

    def withdraw_read_outage_exit(self, position_id, exit_requested_ms, *, now_ms):
        """Withdraw one exact read-outage exit latch; never renews budgets or sends orders."""
        row = self.get(position_id)
        attempts = self.attempts(position_id)
        if row["state"] != "INTERVENTION":
            raise ValueError("Withdrawal requires an INTERVENTION owner")
        if type(exit_requested_ms) is not int or row.get("exit_requested_ms") != exit_requested_ms:
            raise ValueError("Withdrawal requires the exact current exit_requested_ms")
        provenance = exit_provenance(self, row)
        if provenance["kind"] != "read_outage_latch":
            raise ValueError(f"Exit provenance is {provenance['kind']}, not read_outage_latch; withdrawal refused")
        if any(a["kind"] == "exit" and a["created_ms"] >= exit_requested_ms for a in attempts):
            raise ValueError("An exit attempt exists for this request; withdrawal refused")
        if any(a["status"] == "UNKNOWN" or (a["kind"] in {"entry", "add"} and a["status"].lower() not in TERMINAL)
               for a in attempts) or row.get("cancel_entry"):
            raise ValueError("Unknown or unresolved entry/add lifecycle blocks withdrawal")
        if (any(a["kind"] in {"stop", "trailing"} and a["status"] == "FILLED" for a in attempts)
                or decimal(row.get("exit_protective_filled", row.get("protective_filled", "0"))) > 0):
            raise ValueError("Protective fills are recorded; withdrawal refused")
        row["exit_requested_ms"] = None
        row.pop("read_failure_exit", None)
        row.setdefault("withdrawn_exit_requests", []).append(
            {"exit_requested_ms": exit_requested_ms, "withdrawn_ms": now_ms, "provenance": provenance})
        row["reason"] = ("Read-outage exit request withdrawn by explicit command; "
                         "run order recover to resume supervision")
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

    def _record_error(self, row, exc, now, *, reason=None):
        # Only fixed local validation messages may be retained. Transport payloads,
        # missing keys and arbitrary exception text can contain credentials.
        safe_reasons = {
            "External ownership or inconsistent exposure", "Unexpected position generation",
            "Order identity mismatch", "Native order identifier mismatch",
            "Client order identifier mismatch", "Order direction or reduce-only contract mismatch",
            "Native SL semantics did not match", "Trailing order size mismatch",
            "Execution retention gap", "Unknown execution side", "Invalid execution time",
            "Inconsistent add tranche fills", "Entry preflight not ready",
            "Only verified USDC collateral is supported", "Delisted execution asset",
            "Native trailing order semantics did not match", "Native trailing retracement mismatch",
            "Native trailing activation mismatch; immediate activation required",
            "Insufficient available funds", "Portfolio notional limit exceeded",
            "Correlated notional limit exceeded", "Execution spread limit exceeded",
            "Entry limit is outside the quote band", "ATR instrument mismatch",
            "Plan ATR differs from current execution-instrument history", "Invalid order lot/tick",
            "No protective provider available", "Native trailing provider unavailable",
        }
        category = next((cls.__name__ for cls in (KeyError, IndexError, TypeError,
            ValueError, RuntimeError, OSError, StopIteration) if isinstance(exc, cls)), "ExecutionError")
        context = dict(row.get("reconciliation_context", {}))
        row["last_error"] = {
            "category": category,
            "reason": reason or (str(exc) if str(exc) in safe_reasons else "Invalid execution evidence"),
            "tick_ms": now,
            "observed_ms": context.get("observed_now_ms", context.get("exposure_observed_ms", now)),
            "context": context,
        }

    def _state(self, row, state, reason, now, *, preserve_native_intervention=False):
        if state == "INTERVENTION" and not preserve_native_intervention:
            row.pop("native_trailing_intervention", None)
            if row.get("last_error"):
                # First cause is history; the reason stays the current blocker.
                row.setdefault("first_intervention", {**row["last_error"], "summary": reason})
        row.update(state=state, reason=reason)
        self.store.save(row, now)

    def _read_outage(self, row, exc, now):
        """Account-read failure is a warning: never an exit request, flag or deadline."""
        row["read_failures"] = row.get("read_failures", 0) + 1
        row.setdefault("read_failure_since_ms", now)
        health = row.get("read_health") or {}
        new_episode = health.get("status") != "unavailable"
        if new_episode:
            health = {"status": "unavailable", "since_ms": now, "operation": "account_snapshot",
                      "last_success_ms": row.get("last_observed_ms")}
        health.update(last_failure_ms=now, consecutive_failures=row["read_failures"],
                      phase=row["last_error"]["context"].get("phase"), error=read_error_classification(exc))
        row["read_health"] = health
        # A failed read still proves the supervisor was running: observation gaps
        # count only the time between ticks, never the outage itself.
        anchor = max(row.get("last_observed_ms") or 0, row.get("last_supervised_ms") or 0)
        if anchor:
            gap = getattr(self.gateway, "observation_gap_ms", None)
            interval = int(gap(row, anchor, now)) if gap else now - anchor
            row["unsupervised_gap_ms"] = max(row.get("unsupervised_gap_ms", 0), interval)
        row["last_supervised_ms"] = now
        if new_episode:
            row.setdefault("pending_notifications", []).append(
                {"kind": "read_outage", "episode_ms": health["since_ms"]})
        if row["state"] == "INTERVENTION":
            # Read health is reported separately; keep the current blocker.
            self.store.save(row, now)
            return
        self._state(
            row,
            "DEGRADED",
            f"Account snapshot unavailable ({type(exc).__name__}); consecutive failures={row['read_failures']}; "
            "warning only; no exit requested; native orders retained, local supervision paused",
            now,
        )

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
                # Repair legacy terminal owners saved before atomic retirement.
                self.store.retire_unsent_adds(position_id, now_ms)
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
            ) as exc:
                current = self.store.get(position_id)
                if current["version"] == row["version"]:
                    # A legacy read-failure latch keeps its provenance under any blocker.
                    row.pop("native_trailing_intervention", None)
                    self._record_error(row, exc, now_ms)
                    error = row["last_error"]
                    self._state(
                        row,
                        "INTERVENTION",
                        f"Preflight or reconciliation failed ({error['category']}): {error['reason']}",
                        error["observed_ms"],
                    )
                # Concurrent control requests win; reload on the next supervisor iteration.
            # _try_add rejects an expired add only when it evaluates it this tick; retire
            # any expired unsent approval it did not evaluate so it stops showing as pending.
            self.store.retire_unsent_adds(position_id, now_ms)
            return self.store.get(position_id)

    def _step(self, row, now):
        row.pop("last_error", None)
        row.pop("reconciliation_context", None)
        p = row["plan"]
        attempts = self.store.attempts(row["id"])
        native_trailing = p.get("trailing_provider", "local") == "native"
        if row.get("adoption") and (not row.get("adopted_ms") or row.get("percentage_migration_pending")):
            if row["cancel_entry"] or row["exit_requested_ms"] is not None:
                if attempts or row.get("adopted_ms"):
                    self._state(row, "INTERVENTION", "Migration canceled; retain existing owner and protections for manual reconciliation", now)
                    return
                self._state(row, "CLOSED", "Handoff canceled; external position and orders unchanged", now)
                return
            if row["state"] != "ADOPTING":
                return
            validate_plan(dict(p, expires_ms=row.get("admission_expires_ms", p["expires_ms"])), now)
            if not self.live:
                self._state(row, "PREVIEWED", "Paper handoff; no account reads or ownership imported", now)
                return
            from kis_hl.manual_adoption import verify_adoption, verify_kis_adoption
            verifier = verify_kis_adoption if row["adoption"].get("venue") == "kis" else verify_adoption
            try:
                updates, imported = verifier(self.gateway, row, now)
            except ValueError as exc:
                if str(exc).startswith("migration-required:"):
                    self._state(row, "INTERVENTION", str(exc), now)
                    return
                raise
            if row.get("percentage_migration_pending") and updates["adopted_ms"] >= row["admission_expires_ms"]:
                raise ValueError("Read-only migration authority expired during account reads")
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
            if p.get('percentage_entry_authorization'):
                from kis_hl.percentage_entry import prepare_entry
                bars = self.gateway.completed_nine_minute_bars(p['instrument'], now)
            snap = self.gateway.preflight(p, now)
            now = int(snap.get("observed_now_ms", now))
            if p.get('percentage_entry_authorization'):
                p = prepare_entry(row['scope'], row['mode'], p, snap, bars, now)
                row['plan'] = p
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
            entry_type = snap.get("entry_order_type") if p["instrument"].startswith("hl:") else None
            if p["instrument"].startswith("hl:") and entry_type not in {"market", "limit"}:
                raise ValueError("Verified Hyperliquid entry routing required")
            entry_price = (price if p.get('percentage_entry_authorization') else ask) if entry_type == "limit" else price
            if p.get('percentage_entry_authorization') and entry_type != 'limit':
                raise ValueError('NEW percentage entries require hard-capped limit routing')
            # Persist the exact legal IOC ceiling; transport must not recalculate
            # it from a later SDK mid or round it above the checked risk budget.
            if entry_type == "market":
                entry_price = normalize_quote_retracement(
                    bid * Decimal("1.005"), decimal(snap["trailing_price_step"]))
            risk_price = entry_price
            stop = decimal(p["fixed_stop_price"]) if "fixed_stop_price" in p else price - decimal(p["stop_distance"])
            if (risk_price <= stop or size * (risk_price - stop) > decimal(p["max_loss"])
                    or size * risk_price > decimal(p["max_notional"])
                    or size * risk_price > decimal(snap["available_notional"])
                    or size * risk_price + decimal(snap["portfolio_notional"]) > decimal(p["max_portfolio_notional"])
                    or size * risk_price + decimal(snap["correlated_notional"]) > decimal(p["max_correlated_notional"])):
                raise ValueError("Execution price exceeds entry risk budgets")
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
            if entry_type == "limit" and (entry_price % decimal(snap["price_step"], positive=True)
                    or (entry_price != entry_price.to_integral_value()
                        and len(entry_price.normalize().as_tuple().digits) > 5)):
                raise ValueError("Current ask violates Hyperliquid price precision")
            if not self.gateway.native_sl and not p["allow_local_sl"]:
                raise ValueError("No protective provider available")
            if native_trailing and not getattr(self.gateway, "native_trailing", False):
                raise ValueError("Native trailing provider unavailable")
            if native_trailing and 'native_trailing_percent' not in p:
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
            attempt = self._send(row, "entry", now, quantity=str(size), price=str(entry_price),
                                 **({"expires_ms": p['expires_ms']} if p.get('percentage_entry_authorization') else {}),
                                 **({"order_type": entry_type} if entry_type else {}))
            if entry_type == "market" and attempt["status"] == "SUBMITTED":
                # An IOC may fill in the submission response. Reconcile in this
                # cycle so the existing partial-fill SL path runs immediately.
                self._step(row, now)
                if row.get("first_fill_ms") and any(
                    a["kind"] == "stop" for a in self.store.attempts(row["id"])
                ):
                    # Read back the fixed SL before allowing native trailing.
                    self._step(row, now)
            return
        try:
            snap = self.gateway.snapshot(row, attempts, now)
        except (RuntimeError, OSError) as exc:
            self._record_error(row, exc, now, reason="Account snapshot unavailable")
            self._read_outage(row, exc, now)
            return
        supervised_anchor = row.pop("last_supervised_ms", 0)
        unsupervised_gap = row.pop("unsupervised_gap_ms", 0)
        row["read_failures"] = 0
        row.pop("read_failure_since_ms", None)
        row["reconciliation_context"] = dict(snap.get("reconciliation_context", {}))
        now = int(snap.get("observed_now_ms", now))
        health = row.get("read_health") or {}
        if health.get("status") == "unavailable":
            row["read_health"] = {"status": "ok", "last_success_ms": now, "last_outage": {
                "since_ms": health["since_ms"], "until_ms": now, "failures": health["consecutive_failures"],
                "phase": health.get("phase"), "error": health.get("error")}}
            # Persisted with whatever state this tick's reconciliation reaches.
            row.setdefault("pending_notifications", []).append(
                {"kind": "read_recovered", "episode_ms": health["since_ms"]})
        else:
            row["read_health"] = {"status": "ok", "last_success_ms": now,
                                  **({"last_outage": health["last_outage"]} if "last_outage" in health else {})}
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
        if row.get("read_failure_exit"):
            # Latched by the pre-issue-59 policy: never execute it automatically and
            # never clear it in bulk. A flat owner needs no exit and may clean up.
            if size > 0:
                self._state(row, "INTERVENTION", "Legacy read-outage exit latch retained; explicit scoped "
                            "withdrawal or exit decision required", now)
                return
            row.pop("read_failure_exit")
        protective_filled = decimal(snap.get("protective_filled", "0"))
        exit_filled = decimal(snap["fixed_stop_filled"]) if "native_trailing_percent" in p else protective_filled
        if exit_filled > decimal(row.get("exit_protective_filled", row.get("protective_filled", "0"))):
            row["exit_requested_ms"] = row["exit_requested_ms"] or now
        row["exit_protective_filled"] = str(exit_filled)
        row["protective_filled"] = str(protective_filled)
        previous_observation = max(row.get("last_observed_ms", now), supervised_anchor)
        same_session = (
            snap.get("same_execution_session", True)
            and row.get("last_session_open", True)
        )
        row["last_observed_ms"] = now
        row["last_session_open"] = bool(snap["session_open"])
        if not self.gateway.native_sl and not same_session:
            row.pop("unprotected_since_ms", None)
        if (
            size > 0
            and not self.gateway.native_sl
            and max(int(snap.get(
                "regular_session_gap_ms",
                now - previous_observation if snap["session_open"] else 0,
            )), unsupervised_gap) >= p["protection_grace_ms"]
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
                        covered += decimal(order.get("coverage_size", order["size"]))
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
                if protected or not snap["session_open"]:
                    # A closed venue session cannot be protected locally by any
                    # means; it is disclosed gap risk, not a reason to force an exit
                    # at the next open. Only in-session loss of coverage counts.
                    row.pop("unprotected_since_ms", None)
                else:
                    row.setdefault("unprotected_since_ms", now)
            row["local_trailing_covered_size"] = str(size if fresh and (
                not native_trailing or p.get("local_trailing_backup", False)) else 0)
            since = row.get("unprotected_since_ms")
            if not protected and since is not None and now - since >= p["protection_grace_ms"]:
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
                            if "native_trailing_percent" not in p:
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
                          and order.get("retracement_unit") == a.get("retracement_unit", "quote")
                          and decimal(order.get("retracement", "0")) == decimal(a["retracement"])):
                        order_size = decimal(order["size"], positive=True)
                        waiting |= order.get("active") is False and (order_size >= size or "native_trailing_percent" in p)
                        if order.get("active") is True:
                            prior = decimal(row["trailing_covered_size"])
                            row["trailing_covered_size"] = str(min(size, prior + order_size)
                                if "native_trailing_percent" in p else max(prior, min(size, order_size)))
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
                trail_started_ms = trails[-1]["created_ms"] if trails else now
                if "native_trailing_percent" in p:
                    # Cumulative allocations include UNKNOWN outcomes; never
                    # resend them. New fills without an attempt get a new deadline.
                    allocated = sum((decimal(a["quantity"]) for a in trails), Decimal(0))
                    missing = entry_filled - allocated
                    # Later fills must not renew an older increment's immediate
                    # activation deadline. Quote-distance waiting retains its policy.
                    trail_started_ms = min((a["created_ms"] for a in trails
                        if a["status"].lower() not in TERMINAL
                        and orders.get(a.get("order_id"), {}).get("active") is not True),
                        default=now if missing > 0 else trail_started_ms)
                if (trails and not row.get("native_trailing_intervention")
                        and (not waiting or "native_trailing_percent" in p)
                        and (not entry_active or "native_trailing_percent" in p) and not needs_overlay
                        and decimal(row["trailing_covered_size"]) < size
                        and now - trail_started_ms >= p["protection_grace_ms"]):
                    row["exit_requested_ms"] = row["exit_requested_ms"] or now
                if "native_trailing_percent" in p:
                    # Each filled increment gets its own immediate percentage watermark.
                    # Include UNKNOWN attempts: never resend an ambiguous native action.
                    if (missing > 0 and protected and fresh and not row["exit_requested_ms"]
                            and not row.get("native_trailing_intervention")):
                        self._state(row, "PROTECTING", "Fixed SL verified; awaiting added-quantity percentage trail", now)
                        self._send(row, "trailing", now, quantity=str(missing), price="0",
                                   retracement=p["native_trailing_percent"], retracement_unit="percent")
                        return
                if "native_trailing_percent" not in p and (not trails or needs_overlay) and protected and fresh and not entry_active and not row["exit_requested_ms"] and not row.get("native_trailing_intervention"):
                    distance = normalize_quote_retracement(
                        decimal(row.get("native_trailing_distance",
                            decimal(p["atr"]) * decimal(p.get("native_atr_multiple", p["atr_multiple"])))),
                        decimal(snap["trailing_price_step"]))
                    row["native_trailing_distance"] = wire_decimal(distance)
                    self._state(row, "PROTECTING", "Fixed SL verified; awaiting full-position native trailing readback", now)
                    self._send(row, "trailing", now, quantity=str(size), price="0", retracement=str(distance))
                    return
                protected = (protected and decimal(row["trailing_covered_size"]) >= size
                             and not row.get("native_trailing_intervention"))
                if not protected and not row["exit_requested_ms"] and not row.get("native_trailing_intervention"):
                    row["state"], row["reason"] = "PROTECTING", "Await entry terminality and verified native trailing coverage"
            if protected and fresh and not row["exit_requested_ms"]:
                row["state"], row["reason"] = (
                    "PROTECTED",
                    "Coverage verified; native trailing active" if native_trailing else "Coverage verified; local trailing active",
                )
        if any(a["status"] == "FILLED" and (a["kind"] == "stop" or
               (a["kind"] == "trailing" and "native_trailing_percent" not in p)) for a in attempts):
            row["exit_requested_ms"] = row["exit_requested_ms"] or now
        expired_entries = [a for a in entry_active if now >= a.get("expires_ms", p["expires_ms"])]
        if row["cancel_entry"] or row["exit_requested_ms"] or expired_entries:
            for a in entry_active:
                if not (row["cancel_entry"] or row["exit_requested_ms"]) and a not in expired_entries:
                    continue
                target = a.get("order_id")
                prior = [x for x in attempts
                         if target and x["kind"] == "cancel" and x.get("target_id") == target]
                if a.get("cancel_started_ms") is None:
                    started = min(x["created_ms"] for x in prior) if prior else now
                    legacy = row.get("cancel_started_ms")
                    if prior and legacy is not None and a["created_ms"] <= legacy <= started:
                        started = legacy
                    # Budget belongs to this target, including after process death.
                    # Matching cancel history preserves legacy same-target limits;
                    # an unmatched owner clock must not poison a later add.
                    self.store.update_attempt(a, cancel_started_ms=started)
                if not target:
                    self._state(
                        row,
                        "INTERVENTION",
                        "Entry outcome unknown; competing action blocked",
                        now,
                    )
                    return
                if (
                    now - a["cancel_started_ms"] > p["exit_deadline_ms"]
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
                snap.get("session_unavailable_reason") or (
                    "Stale market data; reconcile fills and retain native protection"
                    if self.gateway.native_sl else "Stale market data; local protection unavailable"
                ),
                now,
            )
        else:
            self.store.save(row, now)
        if (row["state"] == "PROTECTED" and not entry_active and not unresolved_exits
                and not row["exit_requested_ms"] and not row["cancel_entry"]):
            self._try_add(row, now)

    def _try_add(self, row, now):
        from kis_hl.conditional_add import preflight_add
        from kis_hl.intraday_add import AddConditionPending, prepare_intraday_add
        from kis_hl.hyperliquid.client import TransientInfoError
        from kis_hl.strategy_signals import Signals
        for tranche in self.store.tranches(row["id"]):
            if tranche["status"] != "QUEUED":
                continue
            if any(a.get("tranche_id") == tranche["id"] for a in self.store.attempts(row["id"])):
                continue  # Durable attempt, including UNKNOWN, is never resent.
            try:
                if not self.store.entries_enabled(row["scope"]):
                    raise ValueError("Entries disabled; add cannot enable account-wide entries")
                # Check authority before deferring so account activity cannot
                # keep expired or revoked approvals queued indefinitely.
                validate_plan(tranche["plan"], now)
                Signals(self.store).check_authority({**row, "plan": tranche["plan"]}, now_ms=now)
                others = [x for x in self.store.list(row["scope"])
                          if x["id"] != row["id"] and x["mode"] == row["mode"]
                          and x["state"] not in FINISHED]
                # DEGRADED can also mean a pending exit; state alone is not
                # sufficient to distinguish a temporary reconciliation wait.
                if any(x["state"] not in {"PROTECTED", "QUEUED", "ENTERING", "PROTECTING", "DEGRADED", "ADOPTING"}
                       or x.get("exit_requested_ms") is not None or x.get("cancel_entry")
                       or x.get("read_failure_exit") or x.get("native_trailing_intervention")
                       for x in others):
                    raise ValueError("Other account exposure needs reconciliation")
                if any(x["state"] != "PROTECTED" for x in others):
                    tranche["reason"] = "Waiting for other account position reconciliation"
                    self.store.save_tranche(tranche)
                    continue
                prepare = prepare_intraday_add if tranche["plan"].get("intraday_authorization") else preflight_add
                sizing, now = prepare(self.gateway, self.store, row, tranche, now)
            except AddConditionPending as exc:
                tranche["reason"] = str(exc)
                self.store.save_tranche(tranche)
                continue
            except TransientInfoError as exc:
                tranche["reason"] = str(exc)
                self.store.save_tranche(tranche)
                continue  # No durable send attempt: revalidate within expiry next tick.
            except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                tranche.update(status="REJECTED", reason=str(exc))
                self.store.save_tranche(tranche)
                continue
            tranche["submission_sizing"] = sizing
            tranche.pop("reason", None)
            self.store.save_tranche(tranche)
            p = tranche["plan"]
            row["add_fixed_stop_price"] = p["fixed_stop_price"]
            a = self._send(row, "add", now, quantity=p["quantity"], price=p["limit_price"],
                           tranche_id=tranche["id"], expires_ms=p["expires_ms"])
            tranche.update(status=a["status"], attempt_id=a["id"])
            self.store.save_tranche(tranche)


_READ_ERROR_CATEGORIES = {
    "TransientInfoError", "RuntimeError", "OSError", "TimeoutError", "ConnectionError",
    "ConnectionResetError", "ConnectionRefusedError", "ConnectionAbortedError",
    "BrokenPipeError", "URLError", "HTTPError",
}


def read_error_classification(exc):
    """Allowlisted structure only: never the message, URL or response body."""
    name = type(exc).__name__
    category = name if name in _READ_ERROR_CATEGORIES else next(
        base.__name__ for base in (TimeoutError, ConnectionError, OSError, RuntimeError, Exception)
        if isinstance(exc, base))
    kind = getattr(exc, "kind", None)
    if kind not in {"http", "timeout", "transport"}:
        kind = ("timeout" if isinstance(exc, TimeoutError)
                else "transport" if isinstance(exc, ConnectionError) else "other")
    status = getattr(exc, "http_status", None)
    return {"category": category, "kind": kind,
            "http_status": status if type(status) is int and 100 <= status <= 599 else None}


def supervision_summary(row, attempts):
    """Native venue orders versus local supervision, from durable state only."""
    plan = row["plan"]
    native = [a["order_id"] for a in attempts if a["kind"] in {"stop", "trailing"}
              and a.get("order_id") and a["status"].lower() not in TERMINAL]
    providers = row.get("providers") or {}
    stop = providers.get("stop_loss", "local" if plan["instrument"].startswith("kis:") else "native")
    local = (["local_stop_loss"] if stop == "local" and plan.get("allow_local_sl") else []) + (
        ["local_trailing"] if plan.get("trailing_provider", "local") == "local"
        or plan.get("local_trailing_backup") else [])
    if row["state"] in FINISHED:
        status, reason = "stopped", "Owner finished"
    elif (row.get("read_health") or {}).get("status") == "unavailable":
        status, reason = "paused", ("Account reads unavailable: local SL/TS, exits and fill reconciliation "
                                    "cannot run; native orders are retained but not re-verified")
    elif row["state"] == "INTERVENTION" and not row.get("native_trailing_intervention"):
        status, reason = "paused", ("Intervention: local trailing and exit processing are suspended until "
                                    "explicit recovery; native orders remain at the venue")
    else:
        status, reason = "active", "Local supervision runs on each fresh consistent readback"
    return {"native_orders_retained": native, "local_protections": local,
            "local_supervision": status, "supervision_reason": reason}


def _iso(ms):
    if ms is None:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def notification_message(note):
    """Fixed English text built from allowlisted payload fields."""
    p = note["payload"]
    health = p.get("read_health") or {}
    head = f"{p['instrument']} ({p['venue']}, owner {note['position_id'][:8]})"
    if note["kind"] == "read_outage":
        error = health.get("error") or {}
        cause = f"HTTP {error['http_status']}" if error.get("http_status") else error.get("kind", "unknown")
        native = ", ".join(map(str, p["native_orders_retained"])) or "none"
        local = ", ".join(p["local_protections"]) or "none"
        return (f"WARNING {head}: account reads unavailable since {_iso(note['episode_ms'])} "
                f"({health.get('operation')}, phase {health.get('phase') or 'unknown'}, {cause}). "
                f"Warning only: no exit requested. Native orders retained: {native}. "
                f"Local supervision {p['local_supervision']} (local protections: {local}). "
                f"Last successful observation: {_iso(health.get('last_success_ms'))}.")
    outage = health.get("last_outage") or {}
    return (f"RECOVERED {head}: account reads recovered at {_iso(outage.get('until_ms'))} after "
            f"{outage.get('failures')} failed reads since {_iso(note['episode_ms'])}. "
            f"State {p['state']}: {p['reason']}. Local supervision {p['local_supervision']}.")


def exit_provenance(store, row):
    """Why an exit was requested; legacy read-outage latches are inferred from events."""
    requested = row.get("exit_requested_ms")
    if requested is None:
        return None
    source = row.get("exit_request_source") or {}
    if source.get("requested_ms") == requested:
        return {"kind": source["kind"], "evidence": "recorded"}
    if row.get("read_failure_exit"):
        return {"kind": "read_outage_latch", "evidence": "flag"}
    with store.connect() as db:
        latched = db.execute(
            "SELECT 1 FROM managed_events WHERE position_id=? AND time_ms=? AND state='INTERVENTION' "
            "AND reason LIKE 'Account snapshot unavailable%' LIMIT 1", (row["id"], requested)).fetchone()
    if latched:
        return {"kind": "read_outage_latch", "evidence": "event",
                "note": "Inferred from the INTERVENTION event persisted when the read-outage policy latched it"}
    return {"kind": "other", "evidence": "none",
            "note": "Protection, trailing or fill trigger; not attributable to a read outage"}


def owner_diagnostics(store, row, now_ms):
    """Read-only status view separating causes, blockers, read health and supervision."""
    p = row["plan"]
    attempts = store.attempts(row["id"])
    requested = row.get("exit_requested_ms")
    exits = [a for a in attempts if a["kind"] == "exit"]
    unresolved = [a for a in exits if a["status"].lower() not in TERMINAL]
    with store.connect() as db:
        total = db.execute("SELECT COUNT(*) FROM managed_events WHERE position_id=?", (row["id"],)).fetchone()[0]
        transitions = [dict(r) for r in db.execute(
            "SELECT time_ms,state,reason FROM (SELECT id,time_ms,state,reason,"
            "LAG(state) OVER w AS prior_state,LAG(reason) OVER w AS prior_reason "
            "FROM managed_events WHERE position_id=? WINDOW w AS (ORDER BY id)) "
            "WHERE prior_state IS NULL OR prior_state!=state OR prior_reason!=reason ORDER BY id",
            (row["id"],))]
    summary = supervision_summary(row, attempts)
    return {
        "intervention": {"first_cause": row.get("first_intervention"),
                         "current_blocker": row.get("intervention_blocker")}
        if row["state"] == "INTERVENTION" else None,
        "read_health": row.get("read_health") or {"status": "unknown"},
        "supervision": summary,
        "exit": {
            "requested_ms": requested,
            "deadline_at_ms": requested + p["exit_deadline_ms"] if requested is not None else None,
            "deadline_exhausted": requested is not None and now_ms - requested > p["exit_deadline_ms"],
            "exit_attempts": len(exits),
            "max_exit_attempts": p["max_exit_attempts"],
            "attempts_exhausted": len(exits) >= p["max_exit_attempts"] and not unresolved,
            "provenance": exit_provenance(store, row),
            "withdrawn": row.get("withdrawn_exit_requests", []),
        },
        # Every save is an event; only state/reason changes are transitions.
        "events": {"total": total, "transition_count": len(transitions),
                   "polls": total - len(transitions), "recent_transitions": transitions[-10:]},
    }
