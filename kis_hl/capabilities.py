"""Append-only, account-scoped capability evidence; documentation is not live proof."""

import json
import sqlite3
from pathlib import Path

from kis_hl.instruments import capabilities, instrument
from kis_hl.journal_sync import encode


class CapabilityEvidence:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS capability_evidence(
            id INTEGER PRIMARY KEY,scope TEXT NOT NULL,instrument TEXT NOT NULL,capability TEXT NOT NULL,
            status TEXT NOT NULL,checked_ms INTEGER NOT NULL,expires_ms INTEGER NOT NULL,payload TEXT NOT NULL)"""
            )

    def record(
        self, scope, key, capability, status, *, now_ms, expires_ms, evidence, details
    ):
        asset = instrument(key)
        if (
            status not in {"unknown", "documented", "verified", "unsupported"}
            or not evidence
        ):
            raise ValueError("Capability status and evidence required")
        if expires_ms <= now_ms:
            raise ValueError("Capability evidence must have a bounded validity period")
        if capability == "native_stop_loss" and status == "verified":
            if (
                asset.venue != "hyperliquid"
                or details.get("side") != "sell"
                or details.get("reduce_only") is not True
                or details.get("trigger_type") != "sl"
                or details.get("kind") != "stop"
                or details.get("status") != "open"
            ):
                raise ValueError("Verified protective readback required")
        payload = {
            "evidence": evidence,
            "venue": asset.venue,
            "market": asset.market,
            "exchange": asset.order_exchange,
            "currency": asset.currency,
            "details": details,
        }
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO capability_evidence(scope,instrument,capability,status,checked_ms,expires_ms,payload) VALUES(?,?,?,?,?,?,?)",
                (scope, key, capability, status, now_ms, expires_ms, encode(payload)),
            )

    def inspect(self, scope, key, *, now_ms):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """SELECT c.* FROM capability_evidence c WHERE scope=? AND instrument=?
                AND id=(SELECT MAX(x.id) FROM capability_evidence x WHERE x.scope=c.scope
                AND x.instrument=c.instrument AND x.capability=c.capability)""",
                (scope, key),
            ).fetchall()
        return {
            "account_scope": scope,
            "documented": capabilities(key),
            "observations": [
                {
                    **dict(r),
                    "payload": json.loads(r["payload"]),
                    "current": r["expires_ms"] > now_ms,
                }
                for r in rows
            ],
            "note": "Evidence is scoped to its order/session/account. An expired row cannot authorize native protection.",
        }
