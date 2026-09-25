"""Independent issue-27 lifecycle probes. Temporary SQLite and stub gateway only.

Does not read .env, open exchange sockets, or modify product/test/docs.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import traceback
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from kis_hl.journal_sync import encode
from kis_hl.managed_execution import ExecutionStore, FINISHED
from tests.test_add_lifecycle import AddLifecycleTests
from tests.test_strategy_tools import NOW

ROOT = Path(__file__).resolve().parents[4]
RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"probe": name, "result": "passed" if ok else "failed", "detail": detail})
    print(("PASS " if ok else "FAIL ") + name)
    print(detail)


def case() -> AddLifecycleTests:
    item = AddLifecycleTests()
    item.setUp()
    return item


def tables(path: Path) -> dict:
    db = sqlite3.connect(path)
    try:
        names = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            name: db.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in names
        }
    finally:
        db.close()


def force_state(store: ExecutionStore, row: dict, state: str) -> None:
    """Legacy finished row without going through save()/retirement."""
    updated = {**row, "state": state, "reason": f"probe legacy {state}", "version": row["version"] + 1}
    db = sqlite3.connect(store.path)
    try:
        changed = db.execute(
            "UPDATE managed_positions SET state=?,version=?,snapshot=? WHERE id=? AND version=?",
            (state, updated["version"], encode(updated), row["id"], row["version"]),
        )
        if changed.rowcount != 1:
            raise RuntimeError("legacy state write missed")
        db.commit()
    finally:
        db.close()


def insert_tranche(store: ExecutionStore, tranche: dict) -> None:
    db = sqlite3.connect(store.path)
    try:
        db.execute(
            "INSERT INTO managed_tranches VALUES(?,?,?)",
            (tranche["id"], tranche["position_id"], encode(tranche)),
        )
        db.commit()
    finally:
        db.close()


def cancels(store: ExecutionStore, position_id: str, target: str) -> list[dict]:
    return [
        item
        for item in store.attempts(position_id)
        if item["kind"] == "cancel" and item.get("target_id") == target
    ]


def probe_separate_deadline_and_retry_caps() -> None:
    deadline = case()
    try:
        add = deadline.send_add()
        deadline.g.cancel = lambda *_args: {"status": "submitted"}
        expiry = deadline.plan["expires_ms"]
        budget = deadline.plan["exit_deadline_ms"]
        deadline.worker.step(deadline.row["id"], expiry)
        clock = next(a for a in deadline.store.attempts(deadline.row["id"]) if a["id"] == add["id"])[
            "cancel_started_ms"
        ]
        deadline.worker.step(deadline.row["id"], expiry + budget)
        at_deadline = deadline.store.get(deadline.row["id"])["state"]
        deadline.worker.step(deadline.row["id"], expiry + budget + 1)
        exhausted = deadline.store.get(deadline.row["id"])["state"]
        later = next(a for a in deadline.store.attempts(deadline.row["id"]) if a["id"] == add["id"])
        deadline.worker.step(deadline.row["id"], expiry + budget + 100000)
        ok = (
            clock == expiry
            and len(cancels(deadline.store, deadline.row["id"], add["id"])) == 1
            and at_deadline != "INTERVENTION"
            and exhausted == "INTERVENTION"
            and later["cancel_started_ms"] == expiry
            and len(cancels(deadline.store, deadline.row["id"], add["id"])) == 1
            and budget > 3
        )
        record(
            "deadline-without-using-retry-cap",
            ok,
            f"budget={budget} cap={deadline.plan['max_exit_attempts']} "
            f"at_deadline={at_deadline} after={exhausted} cancels="
            f"{len(cancels(deadline.store, deadline.row['id'], add['id']))}",
        )
    finally:
        deadline.doCleanups()

    retries = case()
    try:
        add = retries.send_add()
        retries.g.cancel = lambda *_args: {"status": "rejected"}
        expiry = retries.plan["expires_ms"]
        cap = retries.plan["max_exit_attempts"]
        for offset in range(cap):
            retries.worker.step(retries.row["id"], expiry + offset)
        retries.worker.step(retries.row["id"], expiry + cap)
        blocked = retries.store.get(retries.row["id"])["state"]
        ok = (
            len(cancels(retries.store, retries.row["id"], add["id"])) == cap
            and blocked == "INTERVENTION"
            and cap < retries.plan["exit_deadline_ms"]
        )
        record(
            "retry-cap-before-deadline",
            ok,
            f"cap={cap} elapsed_ms={cap} deadline={retries.plan['exit_deadline_ms']} "
            f"state={blocked} cancels={len(cancels(retries.store, retries.row['id'], add['id']))}",
        )
    finally:
        retries.doCleanups()


def probe_crash_before_cancel_send_and_partial_fill() -> None:
    item = case()
    try:
        add = item.send_add()
        expiry = item.plan["expires_ms"]
        real_send = item.worker._send

        def fail_cancel(row, kind, now, **values):
            if kind == "cancel":
                raise SystemExit("before cancel send")
            return real_send(row, kind, now, **values)

        item.worker._send = fail_cancel
        try:
            item.worker.step(item.row["id"], expiry)
            raised = False
        except SystemExit:
            raised = True
        item.worker._send = real_send
        reopened = ExecutionStore(item.store.path)
        attempt = next(a for a in reopened.attempts(item.row["id"]) if a["id"] == add["id"])
        before = len(cancels(reopened, item.row["id"], add["id"]))
        Supervisor = type(item.worker)
        worker = Supervisor(reopened, item.g, live=True)
        worker.step(item.row["id"], expiry + 1)
        after = cancels(reopened, item.row["id"], add["id"])
        restored = next(a for a in reopened.attempts(item.row["id"]) if a["id"] == add["id"])
        ok = raised and before == 0 and attempt["cancel_started_ms"] == expiry and len(after) == 1
        ok = ok and restored["cancel_started_ms"] == expiry and after[0]["status"] == "SUBMITTED"
        record(
            "crash-after-clock-before-cancel-row",
            ok,
            f"raised={raised} prior_cancels={before} restarted_cancels={len(after)} "
            f"clock={restored.get('cancel_started_ms')}",
        )
    finally:
        item.doCleanups()

    item = case()
    try:
        item.historical_entry_cancel()
        add = item.send_add()
        expiry = item.plan["expires_ms"]
        item.g.cancel = lambda *_args: {"status": "submitted"}
        item.worker.step(item.row["id"], expiry)
        item.g.fill(add, "0.2", terminal=False)
        real_send = item.worker._send

        def fail_stop(row, kind, now, **values):
            if kind == "stop":
                raise SystemExit("during incremental stop")
            return real_send(row, kind, now, **values)

        item.worker._send = fail_stop
        try:
            item.worker.step(item.row["id"], expiry + 1)
            raised = False
        except SystemExit:
            raised = True
        item.reopen()
        for offset in (2, 3):
            item.worker.step(item.row["id"], expiry + offset)
        owner = item.store.get(item.row["id"])
        ok = (
            raised
            and Decimal(owner["covered_size"]) == Decimal("1.2")
            and len(item.cancels(add["id"])) == 1
            and owner["state"] != "INTERVENTION"
        )
        record(
            "partial-fill-crash-during-stop-then-restart",
            ok,
            f"raised={raised} covered={owner['covered_size']} state={owner['state']} "
            f"cancels={len(item.cancels(add['id']))}",
        )
    finally:
        item.doCleanups()


def probe_owner_clock_attribution() -> None:
    item = case()
    try:
        item.historical_entry_cancel()
        stale = item.store.get(item.row["id"])["cancel_started_ms"]
        add = item.send_add()
        expiry = item.plan["expires_ms"]
        item.worker.step(item.row["id"], expiry)
        attempt = next(a for a in item.store.attempts(item.row["id"]) if a["id"] == add["id"])
        ok = stale < add["created_ms"] and attempt["cancel_started_ms"] == expiry
        ok = ok and len(item.cancels(add["id"])) == 1 and item.store.get(item.row["id"])["state"] != "INTERVENTION"
        record(
            "old-owner-clock-does-not-poison-later-add",
            ok,
            f"stale={stale} add_created={add['created_ms']} attempt_clock={attempt['cancel_started_ms']} "
            f"state={item.store.get(item.row['id'])['state']}",
        )
    finally:
        item.doCleanups()

    item = case()
    try:
        add = item.send_add()
        item.g.cancel = lambda *_args: {"status": "rejected"}
        expiry = item.plan["expires_ms"]
        item.worker.step(item.row["id"], expiry)
        attempt = next(a for a in item.store.attempts(item.row["id"]) if a["id"] == add["id"])
        attempt.pop("cancel_started_ms", None)
        item.store.update_attempt(attempt)
        foreign = add["created_ms"] + 50
        owner = item.store.get(item.row["id"])
        owner["cancel_started_ms"] = foreign
        item.store.save(owner, expiry)
        item.reopen()
        item.worker.step(item.row["id"], expiry + 2)
        restored = next(a for a in item.store.attempts(item.row["id"]) if a["id"] == add["id"])
        # Spec accepts any owner timestamp inside [creation, earliest matching cancel].
        record(
            "in-window-owner-timestamp-is-attributed-by-spec",
            restored["cancel_started_ms"] == foreign,
            f"foreign={foreign} restored={restored.get('cancel_started_ms')} "
            "conforms to inclusive legacy interval; not a supported cross-target timeline",
        )
    finally:
        item.doCleanups()


def probe_cleanup_rollback_status_and_finished_repair() -> None:
    item = case()
    try:
        queued = item.authorize()
        owner = item.store.get(item.row["id"])
        force_state(item.store, owner, "CLOSED")
        second = {
            **queued,
            "id": uuid4().hex,
            "status": "QUEUED",
            "plan": {**queued["plan"], "intent_id": "legacy-second-tranche"},
        }
        insert_tranche(item.store, second)
        signed = item.store.attempt(
            item.store.get(item.row["id"]),
            "add",
            NOW + 6,
            tranche_id="signed-tranche",
            quantity="0.5",
            price="100",
            signature="probe-signature",
        )
        signed_tranche = {
            **queued,
            "id": "signed-tranche",
            "status": "QUEUED",
            "attempt_id": signed["id"],
            "signature": "probe-signature",
        }
        insert_tranche(item.store, signed_tranche)
        import kis_hl.managed_execution as execution

        original_encode = execution.encode
        seen = {"updates": 0}

        def fail_second_retirement(value):
            if isinstance(value, dict) and value.get("retired_ms") == NOW + 8:
                seen["updates"] += 1
                if seen["updates"] == 2:
                    raise RuntimeError("injected tranche write failure")
            return original_encode(value)

        execution.encode = fail_second_retirement
        try:
            try:
                item.store.retire_unsent_adds(item.row["id"], NOW + 8)
                raised = False
            except RuntimeError as exc:
                raised = "injected" in str(exc)
        finally:
            execution.encode = original_encode
        rolled = {tranche["id"]: tranche for tranche in item.store.tranches(item.row["id"])}
        unchanged = (
            rolled[queued["id"]]["status"] == "QUEUED"
            and "retired_ms" not in rolled[queued["id"]]
            and rolled[second["id"]]["status"] == "QUEUED"
            and rolled["signed-tranche"]["signature"] == "probe-signature"
        )
        item.store.retire_unsent_adds(item.row["id"], NOW + 9)
        retired = {tranche["id"]: tranche for tranche in item.store.tranches(item.row["id"])}
        kept = item.store.attempts(item.row["id"])[-1]
        ok = (
            raised
            and unchanged
            and retired[queued["id"]]["status"] == "CANCELED"
            and retired[second["id"]]["status"] == "CANCELED"
            and retired[queued["id"]]["retired_ms"] == NOW + 9
            and retired["signed-tranche"]["status"] == "QUEUED"
            and retired["signed-tranche"]["signature"] == "probe-signature"
            and kept["signature"] == "probe-signature"
            and kept["status"] == "UNKNOWN"
        )
        record(
            "cleanup-rollback-then-signed-retention",
            ok,
            f"raised={raised} updates_before_failure={seen['updates']} "
            f"after={[retired[key]['status'] for key in (queued['id'], second['id'], 'signed-tranche')]} "
            f"attempt={kept['status']}",
        )
    finally:
        item.doCleanups()

    from kis_hl.cli import main

    item = case()
    try:
        queued = item.authorize()
        before_owner = item.store.get(item.row["id"])
        force_state(item.store, before_owner, "CLOSED")
        queued = item.store.tranches(item.row["id"])[0]
        scope = type("Scope", (), {"key": "scope"})()
        before = tables(item.store.path)
        output = io.StringIO()
        with patch("kis_hl.cli.load_env_file"), patch(
            "kis_hl.operations_cli.scope_client", return_value=(scope, object())
        ), patch("socket.socket", side_effect=AssertionError("probe forbids sockets")), contextlib.redirect_stdout(
            output
        ):
            order_code = main(["--db", str(item.store.path), "order", "status", "--id", item.row["id"]])
            supervisor_code = main(
                ["--db", str(item.store.path), "supervisor", "status", "--venue", "hyperliquid"]
            )
        after = tables(item.store.path)
        decoder = json.JSONDecoder()
        text = output.getvalue()
        parsed = []
        index = 0
        while index < len(text):
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                break
            payload, index = decoder.raw_decode(text, index)
            parsed.append(payload)
        order_status, supervisor_status = parsed
        item.reopen()
        calls = {"n": 0}
        real = item.store.retire_unsent_adds

        def counting(*args, **kwargs):
            calls["n"] += 1
            return real(*args, **kwargs)

        item.store.retire_unsent_adds = counting
        item.worker.step(item.row["id"], NOW + 14)
        repaired = item.store.tranches(item.row["id"])[0]
        ok = (
            order_code == 0
            and supervisor_code == 0
            and before == after
            and order_status["tranches"][0]["status"] == "QUEUED"
            and supervisor_status["positions"][0]["pending_adds"][0]["status"] == "QUEUED"
            and calls["n"] == 1
            and repaired["status"] == "CANCELED"
            and repaired["retired_ms"] == NOW + 14
            and queued["plan"] == repaired["plan"]
            and queued["sizing"] == repaired["sizing"]
        )
        record(
            "status-read-purity-and-supervisor-repair",
            ok,
            f"codes={(order_code, supervisor_code)} db_unchanged={before == after} "
            f"retire_calls_on_step={calls['n']} repaired={repaired['status']}",
        )
    finally:
        item.doCleanups()

    observed = []
    for state in ("CLOSED", "REJECTED", "PREVIEWED"):
        item = case()
        try:
            queued = item.authorize()
            owner = item.store.get(item.row["id"])
            force_state(item.store, owner, state)
            preserved = {**queued, "status": "UNKNOWN", "signature": "keep"}
            item.store.save_tranche(preserved)
            # Restore the unknown tranche after save_tranche, then step through repair.
            item.reopen()
            item.worker.step(item.row["id"], NOW + 15)
            current = item.store.tranches(item.row["id"])[0]
            fresh = {**queued, "status": "QUEUED"}
            item.store.save_tranche(fresh)
            item.worker.step(item.row["id"], NOW + 16)
            retired = item.store.tranches(item.row["id"])[0]
            observed.append(
                {
                    "state": state,
                    "preserved_status": current["status"],
                    "preserved_signature": current.get("signature"),
                    "retired_status": retired["status"],
                    "retired_ms": retired.get("retired_ms"),
                    "owner_column": state in FINISHED,
                }
            )
        finally:
            item.doCleanups()
    ok = all(
        row["preserved_status"] == "UNKNOWN"
        and row["preserved_signature"] == "keep"
        and row["retired_status"] == "CANCELED"
        and row["retired_ms"] == NOW + 16
        for row in observed
    )
    record("finished-states-repair-only-unsent-queued", ok, json.dumps(observed))


def probe_admission_boundary() -> None:
    item = case()
    try:
        owner = item.store.get(item.row["id"])
        owner["state"] = "ENTERING"
        item.store.save(owner, NOW + 1)
        before = len(item.g.sent)
        rejected = False
        try:
            item.signals.execute("add-once", "scope", item.plan, manual=True, live=True, now_ms=NOW + 2)
        except (ValueError, RuntimeError):
            rejected = True
        ok = rejected and len(item.g.sent) == before and item.store.tranches(item.row["id"]) == []
        record(
            "entering-owner-add-is-rejected",
            ok,
            f"rejected={rejected} sent_delta={len(item.g.sent) - before}",
        )
    finally:
        item.doCleanups()


def main() -> None:
    probes = (
        probe_separate_deadline_and_retry_caps,
        probe_crash_before_cancel_send_and_partial_fill,
        probe_owner_clock_attribution,
        probe_cleanup_rollback_status_and_finished_repair,
        probe_admission_boundary,
    )
    for probe in probes:
        try:
            probe()
        except Exception:
            record(probe.__name__, False, traceback.format_exc())
    failed = [item for item in RESULTS if item["result"] != "passed"]
    print(json.dumps({"probes": len(RESULTS), "failed": len(failed), "results": RESULTS}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
