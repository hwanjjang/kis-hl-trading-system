"""Read-only history adapters. Cumulative KIS rows are retained as snapshots."""

from __future__ import annotations
from datetime import datetime
from dataclasses import replace
import hashlib
import json
import time
from zoneinfo import ZoneInfo

from kis_hl.journal_sync import Fill, decimal, encode


def fetch_time_pages(fetch, start, end, *, limit, max_requests=256):
    """Bisect capped inclusive windows; a saturated millisecond is incomplete."""
    pending = [(start, end)]
    result = []
    calls = 0
    while pending:
        a, b = pending.pop()
        calls += 1
        if calls > max_requests:
            raise RuntimeError("History request limit reached")
        rows = fetch(a, b)
        if not isinstance(rows, list) or any(
            not isinstance(r, dict)
            or type(r.get("time")) is not int
            or not a <= r["time"] <= b
            for r in rows
        ):
            raise RuntimeError("Malformed or out-of-window history response")
        if len(rows) >= limit:
            if a == b:
                raise RuntimeError(
                    "Saturated history timestamp requires statement backfill"
                )
            mid = (a + b) // 2
            pending.extend([(mid + 1, b), (a, mid)])
        else:
            result.extend(rows)
    return sorted(result, key=lambda r: r["time"])


def hyperliquid_fill(row):
    coin = str(row["coin"])
    if coin.startswith("@") or "/" in coin:
        raise ValueError(
            "Unresolved spot identity and fee conversion require statement import"
        )
    fee_currency = str(row["feeToken"]).strip()
    if fee_currency != "USDC":
        raise ValueError(
            "Perpetual collateral/cost currency requires explicit verification"
        )
    if row["side"] not in {"B", "A"}:
        raise ValueError("Unknown execution side")
    result = Fill(
        str(row["tid"]),
        coin,
        int(row["time"]),
        "buy" if row["side"] == "B" else "sell",
        str(row["sz"]),
        str(row["px"]),
        "USDC",
        fee=str(row["fee"]),
        order_id=str(row["oid"]),
        position_before=str(row["startPosition"]),
    )
    result.validate()
    return result


def sync_hyperliquid(store, scope, info, *, start_ms, end_ms):
    facts = []
    costs = []
    complete = False
    costs_complete = False
    reason = ""
    anchor = None
    normalization_ok = False
    try:
        raw = fetch_time_pages(
            lambda a, b: info.user_fills_by_time(start_time_ms=a, end_time_ms=b),
            start_ms,
            end_ms,
            limit=2000,
        )
        # Observe the retained boundary after paging, so intervening eviction cannot
        # make an earlier anchor certify an incomplete read.
        tail = info.user_fills()
        if not isinstance(tail, list) or any(
            type(r.get("time")) is not int for r in tail
        ):
            raise ValueError("Malformed retention anchor")
        if tail:
            anchor = min(r["time"] for r in tail)
        for row in raw:
            try:
                facts.append(attribute_fill(store, scope, hyperliquid_fill(row)))
            except (ValueError, KeyError, TypeError):
                retain_unresolved(store, scope, "hyperliquid_fill", row, end_ms)
                reason = "Unresolved source executions require statement import"
        complete = not reason and anchor is not None and start_ms >= anchor
        normalization_ok = not reason
        funding = fetch_time_pages(
            lambda a, b: info.user_funding(start_time_ms=a, end_time_ms=b),
            start_ms,
            end_ms,
            limit=500,
        )
        for row in funding:
            delta = row["delta"]
            costs.append(
                {
                    "event_id": str(row["hash"]) + ":" + delta["coin"],
                    "symbol": delta["coin"],
                    "time_ms": row["time"],
                    "currency": "USDC",
                    "amount": str(-decimal(delta["usdc"])),
                }
            )
        costs_complete = True
        if not complete:
            reason = (
                reason
                or "Requested interval predates verified retention boundary; statement backfill required"
            )
    except (RuntimeError, ValueError, KeyError, TypeError):
        reason = reason or "History incomplete; retry or import a source statement"
    result = store.ingest(
        scope,
        facts,
        start_ms=start_ms,
        end_ms=end_ms,
        source="Hyperliquid info history",
        allow_attribution_enrichment=True,
        complete=complete,
        costs_complete=costs_complete,
        costs=costs,
        reason=reason,
    )
    if (
        not complete
        and costs_complete
        and normalization_ok
        and anchor is not None
        and anchor <= end_ms
    ):
        result = store.ingest(
            scope,
            [],
            start_ms=max(anchor, start_ms),
            end_ms=end_ms,
            source="Hyperliquid retained-tail boundary",
            complete=True,
            costs_complete=True,
        )
    result.update(run_complete=complete and costs_complete, run_reason=reason)
    return result


