"""Fill-triggered journal sync requests, journal notifications and journal status (#58).

Supervisors record a durable request after their state commit; the `market collect`
worker syncs it with bounded retries. New position-change journals are announced
once each through the shared `managed_notifications` outbox that Hermes delivers.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
import json
import logging
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from kis_hl.data_store import encode, now_ms as current_ms

logger = logging.getLogger(__name__)

REQUEST_OVERLAP_MS = 15 * 60_000
BACKOFF_BASE_MS = 30_000
BACKOFF_CAP_MS = 15 * 60_000
BATCH_ENTRY_LIMIT = 20
KST = ZoneInfo("Asia/Seoul")

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_sync_requests(venue TEXT NOT NULL,account TEXT NOT NULL,
    scope TEXT NOT NULL,pending_since_ms INTEGER,requested_ms INTEGER,
    request_count INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_ms INTEGER,last_attempt_ms INTEGER,last_error TEXT,last_success_ms INTEGER,
    last_result TEXT,PRIMARY KEY(venue,account));
CREATE TABLE IF NOT EXISTS journal_notification_baseline(scope TEXT PRIMARY KEY,
    after_run_id INTEGER NOT NULL,created_ms INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS journal_sync_status(scope TEXT PRIMARY KEY,last_attempt_ms INTEGER,
    last_success_ms INTEGER,last_outcome TEXT,last_result TEXT);
CREATE TABLE IF NOT EXISTS journal_notified(journal_id INTEGER PRIMARY KEY,scope TEXT NOT NULL,
    notification_id INTEGER NOT NULL);
"""
REQUEST_FIELDS = ("pending_since_ms", "requested_ms", "request_count", "attempts", "next_attempt_ms",
                  "last_attempt_ms", "last_error", "last_success_ms", "last_result")
# One enablement baseline for all accounts: journals that existed before the first
# notifying sync stay silent; every later journal (any account, any path) is announced.
BASELINE = "*"


def ensure_schema(db):
    """Additive tables beside the checksum-locked canonical schema."""
    db.executescript(SCHEMA)


@contextmanager
def _connect(path, *, readonly=False, timeout=10):
    path = Path(path).expanduser()
    db = (sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout) if readonly
          else sqlite3.connect(path, timeout=timeout))
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _account(venue, account):
    return account.lower() if venue == "hyperliquid" and account else account


def request_sync(path, *, venue, account, scope, since_ms, now_ms, timeout=10):
    """Record or coalesce the one pending request for this venue/account."""
    if venue not in {"hyperliquid", "kis"} or not account or not scope:
        raise ValueError("Journal sync request requires venue, account and scope")
    with _connect(path, timeout=timeout) as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO journal_sync_requests(venue,account,scope,pending_since_ms,requested_ms,request_count,"
            "attempts,next_attempt_ms) VALUES(?,?,?,?,?,1,0,?) ON CONFLICT(venue,account) DO UPDATE SET "
            "scope=excluded.scope,requested_ms=excluded.requested_ms,request_count=request_count+1,"
            "attempts=CASE WHEN pending_since_ms IS NULL THEN 0 ELSE attempts END,"
            "next_attempt_ms=CASE WHEN pending_since_ms IS NULL THEN excluded.next_attempt_ms ELSE next_attempt_ms END,"
            "pending_since_ms=CASE WHEN pending_since_ms IS NULL THEN excluded.pending_since_ms "
            "ELSE min(pending_since_ms,excluded.pending_since_ms) END",
            (venue, _account(venue, account), scope, since_ms, now_ms, now_ms))


def sync_requests(path):
    """All request rows; an absent database or table means none."""
    if not Path(path).expanduser().exists():
        return []
    try:
        with _connect(path, readonly=True) as db:
            return [dict(r) for r in db.execute("SELECT * FROM journal_sync_requests ORDER BY venue,account")]
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return []
        raise


def backoff_ms(attempts):
    return min(BACKOFF_BASE_MS * 2 ** (attempts - 1), BACKOFF_CAP_MS)


