"""Harness-neutral account, instrument, managed order and journal commands."""

from dataclasses import asdict, replace
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import time
from pathlib import Path

from kis_hl.config import load_kis_config, load_hyperliquid_config
from kis_hl.execution_lock import account_lock
from kis_hl.instruments import instrument, list_instruments, capabilities
from kis_hl.journal_sync import Fill, JournalLedger, Scope, SyncSchedule, encode
from kis_hl.journal_history import sync_hyperliquid, sync_kis
from kis_hl.kis.client import KisClient
from kis_hl.hyperliquid.client import HyperliquidInfoClient, HyperliquidTradingClient
from kis_hl.managed_execution import ExecutionStore, Supervisor, TERMINAL, validate_plan


def kis_client():
    config = load_kis_config()
    digest = hashlib.sha256(
        json.dumps([config.app_key, config.app_secret]).encode()
    ).hexdigest()
    return KisClient(replace(config, token_dir=config.token_dir / digest))


def scope_client(venue, account=None):
    if venue == "kis":
        client = kis_client()
        if account and account != client.config.account_id:
            raise ValueError("Requested KIS account differs from configured account")
        return Scope("kis", client.config.mode, client.config.account_id), client
    config = load_hyperliquid_config()
    if account and account.lower() != config.account_address.lower():
        # An explicit public-read override must never retain a signer or silently
        # carry the configured subaccount route into a different account scope.
        config = replace(config, account_address=account, private_key="",
                         master_account_address="", subaccount_address="")
    return Scope(
        "hyperliquid",
        "testnet" if "testnet" in config.base_url else "mainnet",
        config.account_address,
    ), HyperliquidInfoClient(config)


