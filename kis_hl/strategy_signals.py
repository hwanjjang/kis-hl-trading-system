"""Versioned strategy outputs and explicit execution authority; no strategy code runner."""

import json

from kis_hl.execution_lock import account_lock
from kis_hl.instruments import instrument
from kis_hl.journal_sync import decimal, encode
from kis_hl.managed_execution import validate_plan


class Signals:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS strategy_versions(id TEXT,version TEXT,payload TEXT NOT NULL,PRIMARY KEY(id,version));
            CREATE TABLE IF NOT EXISTS strategy_signals(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS execution_grants(id TEXT PRIMARY KEY,payload TEXT NOT NULL,
                reserved_intents INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0);
        """
            )

    def register(self, record):
        if not all(
            isinstance(record.get(k), str) and record[k].strip()
            for k in ["id", "version", "description"]
        ):
            raise ValueError("Strategy ID, version and description required")
        self._instruments(record.get("instruments"))
        with self.store.connect() as db:
            old = db.execute(
                "SELECT payload FROM strategy_versions WHERE id=? AND version=?",
                (record["id"], record["version"]),
            ).fetchone()
            if old and old[0] != encode(record):
                raise ValueError("Strategy version is immutable")
            db.execute(
                "INSERT OR IGNORE INTO strategy_versions VALUES(?,?,?)",
                (record["id"], record["version"], encode(record)),
            )
        return record

    @staticmethod
    def _instruments(items):
        if not isinstance(items, list) or not items:
            raise ValueError("Explicit instrument set required")
        for key in items:
            instrument(key)

    def list(self, kind="signals"):
        table = {
            "signals": "strategy_signals",
            "strategies": "strategy_versions",
            "grants": "execution_grants",
        }[kind]
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM " + table).fetchall()
        return [
            {
                **json.loads(r["payload"]),
                **(
                    {
                        "reserved_intents": r["reserved_intents"],
                        "revoked": bool(r["revoked"]),
                    }
                    if kind == "grants"
                    else {}
                ),
            }
            for r in rows
        ]

    def ingest(self, record, *, now_ms):
        for key in [
            "id",
            "strategy",
            "strategy_version",
            "signal_instrument",
            "rationale",
        ]:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError("Signal identity and rationale required")
        if (
            type(record.get("observed_ms")) is not int
            or type(record.get("expires_ms")) is not int
            or not 0 <= record["observed_ms"] <= now_ms < record["expires_ms"]
        ):
            raise ValueError("Signal is expired or has invalid timestamps")
        instrument(record["signal_instrument"])
        self._instruments(record.get("execution_instruments"))
        with self.store.connect() as db:
            strategy = db.execute(
                "SELECT payload FROM strategy_versions WHERE id=? AND version=?",
                (record["strategy"], record["strategy_version"]),
            ).fetchone()
            if not strategy or not set(record["execution_instruments"]) <= set(
                json.loads(strategy[0])["instruments"]
            ):
                raise ValueError("Signal does not match a registered strategy version")
            old = db.execute(
                "SELECT payload FROM strategy_signals WHERE id=?", (record["id"],)
            ).fetchone()
            if old and old[0] != encode(record):
                raise ValueError("Signal ID is immutable")
            db.execute(
                "INSERT OR IGNORE INTO strategy_signals VALUES(?,?)",
                (record["id"], encode(record)),
            )
        return record

    def grant(self, record, *, now_ms):
        for key in ["id", "scope", "strategy", "strategy_version"]:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError("Grant identity required")
        self._instruments(record.get("instruments"))
        decimal(record.get("max_notional"), positive=True)
        if type(record.get("max_intents")) is not int or record["max_intents"] <= 0:
            raise ValueError("Positive grant intent budget required")
        if type(record.get("expires_ms")) is not int or record["expires_ms"] <= now_ms:
            raise ValueError("Grant has expired")
        if type(record.get("live")) is not bool:
            raise ValueError("Grant mode required")
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO execution_grants(id,payload) VALUES(?,?)",
                (record["id"], encode(record)),
            )
        return record

    def revoke(self, grant_id):
        with self.store.connect() as db:
            if (
                db.execute(
                    "UPDATE execution_grants SET revoked=1 WHERE id=?", (grant_id,)
                ).rowcount
                != 1
            ):
                raise ValueError("Unknown grant")
        return {"id": grant_id, "revoked": True}

    def check_authority(self, row, *, now_ms):
        p = row["plan"]
        if p.get("signal_id"):
            with self.store.connect() as db:
                raw = db.execute(
                    "SELECT payload FROM strategy_signals WHERE id=?", (p["signal_id"],)
                ).fetchone()
            if not raw or now_ms >= json.loads(raw[0])["expires_ms"]:
                raise ValueError("Signal expired before entry")
        if not p.get("grant_id"):
            return
        with self.store.connect() as db:
            raw = db.execute(
                "SELECT * FROM execution_grants WHERE id=?", (p["grant_id"],)
            ).fetchone()
        if not raw or raw["revoked"]:
            raise ValueError("Execution grant missing or revoked")
        grant = json.loads(raw["payload"])
        if (
            grant["scope"] != row["scope"]
            or grant["live"] != (row["mode"] == "live")
            or grant["strategy"] != p["strategy"]
            or grant["strategy_version"] != p["strategy_version"]
            or p["instrument"] not in grant["instruments"]
        ):
            raise ValueError("Grant scope does not authorize this plan")
        if now_ms >= grant["expires_ms"]:
            raise ValueError("Execution grant expired")
        if decimal(p["quantity"]) * decimal(p["limit_price"]) > decimal(
            grant["max_notional"]
        ):
            raise ValueError("Grant notional exceeded")

    def execute(
        self, signal_id, scope, plan, *, live=False, manual=False, grant_id=None, now_ms
    ):
        if manual == bool(grant_id):
            raise ValueError("Choose explicit manual authority or a bounded grant")
        with self.store.connect() as db:
            raw = db.execute(
                "SELECT payload FROM strategy_signals WHERE id=?", (signal_id,)
            ).fetchone()
        if not raw:
            raise ValueError("Unknown signal")
        signal = json.loads(raw[0])
        if now_ms >= signal["expires_ms"]:
            raise ValueError("Signal expired")
        if (
            plan["instrument"] not in signal["execution_instruments"]
            or plan["signal_instrument"] != signal["signal_instrument"]
            or plan["strategy"] != signal["strategy"]
            or plan["strategy_version"] != signal["strategy_version"]
        ):
            raise ValueError("Plan does not match signal")
        p = validate_plan(
            {
                **plan,
                "intent_id": "signal:" + signal_id,
                "signal_id": signal_id,
                "grant_id": grant_id,
            },
            now_ms,
        )
        row = {"scope": scope, "mode": "live" if live else "paper", "plan": p}
        with account_lock("signal-intent", scope):
            for existing in self.store.list(scope):
                if (
                    existing["mode"] == row["mode"]
                    and existing["plan"]["intent_id"] == p["intent_id"]
                ):
                    if existing["plan"] != p:
                        raise ValueError("Conflicting signal execution replay")
                    return existing
            self.check_authority(row, now_ms=now_ms)
            if grant_id:
                # Reserve before enqueue. A crash may consume a slot, but cannot grant extra trades.
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    g = db.execute(
                        "SELECT * FROM execution_grants WHERE id=?", (grant_id,)
                    ).fetchone()
                    if (
                        g["revoked"]
                        or g["reserved_intents"]
                        >= json.loads(g["payload"])["max_intents"]
                    ):
                        raise ValueError("Grant revoked or intent budget exhausted")
                    db.execute(
                        "UPDATE execution_grants SET reserved_intents=reserved_intents+1 WHERE id=?",
                        (grant_id,),
                    )
            return self.store.enqueue(scope, p, live=live, now_ms=now_ms)