def process_requests(store, *, clock, sync=None):
    """Sync every due request; one account's failure never blocks another."""
    if sync is None:
        def sync(venue, account, start_ms):
            return sync_and_notify(store, venue, account, start_ms=start_ms, now_ms=clock)
    with _connect(store.path) as db:
        ensure_schema(db)
        due = [dict(r) for r in db.execute(
            "SELECT * FROM journal_sync_requests WHERE pending_since_ms IS NOT NULL AND next_attempt_ms<=? "
            "ORDER BY next_attempt_ms,venue,account", (clock,))]
    outcomes = []
    for row in due:
        key = (row["venue"], row["account"])
        try:
            result = sync(row["venue"], row["account"], max(0, row["pending_since_ms"] - REQUEST_OVERLAP_MS))
        except Exception as exc:  # Recorded and retried; never propagated to the worker loop.
            attempts = row["attempts"] + 1
            with _connect(store.path) as db:
                db.execute("UPDATE journal_sync_requests SET attempts=?,last_attempt_ms=?,last_error=?,"
                           "next_attempt_ms=? WHERE venue=? AND account=?",
                           (attempts, clock, type(exc).__name__, clock + backoff_ms(attempts), *key))
            logger.warning("journal_sync_request_retry", extra={"venue": row["venue"], "attempts": attempts,
                                                                "error_type": type(exc).__name__})
            outcomes.append({"venue": row["venue"], "status": "failed", "attempts": attempts,
                             "error_type": type(exc).__name__})
            continue
        result = result if isinstance(result, dict) else {}
        summary = _summary(result)
        partial = summary["outcome"] == "partial"
        with _connect(store.path) as db:
            # A fill recorded while this sync ran keeps the request pending for one more pass. An
            # incomplete collection clears the request (retrying cannot fix source gaps) but keeps
            # the success clock and records the unresolved buckets for journal-status.
            db.execute(
                "UPDATE journal_sync_requests SET last_success_ms=CASE WHEN ? THEN last_success_ms ELSE ? END,"
                "last_attempt_ms=?,attempts=0,last_error=?,last_result=?,"
                "pending_since_ms=CASE WHEN request_count=? THEN NULL ELSE pending_since_ms END,"
                "next_attempt_ms=CASE WHEN request_count=? THEN NULL ELSE ? END WHERE venue=? AND account=?",
                (partial, clock, clock, "partial_collection" if partial else None, encode(summary),
                 row["request_count"], row["request_count"], clock, *key))
        outcomes.append({"venue": row["venue"], "status": summary["outcome"],
                         **{k: v for k, v in summary.items() if k != "outcome"}})
    return outcomes


def _summary(result):
    """Counts and sanitized source findings only (no raw bodies or addresses)."""
    summary = {k: result[k] for k in ("fills", "domestic_trades", "overseas_trades", "notification_id") if k in result}
    summary["outcome"] = "partial" if result.get("collection_complete") is False else "success"
    findings = [{k: f.get(k) for k in ("market", "date", "instrument", "reason") if f.get(k) is not None}
                for f in result.get("quality_findings") or [] if isinstance(f, dict)]
    if findings:
        summary["quality_findings"] = findings
    return summary


def max_run_id(store):
    with store.connect() as db:
        return db.execute("SELECT coalesce(max(id),0) FROM analysis_runs").fetchone()[0]


def ensure_baseline(store, *, now_ms, after_run_id=None):
    """Record the enablement baseline once, before any notifying sync ingests."""
    after = max_run_id(store) if after_run_id is None else after_run_id
    with _connect(store.path) as db:
        ensure_schema(db)
        db.execute("INSERT OR IGNORE INTO journal_notification_baseline VALUES(?,?,?)", (BASELINE, after, now_ms))
        return db.execute("SELECT after_run_id FROM journal_notification_baseline WHERE scope=?",
                          (BASELINE,)).fetchone()[0]