def attribute_fill(store, scope, fill):
    """Only globally unique HL native order IDs establish automatic attribution."""
    if scope.venue != "hyperliquid" or not fill.order_id:
        return fill
    with store.connect() as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='managed_attempts'"
        ).fetchone():
            return fill
        rows = db.execute(
            "SELECT a.snapshot,p.snapshot FROM managed_attempts a JOIN managed_positions p ON p.id=a.position_id WHERE p.scope=? AND p.mode=?",
            (scope.key, "live"),
        ).fetchall()
    matches = []
    from kis_hl.instruments import instrument

    for attempt, position in rows:
        a, p = json.loads(attempt), json.loads(position)
        if (
            a["kind"] != "cancel"
            and str(a.get("order_id")) == fill.order_id
            and a["created_ms"] <= fill.time_ms
            and instrument(p["plan"]["instrument"]).symbol == fill.symbol
        ):
            matches.append(p["plan"])
    if len(matches) == 1:
        p = matches[0]
        return replace(
            fill,
            strategy=p["strategy"],
            origin="agent",
            strategy_version=p["strategy_version"],
            harness=p.get("harness", "unknown"),
            signal_id=p.get("signal_id") or "",
        )
    return fill


def retain_unresolved(store, scope, kind, payload, time_ms):
    # Only explicit trading fields; vendor payloads can contain account identifiers.
    allowed = {
        "coin",
        "tid",
        "oid",
        "hash",
        "time",
        "side",
        "sz",
        "px",
        "fee",
        "feeToken",
        "startPosition",
        "ord_dt",
        "odno",
        "orgn_odno",
        "ord_gno_brno",
        "pdno",
        "sll_buy_dvsn_cd",
        "sll_buy_dvsn",
        "ord_tmd",
        "tot_ccld_qty",
        "tot_ccld_amt",
        "avg_prvs",
        "ft_ccld_qty",
        "ft_ccld_unpr3",
        "nccs_qty",
        "ord_qty",
        "ovrs_excg_cd",
        "cncl_yn",
    }
    safe = {k: v for k, v in payload.items() if k in allowed}
    body = encode(safe)
    key = hashlib.sha256(encode([kind, safe]).encode()).hexdigest()
    with store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS journal_source_snapshots(scope TEXT, snapshot_id TEXT, kind TEXT, payload TEXT, observed_ms INTEGER, PRIMARY KEY(scope,snapshot_id))"
        )
        db.execute(
            "INSERT OR IGNORE INTO journal_source_snapshots VALUES(?,?,?,?,?)",
            (scope.key, key, kind, body, time_ms),
        )


def sync_kis(store, scope, client, *, start_ms, end_ms):
    count = 0
    for market, zone in [("domestic", "Asia/Seoul"), ("overseas", "America/New_York")]:
        start = datetime.fromtimestamp(start_ms / 1000, ZoneInfo(zone)).strftime(
            "%Y%m%d"
        )
        end = datetime.fromtimestamp(end_ms / 1000, ZoneInfo(zone)).strftime("%Y%m%d")
        data = client.account_pages(
            market + "_history", date_from=start, date_to=end, exchange="NASD"
        )
        rows = data["output1"] if market == "domestic" else data["output"]
        for row in rows:
            retain_unresolved(
                store, scope, "kis_" + market + "_order_summary", row, end_ms
            )
            count += 1
    # These APIs report order summaries, not a guaranteed per-execution timestamp/fee ledger.
    result = store.ingest(
        scope,
        [],
        start_ms=start_ms,
        end_ms=end_ms,
        source="KIS cumulative order history",
        complete=False,
        costs_complete=False,
        reason="Order snapshots collected; execution timestamps and costs require source statement",
    )
    return {
        **result,
        "order_snapshots": count,
        "run_complete": False,
        "collection_complete": True,
        "run_reason": "KIS summaries retained; import execution/cost statement to finalize journals",
    }