def add_commands(sub, journal_sub):
    ins = sub.add_parser(
        "instrument", help="Inspect explicit signal/execution mappings"
    )
    ins_sub = ins.add_subparsers(dest="instrument_action", required=True)
    ins_sub.add_parser("list").set_defaults(
        handler=lambda a: {"instruments": list_instruments()}
    )
    cap = ins_sub.add_parser("capabilities")
    cap.add_argument("--instrument", required=True)
    cap.set_defaults(handler=lambda a: capabilities(a.instrument))
    verify = ins_sub.add_parser(
        "verify", help="Read venue instrument metadata without orders"
    )
    verify.add_argument("--instrument", required=True)
    verify.set_defaults(handler=cmd_verify_instrument)
    capability = sub.add_parser(
        "capability", help="Inspect account-scoped capability evidence"
    )
    capability.add_argument("action", choices=["inspect"])
    capability.add_argument("--instrument", required=True)
    capability.add_argument("--account")
    capability.add_argument(
        "--environment", choices=["live", "sim", "mainnet", "testnet"]
    )
    capability.set_defaults(handler=cmd_capability)
    chart = sub.add_parser("chart", help="Read an explicitly named analysis series")
    chart.add_argument("--instrument", required=True)
    chart.add_argument("--date-from", required=True)
    chart.add_argument("--date-to", required=True)
    chart.add_argument("--exchange", help="Explicit quote route for an unresolved ETF")
    chart.set_defaults(handler=cmd_chart)
    account = sub.add_parser(
        "account", help="Read account positions/orders/history/buying power"
    )
    account.add_argument(
        "view", choices=["positions", "orders", "history", "buying-power", "capital"]
    )
    account.add_argument("--venue", choices=["kis", "hyperliquid"], required=True)
    account.add_argument(
        "--market", choices=["domestic", "overseas"], default="domestic"
    )
    account.add_argument("--instrument")
    account.add_argument("--price", default="0")
    account.add_argument("--date-from")
    account.add_argument("--date-to")
    account.add_argument("--dex")
    account.add_argument("--older-history", action="store_true")
    account.set_defaults(handler=cmd_account)
    for action in [
        "sync",
        "run",
        "status",
        "report",
        "configure",
        "import",
        "reconcile",
    ]:
        j = journal_sub.add_parser(
            action, help="Account-wide execution journal " + action
        )
        j.add_argument("--venue", choices=["kis", "hyperliquid"], required=True)
        j.add_argument("--account", help="Explicit account scope (read/import only)")
        if action in {"status", "report", "configure"}:
            j.add_argument(
                "--environment", choices=["live", "sim", "mainnet", "testnet"]
            )
        if action == "import":
            j.add_argument("--input", required=True)
            j.add_argument(
                "--environment",
                choices=["live", "sim", "mainnet", "testnet"],
                required=True,
            )
            j.add_argument("--allow-corrections", action="store_true")
        if action in {"sync", "run"}:
            j.add_argument(
                "--start-ms",
                type=int,
                help="Initial backfill start; required before first collection",
            )
            j.add_argument("--end-ms", type=int)
        if action == "run":
            j.add_argument("--once", action="store_true")
            j.add_argument("--poll-seconds", type=int, default=30)
        if action == "configure":
            j.add_argument("--interval-seconds", type=int, required=True)
        if action == "report":
            j.add_argument("--strategy")
        j.set_defaults(handler=cmd_journal_sync, sync_action=action)
    orders = sub.add_parser(
        "order", help="Preview or queue a protected trade plan; no default live writes"
    )
    order_sub = orders.add_subparsers(dest="order_action", required=True)
    for action in ["prepare", "preview", "submit"]:
        c = order_sub.add_parser(action)
        c.add_argument("--input", required=True)
        if action == "submit":
            c.add_argument("--live", action="store_true")
        c.set_defaults(handler=cmd_order)
    adopt = order_sub.add_parser("adopt", help="Queue explicit management of an existing protected HL long")
    adopt.add_argument("--input", required=True)
    adopt.add_argument("--entry-order-id", type=int, required=True)
    adopt.add_argument("--stop-order-id", type=int, required=True)
    adopt.add_argument("--live", action="store_true")
    adopt.set_defaults(handler=cmd_order)
    for action in ["status", "cancel", "exit", "recover"]:
        c = order_sub.add_parser(action)
        c.add_argument("--id", required=True)
        c.set_defaults(handler=cmd_order)
    amend = order_sub.add_parser(
        "amend",
        help="Replace an unsent plan; active entries require cancel/reconciliation",
    )
    amend.add_argument("--id", required=True)
    amend.add_argument("--input", required=True)
    amend.set_defaults(handler=cmd_order)
    sup = sub.add_parser(
        "supervisor", help="Multiplex managed positions under one account owner"
    )
    sup.add_argument(
        "action", choices=["run", "status", "pause-entries", "resume-entries"]
    )
    sup.add_argument("--venue", choices=["kis", "hyperliquid"], required=True)
    sup.add_argument("--live", action="store_true")
    sup.add_argument("--once", action="store_true")
    sup.add_argument("--poll-seconds", type=float, default=1)
    sup.set_defaults(handler=cmd_supervisor)
    strategy = sub.add_parser(
        "strategy", help="Register versioned skills and bounded execution grants"
    )
    ss = strategy.add_subparsers(dest="strategy_action", required=True)
    for action in ["evaluate", "indicators", "stop", "size", "decide"]:
        c = ss.add_parser(action, help="Deterministic strategy evidence; no order submission")
        c.add_argument("--input", required=True)
        if action != "decide":
            c.add_argument("--as-of-ms", type=int, help="Explicit offline replay clock; no order authority")
        c.set_defaults(handler=cmd_strategy_tool)
    for action in ["list", "register", "grant", "revoke", "grants"]:
        c = ss.add_parser(action)
        c.set_defaults(handler=cmd_strategy)
        if action in {"register", "grant"}:
            c.add_argument("--input", required=True)
        if action == "grant":
            c.add_argument("--venue", choices=["kis", "hyperliquid"], required=True)
            c.add_argument("--live", action="store_true")
        if action == "revoke":
            c.add_argument("--id", required=True)
    signal = sub.add_parser(
        "signal", help="Store skill outputs separately from order authority"
    )
    ss = signal.add_subparsers(dest="signal_action", required=True)
    for action in ["list", "ingest", "execute"]:
        c = ss.add_parser(action)
        c.set_defaults(handler=cmd_signal)
        if action in {"ingest", "execute"}:
            c.add_argument("--input", required=True)
        if action == "execute":
            c.add_argument("--id", required=True)
            c.add_argument("--manual", action="store_true")
            c.add_argument("--grant")
            c.add_argument("--live", action="store_true")