def _record_sync(store, scope, result, now_ms):
    summary = _summary(result)
    with _connect(store.path) as db:
        ensure_schema(db)
        # Syncs can finish out of order: success time only moves forward, and only a newer
        # attempt replaces the attempt time, outcome and result.
        db.execute(
            "INSERT INTO journal_sync_status VALUES(?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET "
            "last_outcome=CASE WHEN excluded.last_attempt_ms>=last_attempt_ms THEN excluded.last_outcome ELSE last_outcome END,"
            "last_result=CASE WHEN excluded.last_attempt_ms>=last_attempt_ms THEN excluded.last_result ELSE last_result END,"
            "last_attempt_ms=max(last_attempt_ms,excluded.last_attempt_ms),"
            "last_success_ms=CASE WHEN excluded.last_success_ms IS NULL THEN last_success_ms "
            "WHEN last_success_ms IS NULL THEN excluded.last_success_ms "
            "ELSE max(last_success_ms,excluded.last_success_ms) END",
            (scope, now_ms, now_ms if summary["outcome"] == "success" else None, summary["outcome"], encode(summary)))


def sync_and_notify(store, venue, account, *, start_ms, end_ms=None, client=None, scope=None, now_ms=None):
    """The single sync path for requests, account jobs and `data sync`."""
    from kis_hl.data_account_sync import sync_account
    moment = current_ms() if now_ms is None else now_ms
    ensure_baseline(store, now_ms=moment)  # Before ingestion, so no concurrent sync can hide journals.
    kwargs = {"start_ms": start_ms}
    if end_ms is not None:
        kwargs["end_ms"] = end_ms
    if client is not None:
        kwargs.update(client=client, scope=scope)
    result = sync_account(store, venue, account, **kwargs)
    aid = result.get("account_id") if isinstance(result, dict) else None
    if aid:
        result["notification_id"] = enqueue_journal_notifications(store, aid, now_ms=moment)
        _record_sync(store, aid, result, moment)
    return result


def _pending_journals(store, scope):
    with _connect(store.path) as db:
        ensure_schema(db)
        base = db.execute("SELECT after_run_id FROM journal_notification_baseline WHERE scope=?", (BASELINE,)).fetchone()
        if base is None:
            return []
        return [(r["id"], json.loads(r["result"])) for r in db.execute(
            "SELECT DISTINCT r.id,r.result FROM analysis_runs r JOIN analysis_inputs i ON i.run_id=r.id "
            "JOIN fact_revisions f ON f.id=i.fact_id WHERE r.kind='position_change' AND f.scope=? AND r.id>? "
            "AND r.id NOT IN (SELECT journal_id FROM journal_notified) ORDER BY r.id", (scope, base[0]))]


def _close_pnl(store, scope, entries):
    """Realized PnL for closes, confirmed only for a FINALIZED cycle."""
    from kis_hl.journal_exports import journal_view
    view = journal_view(store, [scope])[0]
    # The reconstructed chronology names the fact that returned inventory to zero.
    closing = {c["closed_fact_id"]: c for c in view["cycles"] if c.get("closed_fact_id") is not None}
    for entry in entries:
        cycle = closing.get(entry["fact_id"])
        if cycle is None:
            if entry["change"] == "close":
                entry["pnl"] = {"status": "pending", "net_pnl": None, "net_return_pct": None,
                                "reasons": ["cycle_unresolved"]}
            continue
        reasons = sorted(set(cycle["reasons"]) | ({"shared_funding"} if cycle["shared_funding_ids"] else set()))
        confirmed = cycle["status"] == "FINALIZED"
        entry["pnl"] = {"status": "confirmed" if confirmed else "pending",
                        "net_pnl": cycle["net_pnl"] if confirmed else None,
                        "net_return_pct": cycle["net_return_pct"] if confirmed else None, "reasons": reasons}


def enqueue_journal_notifications(store, scope, *, now_ms):
    """One outbox batch for journals not yet notified; each journal_id at most once."""
    from kis_hl.managed_execution import ExecutionStore
    pending = _pending_journals(store, scope)
    if not pending:
        return None
    keys = ("journal_id", "fact_id", "instrument", "change", "signed_quantity", "price", "currency",
            "event_start_ms", "time_precision")
    entries = [{k: ({**result, "journal_id": run_id}).get(k) for k in keys} for run_id, result in pending]
    _close_pnl(store, scope, entries)
    ExecutionStore(store.path)  # Ensure the shared outbox exists in this database.
    with _connect(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        ids = [e["journal_id"] for e in entries]
        taken = {r[0] for r in db.execute(
            f"SELECT journal_id FROM journal_notified WHERE journal_id IN ({','.join('?' for _ in ids)})", ids)}
        entries = [e for e in entries if e["journal_id"] not in taken]
        if not entries:
            return None
        venue = db.execute("SELECT venue FROM accounts WHERE id=?", (scope,)).fetchone()
        payload = {"venue": venue[0] if venue else "unknown", "count": len(entries),
                   "entries": entries[:BATCH_ENTRY_LIMIT], "more": max(0, len(entries) - BATCH_ENTRY_LIMIT)}
        note = db.execute(
            "INSERT INTO managed_notifications(position_id,scope,mode,kind,episode_ms,created_ms,payload) "
            "VALUES(?,?,?,?,?,?,?)", (f"journal-batch:{entries[0]['journal_id']}", scope, "live", "journal_batch",
                                      now_ms, now_ms, encode(payload))).lastrowid
        db.executemany("INSERT INTO journal_notified VALUES(?,?,?)",
                       [(e["journal_id"], scope, note) for e in entries])
        return note


def _number(value, *, signed=False):
    text = f"{Decimal(str(value)).normalize():f}"
    return ("+" + text) if signed and not text.startswith("-") and Decimal(text) != 0 else text


def _when(ms, precision):
    moment = datetime.fromtimestamp(ms / 1000, tz=KST)
    if precision == "MILLISECOND":
        return moment.strftime("%Y-%m-%d %H:%M:%S KST")
    return f"{moment:%Y-%m-%d} KST ({precision or 'unknown'} precision)"


def _entry_line(e):
    quantity = _number(e["signed_quantity"], signed=True) if e.get("signed_quantity") is not None else "?"
    price = _number(e["price"]) if e.get("price") is not None else "unknown price"
    line = f"- {e['instrument']} {e['change']} {quantity} @ {price} {e.get('currency') or ''}".rstrip()
    line += f", {_when(e['event_start_ms'], e.get('time_precision'))}"
    pnl = e.get("pnl")
    if pnl and pnl["status"] == "confirmed":
        pct = Decimal(str(pnl["net_return_pct"])).quantize(Decimal("0.01"))
        line += f"; PnL {_number(pnl['net_pnl'], signed=True)} {e.get('currency') or ''} ({'+' if pct > 0 else ''}{pct}%)"
    elif pnl:
        line += f"; PnL pending ({', '.join(pnl['reasons']) or 'unconfirmed'})"
    return line


def journal_message(payload):
    count = payload["count"]
    lines = [f"JOURNAL {payload['venue']}: {count} new entr{'y' if count == 1 else 'ies'}"]
    lines += [_entry_line(e) for e in payload["entries"]]
    if payload.get("more"):
        lines.append(f"... and {payload['more']} more")
    return "\n".join(lines)


def _kst_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=KST).date()