def cmd_chart(args):
    asset = instrument(args.instrument)
    start = datetime.strptime(args.date_from, "%Y%m%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.date_to, "%Y%m%d").replace(tzinfo=timezone.utc)
    if start > end:
        raise ValueError("Reversed chart dates")
    if asset.venue == "hyperliquid":
        r = HyperliquidInfoClient(load_hyperliquid_config()).candle_snapshot(
            asset.symbol,
            interval="1d",
            start_time_ms=int(start.timestamp() * 1000),
            end_time_ms=int(end.timestamp() * 1000),
        )
        body = r
    else:
        c = kis_client()
        if asset.market in {"domestic", "domestic_index"}:
            r = c.domestic_chart(
                symbol=asset.symbol,
                date_from=args.date_from,
                date_to=args.date_to,
                index=asset.market == "domestic_index",
            )
        elif asset.market == "overseas_index":
            r = c.inquire_overseas_daily_chartprice(
                symbol=asset.symbol, date_from=args.date_from, date_to=args.date_to
            )
        else:
            exchange = args.exchange or asset.quote_exchange
            if not exchange:
                raise ValueError(
                    "Unverified KIS quote route; explicit --exchange required"
                )
            r = c.overseas_stock_chart(
                symbol=asset.symbol, exchange=exchange, end_date=args.date_to
            )
        if (
            r.status >= 400
            or not isinstance(r.body, dict)
            or r.body.get("rt_cd") != "0"
        ):
            raise RuntimeError("KIS chart inquiry failed")
        body = r.body
    return {
        "instrument": asdict(asset),
        "source": "venue_api",
        "requested_from": args.date_from,
        "requested_to": args.date_to,
        "interval": "1d",
        "coverage": "returned page only; verify history depth before strategy use",
        "timezone": (
            "UTC"
            if asset.venue == "hyperliquid"
            else (
                "Asia/Seoul"
                if asset.market.startswith("domestic")
                else "America/New_York"
            )
        ),
        "currency": asset.currency,
        "requires_complete_bar_filter": True,
        "adjustment": (
            "vendor adjusted"
            if asset.venue == "kis" and "index" not in asset.market
            else "vendor native"
        ),
        "price_basis": "index" if "index" in asset.market else "execution instrument",
        "data": body,
    }


def cmd_account(args):
    scope, client = scope_client(args.venue)
    if args.view == "capital":
        if args.venue != "hyperliquid":
            raise ValueError("Account-total capture currently supports Hyperliquid only")
        from kis_hl.account_capital import capture_capital, reconcile_capital
        evidence = capture_capital(client, scope=scope.key, now_ms=int(time.time()*1000), max_age_ms=60000)
        return {"capital_evidence": evidence, "reconciliation": reconcile_capital(
            evidence, scope=scope.key, now_ms=int(time.time()*1000), max_age_ms=60000)}
    if args.venue == "hyperliquid":
        if args.view == "positions":
            data = client.clearinghouse_state(dex=args.dex)
        elif args.view == "orders":
            data = client.frontend_open_orders(dex=args.dex)
        elif args.view == "history":
            if not args.date_from or not args.date_to:
                raise ValueError("History dates required")
            from kis_hl.journal_history import fetch_time_pages

            start = int(
                datetime.strptime(args.date_from, "%Y%m%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
                * 1000
            )
            end = (
                int(
                    datetime.strptime(args.date_to, "%Y%m%d")
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                    * 1000
                )
                + 86399999
            )
            data = fetch_time_pages(
                lambda a, b: client.user_fills_by_time(start_time_ms=a, end_time_ms=b),
                start,
                end,
                limit=2000,
            )
        else:
            data = client.clearinghouse_state(dex=args.dex)
    else:
        kind = {
            "positions": "balance",
            "orders": "orders",
            "history": "history",
            "buying-power": "buying_power",
        }[args.view]
        asset = instrument(args.instrument) if args.instrument else None
        data = client.account_pages(
            args.market + "_" + kind,
            exchange=asset.order_exchange if asset else "NASD",
            symbol=asset.symbol if asset else "",
            price=args.price,
            date_from=args.date_from or "",
            date_to=args.date_to or "",
            older_history=args.older_history,
        )
    return {
        "account_scope": scope.key,
        "environment": scope.environment,
        "data": redact(data),
    }


def redact(value):
    if isinstance(value, dict):
        return {
            k: redact(v)
            for k, v in value.items()
            if k.lower()
            not in {
                "cano",
                "acnt_prdt_cd",
                "account",
                "account_id",
                "account_address",
                "user",
                "appkey",
                "appsecret",
                "access_token",
            }
        }
    if isinstance(value, list):
        return [redact(x) for x in value]
    return value


def cmd_journal_sync(args):
    store = JournalLedger(args.db)
    now = int(time.time() * 1000)
    if args.sync_action == "import":
        if not args.account:
            raise ValueError("Import requires explicit --account scope")
        scope = Scope(args.venue, args.environment, args.account)
        raw = json.loads(Path(args.input).read_text())
        if raw.get("schema_version") != 1:
            raise ValueError("Unsupported statement schema")
        # Account identities are supplied by the operator, not read from an arbitrary file.
        return store.ingest(
            scope,
            [Fill(**f) for f in raw["fills"]],
            start_ms=raw["start_ms"],
            end_ms=raw["end_ms"],
            source=raw["source"],
            complete=raw["complete"],
            costs_complete=raw["costs_complete"],
            costs=raw.get("costs", []),
            allow_corrections=args.allow_corrections,
        )
    if (
        args.sync_action in {"status", "report", "configure"}
        and args.account
        and args.environment
    ):
        scope, client = Scope(args.venue, args.environment, args.account), None
    else:
        scope, client = scope_client(args.venue, args.account)
    schedule = SyncSchedule(store, scope)
    if args.sync_action == "status":
        return {**store.status(scope), "schedule": schedule.settings()}
    if args.sync_action == "report":
        return store.report(scope, strategy=args.strategy)
    if args.sync_action == "configure":
        return schedule.configure(args.interval_seconds, now_ms=now)
    if args.sync_action == "reconcile":
        holdings = {}
        if args.venue == "hyperliquid":
            for dex in [None, "xyz"]:
                for row in client.clearinghouse_state(dex=dex)["assetPositions"]:
                    p = row["position"]
                    holdings[p["coin"]] = p["szi"]
        else:
            for market in ["domestic", "overseas"]:
                for row in client.account_pages(market + "_balance", exchange="NASD")[
                    "output1"
                ]:
                    holdings[row["pdno"]] = row[
                        "hldg_qty" if market == "domestic" else "ovrs_cblc_qty"
                    ]
        return store.reconcile_holdings(scope, holdings, now_ms=now)
    if args.sync_action == "run" and args.poll_seconds <= 0:
        raise ValueError("Positive scheduler poll interval required")
    while True:
        with ExitStack() as locks:
            try:
                locks.enter_context(
                    account_lock("journal:" + scope.environment, scope.key)
                )
            except RuntimeError:
                if args.sync_action == "sync" or args.once:
                    raise
                time.sleep(min(args.poll_seconds, 60))
                continue
            now = int(time.time() * 1000)
            if args.sync_action == "sync" or schedule.due(now):
                end = args.end_ms if args.end_ms is not None else now
                status = store.status(scope)
                start = (
                    args.start_ms
                    if args.start_ms is not None
                    else status["reconciled_until_ms"]
                )
                # KIS snapshot collection has a separate successful-run clock, not fabricated fill coverage.
                if start is None:
                    start = schedule.settings()["last_success_ms"]
                if start is None:
                    raise ValueError(
                        "First sync requires --start-ms for explicit history scope"
                    )
                start = max(0, start - 86400000) if args.start_ms is None else start
                if end < start:
                    raise ValueError("Reversed synchronization interval")
                try:
                    result = (sync_kis if args.venue == "kis" else sync_hyperliquid)(
                        store, scope, client, start_ms=start, end_ms=end
                    )
                except Exception:
                    store.ingest(
                        scope,
                        [],
                        start_ms=start,
                        end_ms=end,
                        source="failed sync",
                        complete=False,
                        costs_complete=False,
                        reason="Account history collection failed",
                    )
                    if args.sync_action == "sync" or args.once:
                        schedule.attempted(
                            int(time.time() * 1000), "Account history collection failed"
                        )
                        raise RuntimeError(
                            "Journal synchronization failed; cursor unchanged"
                        ) from None
                    result = {
                        "run_complete": False,
                        "run_reason": "Collection failed; retry on next poll",
                    }
                if result.get("run_complete") or result.get("collection_complete"):
                    schedule.success(int(time.time() * 1000))
                else:
                    schedule.attempted(
                        int(time.time() * 1000),
                        result.get("run_reason") or "History coverage incomplete",
                    )
                if args.sync_action == "sync" or args.once:
                    return result
            elif args.once:
                return {"due": False, "schedule": schedule.settings()}
        # Release the account collection lock before waiting for the next poll.
        time.sleep(min(args.poll_seconds, 60))


def cmd_order(args):
    store = ExecutionStore(args.db)
    now = int(time.time() * 1000)
    if args.order_action == "adopt":
        p = validate_plan(json.loads(Path(args.input).read_text()), now)
        asset = instrument(p["instrument"])
        instrument(p["signal_instrument"])
        scope, _ = scope_client(asset.venue)
        return store.enqueue_adoption(scope.key, p, entry_order_id=args.entry_order_id,
                                      stop_order_id=args.stop_order_id, live=args.live, now_ms=now)
    if args.order_action == "prepare":
        from kis_hl.managed_gateways import ManagedKisGateway

        p = json.loads(Path(args.input).read_text())
        asset = instrument(p["instrument"])
        scope, client = scope_client(asset.venue)
        if asset.venue == "kis":
            atr, source = ManagedKisGateway(client)._atr(asset, now)
        else:
            from kis_hl.trailing_runner import fetch_trailing_atr

            atr, bars = fetch_trailing_atr(client, asset.symbol, now_ms=now)
            source = {
                "instrument": asset.id,
                "basis": "Hyperliquid closed daily bars",
                "last_bar_end_ms": bars[-1]["T"],
            }
        return {
            "dry_run": True,
            "plan": validate_plan({**p, "atr": str(atr)}, now),
            "atr_source": source,
        }
    if args.order_action in {"preview", "submit"}:
        p = validate_plan(json.loads(Path(args.input).read_text()), now)
        if p.get("action") == "add":
            if args.order_action == "submit":
                raise ValueError("Use signal execute for bounded add authority")
            from kis_hl.conditional_add import validate_add
            from kis_hl.strategy_signals import Signals
            owner = store.get(p["position_id"])
            signal = next((s for s in Signals(store).list() if s["id"] == p.get("signal_id")), None)
            if signal is None:
                raise ValueError("Add preview requires a registered signal_id for evidence expiry")
            return {"dry_run": True, "plan": p, "sizing": validate_add(p, owner, signal, now, preview=True),
                "authority_required": True}
        if p.get("signal_id") or p.get("grant_id"):
            raise ValueError("Use signal execute for signal/grant authority")
        asset = instrument(p["instrument"])
        instrument(p["signal_instrument"])
        if args.order_action == "preview":
            return {"dry_run": True, "plan": p, "capabilities": capabilities(asset.id)}
        scope, client = scope_client(asset.venue)
        return store.enqueue(scope.key, p, live=args.live, now_ms=now)
    if args.order_action == "status":
        return {**store.get(args.id), "attempts": store.attempts(args.id), "tranches": store.tranches(args.id)}
    if args.order_action in {"exit", "cancel"}:
        return store.request_exit(
            args.id, now, cancel_only=args.order_action == "cancel"
        )
    row = store.get(args.id)
    if args.order_action == "amend":
        if row["state"] != "QUEUED" or store.attempts(row["id"]):
            raise ValueError("Only an unsent queued plan can be amended")
        p = validate_plan(json.loads(Path(args.input).read_text()), now)
        if (
            p["intent_id"] != row["plan"]["intent_id"]
            or p["instrument"] != row["plan"]["instrument"]
            or p.get("grant_id")
            or p.get("signal_id")
        ):
            raise ValueError(
                "Amendment must preserve intent/instrument and cannot change authority"
            )
        if row["plan"].get("signal_id"):
            raise ValueError(
                "Signal plans are immutable; cancel and produce a new signal"
            )
        row["plan"] = p
        store.save(row, now)
        return row
    if row["state"] != "INTERVENTION":
        raise ValueError("Only an intervention state can be recovered")
    row.update(
        state="ADOPTING" if row.get("adoption") and not row.get("adopted_ms") else "ENTERING",
        reason="Explicit recovery requested; budgets and ownership unchanged",
    )
    store.save(row, now)
    return row


def cmd_supervisor(args):
    from kis_hl.managed_gateways import ManagedHyperliquidGateway, ManagedKisGateway

    scope, client = scope_client(args.venue)
    store = ExecutionStore(args.db)

    def positions():
        # Execution uncertainty is separate from protection of observed exposure.
        return [{**row, "pending_adds": [
            {**{key: tranche.get(key) for key in ("id", "status", "filled", "attempt_id", "reason")},
             "signal_id": tranche["plan"]["signal_id"]}
            for tranche in store.tranches(row["id"]) if tranche["status"].lower() not in TERMINAL
        ]} for row in store.list(scope.key)]

    if args.action == "status":
        return {
            "positions": positions(),
            "entries_enabled": store.entries_enabled(scope.key),
        }
    if args.action in {"pause-entries", "resume-entries"}:
        store.set_entries(scope.key, args.action == "resume-entries")
        return {"entries_enabled": store.entries_enabled(scope.key)}
    if not 0 < args.poll_seconds <= 60:
        raise ValueError("Supervisor polling must be between zero and 60 seconds")
    gateway = (
        ManagedKisGateway(client)
        if args.venue == "kis"
        else ManagedHyperliquidGateway(
            client,
            HyperliquidTradingClient(client.config, verification_db_path=args.db),
        )
    )
    worker = Supervisor(store, gateway, live=args.live)
    with account_lock(gateway.network, gateway.account):
        while True:
            now = int(time.time() * 1000)
            store.heartbeat(scope.key, now, args.live)
            for row in store.list(scope.key):
                if (row["mode"] == "live") == args.live:
                    worker.step(row["id"], int(time.time() * 1000))
            if args.once:
                return {"positions": positions()}
            time.sleep(args.poll_seconds)


def cmd_strategy(args):
    from kis_hl.strategy_signals import Signals

    signals = Signals(ExecutionStore(args.db))
    action = args.strategy_action
    if action == "list":
        return signals.list("strategies")
    if action == "grants":
        return signals.list("grants")
    if action == "revoke":
        return signals.revoke(args.id)
    raw = json.loads(Path(args.input).read_text())
    if action == "register":
        return signals.register(raw)
    scope, _ = scope_client(args.venue)
    return signals.grant(
        {**raw, "scope": scope.key, "live": args.live}, now_ms=int(time.time() * 1000)
    )


def cmd_strategy_tool(args):
    from kis_hl.strategy_tools import evaluate_setup, indicator_facts, initial_stop, size_position, ingest_decision
    from kis_hl.strategy_signals import Signals

    raw = json.loads(Path(args.input).read_text())
    replay_ms = getattr(args, "as_of_ms", None)
    now = int(time.time() * 1000) if replay_ms is None else replay_ms
    if args.strategy_action == "evaluate":
        return evaluate_setup(raw, now_ms=now)
    if args.strategy_action == "indicators":
        return indicator_facts(raw, now_ms=now)
    if args.strategy_action == "size":
        return size_position(raw, now_ms=now)
    if args.strategy_action == "stop":
        return initial_stop(raw)
    return ingest_decision(Signals(ExecutionStore(args.db)), raw, now_ms=now)


def cmd_signal(args):
    from kis_hl.strategy_signals import Signals

    signals = Signals(ExecutionStore(args.db))
    if args.signal_action == "list":
        return signals.list()
    raw = json.loads(Path(args.input).read_text())
    now = int(time.time() * 1000)
    if args.signal_action == "ingest":
        return signals.ingest(raw, now_ms=now)
    scope, _ = scope_client(instrument(raw["instrument"]).venue)
    return signals.execute(
        args.id,
        scope.key,
        raw,
        live=args.live,
        manual=args.manual,
        grant_id=args.grant,
        now_ms=now,
    )


def cmd_verify_instrument(args):
    asset = instrument(args.instrument)
    scope, client = scope_client(asset.venue)
    if asset.venue == "kis" and asset.market == "overseas":
        r = client.overseas_instrument_info(
            symbol=asset.symbol, exchange=asset.order_exchange
        )
        if r.status >= 400 or r.body.get("rt_cd") != "0":
            raise ValueError("Instrument metadata inquiry failed")
        data = r.body["output"]
        if (
            data["ovrs_excg_cd"] != asset.order_exchange
            or data["tr_crcy_cd"] != asset.currency
        ):
            raise ValueError("KIS instrument metadata does not match catalog")
        result = {
            "instrument": asset.id,
            "account_scope": scope.key,
            "metadata": redact(data),
            "native_protection": "unverified",
            "live_order_acceptance": "not_tested",
        }
    elif asset.venue == "hyperliquid":
        from kis_hl.assets import resolve_hyperliquid_symbol

        a = resolve_hyperliquid_symbol(asset.symbol)
        data = client.meta_and_asset_ctxs(dex=a.dex)
        result = {
            "instrument": asset.id,
            "account_scope": scope.key,
            "metadata": [x for x in data[0]["universe"] if x["name"] == a.coin],
            "eligibility_note": "Use xyz-assets verify to update the existing live eligibility table",
        }
    else:
        r = client.order_book(market="domestic", symbol=asset.symbol)
        if r.status >= 400 or r.body.get("rt_cd") != "0":
            raise ValueError("Instrument quote route inquiry failed")
        result = {
            "instrument": asset.id,
            "account_scope": scope.key,
            "quote_route": "observed",
            "native_protection": "unverified",
        }
    from kis_hl.capabilities import CapabilityEvidence

    now = int(time.time() * 1000)
    CapabilityEvidence(args.db).record(
        scope.key,
        asset.id,
        "instrument_identity",
        "verified",
        now_ms=now,
        expires_ms=now + 86400000,
        evidence="Read-only venue metadata or quote route",
        details=result,
    )
    return result


def cmd_capability(args):
    from kis_hl.capabilities import CapabilityEvidence

    asset = instrument(args.instrument)
    scope = (
        Scope(asset.venue, args.environment, args.account)
        if args.account and args.environment
        else scope_client(asset.venue, args.account)[0]
    )
    return CapabilityEvidence(args.db).inspect(
        scope.key, asset.id, now_ms=int(time.time() * 1000)
    )