def journal_status(store, accounts=None, *, as_of_ms=None):
    """Read-only journal health: positions, today's entries, statistics, pending items, sync state."""
    from kis_hl.journal_exports import journal_view, statistics, serial
    asof = current_ms() if as_of_ms is None else as_of_ms
    with store.connect() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT id,venue,label,native_id FROM accounts WHERE venue IN ('hyperliquid','kis') ORDER BY venue,id")]
        jobs = [dict(r, config=json.loads(r["config"])) for r in db.execute(
            "SELECT id,config,interval_seconds,last_attempt_ms,last_success_ms,last_reason FROM ingestion_jobs ORDER BY id")]
        worker = db.execute("SELECT max(finished_ms) FROM collection_runs WHERE job_id='worker-heartbeat'").fetchone()[0]
        failures = {r["scope"]: dict(r) for r in db.execute(
            "SELECT scope,dataset,observed_ms,details FROM dataset_coverage WHERE status='failed' ORDER BY id")}
        try:
            synced = {r["scope"]: dict(r) for r in db.execute("SELECT * FROM journal_sync_status")}
        except sqlite3.OperationalError:  # Never written yet; read-only status creates nothing.
            synced = {}
    selected = [r for r in rows if accounts is None or r["id"] in accounts]
    if accounts is not None and len(selected) != len(set(accounts)):
        raise ValueError("Unknown journal-status account")
    view = journal_view(store, [r["id"] for r in selected], as_of_ms=asof, raw=True)[0] if selected else None
    requests = {r["scope"]: r for r in sync_requests(store.path)}
    today = _kst_date(asof)
    # Findings without a scope (inventory/chronology) belong to the account owning their facts.
    finding_facts = sorted({f for i in (view["quality_findings"] if view else []) for f in i.get("fact_ids", [])})
    fact_scope = {}
    if finding_facts:
        with store.connect() as db:
            fact_scope = dict(db.execute(f"SELECT id,scope FROM fact_revisions WHERE id IN "
                                         f"({','.join('?' for _ in finding_facts)})", finding_facts).fetchall())
    venues = Counter(r["venue"] for r in rows)

    def job_owner(job):
        config = job["config"]
        if config.get("kind") != "account":
            return None
        if config.get("account"):
            return next((r["id"] for r in rows if r["venue"] == config.get("venue")
                         and r["native_id"] == _account(config["venue"], config["account"])), None)
        # A default-account job is attributable only when the venue has exactly one account.
        return next((r["id"] for r in rows if r["venue"] == config.get("venue")), None) \
            if venues[config.get("venue")] == 1 else None

    def job_view(job):
        return {k: job[k] for k in ("id", "interval_seconds", "last_attempt_ms", "last_success_ms", "last_reason")}

    result = []
    for account in selected:
        aid = account["id"]
        cycles = [c for c in view["cycles"] if c["account"] == aid]
        closed = [c for c in cycles if c["closed_ms"] is not None]
        unsettled = [c for c in cycles if c["status"] != "FINALIZED"]
        request = requests.get(aid)
        failure = failures.get(aid)
        last_sync = synced.get(aid)
        result.append(serial({
            "account": aid, "label": account["label"], "venue": account["venue"],
            "open_positions": [{"instrument": c["instrument"], "side": c["side"],
                                "quantity": c["entry_quantity"] - c["exit_quantity"], "currency": c["currency"],
                                "opened_ms": c["opened_ms"], "time_precision": c["time_precision"]}
                               for c in cycles if c["status"] == "OPEN"],
            "today": [{k: e.get(k) for k in ("journal_id", "instrument", "change", "signed_quantity", "price",
                                             "currency", "event_start_ms", "time_precision")}
                      for e in view["position_changes"]
                      if e["account"] == aid and _kst_date(e["event_start_ms"]) == today],
            "cycles": {"closed": len(closed), "open": sum(c["status"] == "OPEN" for c in cycles),
                       "by_status": dict(Counter(c["status"] for c in closed)),
                       "statistics": statistics(closed)},
            "pending": {"cycles": len(unsettled),
                        "reasons": dict(Counter(r for c in unsettled for r in set(c["reasons"]))),
                        "quality_findings": dict(Counter(
                            i["kind"] for i in view["quality_findings"]
                            if i.get("scope") == aid or any(fact_scope.get(f) == aid for f in i.get("fact_ids", []))))},
            "sync": {"request": ({**{k: request[k] for k in REQUEST_FIELDS},
                                  "last_result": json.loads(request["last_result"]) if request["last_result"] else None}
                                 if request else None),
                     "last_sync": ({"last_attempt_ms": last_sync["last_attempt_ms"],
                                    "last_success_ms": last_sync["last_success_ms"],
                                    "last_outcome": last_sync["last_outcome"],
                                    "last_result": json.loads(last_sync["last_result"]) if last_sync["last_result"] else None}
                                   if last_sync else None),
                     "jobs": [job_view(j) for j in jobs if job_owner(j) == aid],
                     "last_failure": {"dataset": failure["dataset"], "observed_ms": failure["observed_ms"],
                                      "reason": json.loads(failure["details"]).get("reason")} if failure else None},
        }))
    unattributed = [job_view(j) for j in jobs if j["config"].get("kind") == "account" and job_owner(j) is None]
    return {"as_of_ms": asof, "kst_date": today.isoformat(), "worker_last_seen_ms": worker, "accounts": result,
            "unattributed_jobs": unattributed}


def enqueue_daily_summary(store, status, *, now_ms):
    """One journal_daily outbox row per account and KST date, built from journal_status output."""
    from kis_hl.managed_execution import ExecutionStore
    ExecutionStore(store.path)
    day = status["kst_date"]
    episode = int(datetime.fromisoformat(day).replace(tzinfo=KST).timestamp() * 1000)
    created = []
    with _connect(store.path) as db:
        for account in status["accounts"]:
            payload = {"kst_date": day, **{k: account[k] for k in ("venue", "label", "open_positions", "cycles",
                                                                    "pending", "sync")},
                       "today_count": len(account["today"])}
            cursor = db.execute(
                "INSERT OR IGNORE INTO managed_notifications(position_id,scope,mode,kind,episode_ms,created_ms,payload) "
                "VALUES(?,?,?,?,?,?,?)", (f"journal-daily:{day}:{account['account'][:12]}", account["account"], "live",
                                          "journal_daily", episode, now_ms, encode(payload)))
            if cursor.rowcount == 1:
                created.append(cursor.lastrowid)
    return created


def daily_message(payload):
    stats = payload["cycles"]["statistics"]
    opened = ", ".join(f"{p['instrument']} {p['side']} {_number(p['quantity'])}" for p in payload["open_positions"])
    parts = [f"open {opened}" if opened else "no open positions",
             f"{payload['today_count']} journal entr{'y' if payload['today_count'] == 1 else 'ies'} today",
             f"closed cycles {payload['cycles']['closed']} ({', '.join(f'{k} {v}' for k, v in sorted(payload['cycles']['by_status'].items())) or 'none'})"]
    if stats["trade_count"]:
        def pct(value):
            return "n/a" if value is None else f"{Decimal(str(value)).quantize(Decimal('0.01'))}%"
        parts.append(f"statistics: {stats['trade_count']} finalized, win rate {pct(stats['win_rate_pct'])}, "
                     f"avg profit {pct(stats['average_profit'])}, avg loss {pct(stats['average_loss'])}")
    else:
        n = stats["excluded_count"]
        parts.append(f"statistics pending ({n} cycle{'s' if n != 1 else ''} not finalized)")
    reasons = payload["pending"]["reasons"]
    if reasons:
        parts.append("pending: " + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    sync_state = payload["sync"]
    request, last_sync = sync_state["request"], sync_state.get("last_sync")
    if request and request["pending_since_ms"] is not None:
        sync = "sync request pending"
        if request["attempts"]:
            n = request["attempts"]
            sync += f", {n} failed attempt{'s' if n != 1 else ''} ({request['last_error']})"
    else:
        last = max([request["last_success_ms"] if request else None,
                    last_sync["last_success_ms"] if last_sync else None] +
                   [j["last_success_ms"] for j in sync_state["jobs"]], key=lambda x: x or 0)
        sync = f"last sync {datetime.fromtimestamp(last / 1000, tz=KST):%Y-%m-%d %H:%M KST}" if last else "no successful sync recorded"
    latest = last_sync if last_sync else None
    if latest and latest["last_outcome"] == "partial":
        unresolved = len((latest.get("last_result") or {}).get("quality_findings", []))
        sync += f"; last sync partial ({unresolved} unresolved source bucket{'s' if unresolved != 1 else ''})"
    parts.append(sync)
    name = payload["venue"] if payload["label"] in ("", payload["venue"]) else f"{payload['venue']}, {payload['label']}"
    return f"DAILY JOURNAL {payload['kst_date']} ({name}): " + "; ".join(parts)
