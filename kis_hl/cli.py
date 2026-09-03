from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.btc_strategy import (
    DEFAULT_BTC_ENTRY_NOTIONAL_USDC,
    DEFAULT_BTC_STOP_ATR_MULTIPLE,
    fetch_btc_perp_atr_10d,
    run_btc_spot_breakout_monitor,
)
from kis_hl.config import (
    load_env_file,
    load_hyperliquid_config,
    load_kis_config,
    load_runtime_config,
)
from kis_hl.daily_collector import collect_trade_xyz_daily_bars
from kis_hl.hyperliquid.client import (
    HyperliquidInfoClient,
    HyperliquidTradingClient,
    extract_hyperliquid_order_id,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.kis.client import KisClient
from kis_hl.kis_collector import (
    collect_trade_xyz_kis_quotes,
    fetch_mapped_kis_response,
    raise_on_kis_failure,
)
from kis_hl.logging_utils import configure_logging, get_logger
from kis_hl.reference_collector import (
    collect_trade_xyz_reference_quotes,
    fetch_mapped_reference_response,
)
from kis_hl.reference_mappings import REFERENCE_PROVIDER_YAHOO
from kis_hl.signals import (
    BTCUSDC_FUTURES_INTERVAL,
    BTCUSDC_FUTURES_SYMBOL,
    evaluate_btcusdc_futures_3h_breakout,
)
from kis_hl.storage import (
    get_trade_xyz_kis_mapping,
    get_trade_xyz_reference_mapping,
    list_trade_journal_entries,
    list_trade_xyz_kis_mappings,
    list_trade_xyz_reference_mappings,
    list_trade_xyz_assets,
    seed_trade_xyz_reference_mappings,
    seed_trade_xyz_kis_mappings,
    seed_trade_xyz_assets,
    store_market_payload,
    store_order_submission,
    store_protective_order,
    store_trade_journal_entry,
)
from kis_hl.trade_journal import (
    calculate_trade_journal_stats,
    create_trade_journal_record,
    trade_journal_report,
)
from kis_hl.trade_xyz_verifier import summarize_checks, verify_trade_xyz_assets
from kis_hl.xyz_market_collector import (
    collect_xyz_funding_rates,
    collect_xyz_spreads,
    collect_xyz_universe,
)
from kis_hl.yahoo_finance.client import YahooFinanceClient

logger = get_logger(__name__)

TRADE_XYZ_ASSET_CLASS_CHOICES = ["commodity", "equity_index", "etf", "fx", "stock"]


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    runtime = load_runtime_config()
    configure_logging(runtime.log_level)

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    try:
        result = args.handler(args)
    except Exception as exc:
        logger.error("cli_command_failed", extra={"command": args.command, "error": str(exc)})
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kis-hl")
    parser.add_argument("--db", default="data/kis_hl.sqlite", help="SQLite database path")
    sub = parser.add_subparsers(dest="command")

    kis_price = sub.add_parser("kis-price", help="Fetch one KIS quote")
    kis_price.add_argument("--market", choices=["domestic", "overseas"], required=True)
    kis_price.add_argument("--symbol", required=True)
    kis_price.add_argument("--exchange-code", default="NAS")
    kis_price.add_argument("--market-code", default="J")
    kis_price.add_argument("--store", action="store_true")
    kis_price.set_defaults(handler=cmd_kis_price)

    kis_daily = sub.add_parser("kis-daily", help="Fetch KIS overseas daily chart prices")
    kis_daily.add_argument("--symbol", required=True)
    kis_daily.add_argument("--from", dest="date_from", required=True)
    kis_daily.add_argument("--to", dest="date_to", required=True)
    kis_daily.add_argument("--period", default="D")
    kis_daily.add_argument("--market-code", default="N")
    kis_daily.add_argument("--store", action="store_true")
    kis_daily.set_defaults(handler=cmd_kis_daily)

    hl_mids = sub.add_parser("hl-mids", help="Fetch Hyperliquid all mids")
    hl_mids.add_argument("--dex")
    hl_mids.add_argument("--symbols", nargs="*")
    hl_mids.set_defaults(handler=cmd_hl_mids)

    hl_candles = sub.add_parser("hl-candles", help="Fetch Hyperliquid candle snapshot")
    hl_candles.add_argument("--symbol", required=True)
    hl_candles.add_argument("--interval", default="15m")
    hl_candles.add_argument("--start-ms", type=int, required=True)
    hl_candles.add_argument("--end-ms", type=int, required=True)
    hl_candles.add_argument("--dex")
    hl_candles.set_defaults(handler=cmd_hl_candles)

    btc_breakout = sub.add_parser(
        "btc-3h-breakout",
        help="Evaluate BTCUSDC futures 3H previous-high close breakout",
    )
    btc_breakout.add_argument("--symbol", default=BTCUSDC_FUTURES_SYMBOL)
    btc_breakout.add_argument("--start-ms", type=int, required=True)
    btc_breakout.add_argument("--end-ms", type=int, required=True)
    btc_breakout.add_argument("--lookback-candles", type=int, default=1)
    btc_breakout.set_defaults(handler=cmd_btc_3h_breakout)

    btc_monitor = sub.add_parser(
        "btc-3h-monitor",
        help="Monitor BTCUSDC spot websocket prices and enter BTC perps on 3H close breakout",
    )
    btc_monitor.add_argument("--atr-10d", help="ATR(10D) override. If omitted, fetch 1d candles.")
    btc_monitor.add_argument("--atr-lookback-days", type=int, default=20)
    btc_monitor.add_argument(
        "--entry-notional-usdc",
        default=str(DEFAULT_BTC_ENTRY_NOTIONAL_USDC),
        help="Entry notional in USDC",
    )
    btc_monitor.add_argument(
        "--stop-atr-multiple",
        default=str(DEFAULT_BTC_STOP_ATR_MULTIPLE),
        help="Stop distance multiplier for ATR(10D)",
    )
    btc_monitor.add_argument("--lookback-candles", type=int, default=1)
    btc_monitor.add_argument("--slippage", default="0.05")
    btc_monitor.add_argument("--verification-max-age-hours", type=int, default=24)
    btc_monitor.add_argument("--live", action="store_true", help="Send entry and stop orders")
    btc_monitor.add_argument("--no-store", action="store_true")
    btc_monitor.add_argument("--max-messages", type=int)
    btc_monitor.add_argument("--max-reconnects", type=int)
    btc_monitor.set_defaults(handler=cmd_btc_3h_monitor)

    hl_account = sub.add_parser("hl-account", help="Fetch Hyperliquid wallet asset info")
    hl_account.add_argument("--user", help="Wallet address. Defaults to configured account address.")
    hl_account.add_argument(
        "--dex",
        action="append",
        default=[],
        help="Optional perp dex name to query, for example xyz. Can be repeated.",
    )
    hl_account.add_argument("--no-spot", action="store_true", help="Skip spot clearinghouse state")
    hl_account.add_argument(
        "--all-dexs",
        action="store_true",
        help="Try Hyperliquid ALL_DEXES aggregation. This may be unavailable on the public endpoint.",
    )
    hl_account.add_argument(
        "--no-all-dexs",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    hl_account.set_defaults(handler=cmd_hl_account)

    trade = sub.add_parser("trade", help="Prepare or submit a Hyperliquid order")
    trade.add_argument("--symbol", required=True)
    trade.add_argument("--dex")
    trade.add_argument("--side", choices=["buy", "sell"], required=True)
    trade.add_argument("--order-type", choices=["limit", "market", "stop-market"], required=True)
    trade.add_argument("--size", required=True)
    trade.add_argument("--price")
    trade.add_argument("--trigger-price")
    trade.add_argument("--tpsl", choices=["tp", "sl"], default="sl")
    trade.add_argument("--reduce-only", action="store_true")
    trade.add_argument("--tif", default="Gtc")
    trade.add_argument("--slippage", default="0.05")
    trade.add_argument("--verification-max-age-hours", type=int, default=24)
    trade.add_argument(
        "--allow-outside-session",
        action="store_true",
        help="Allow live non-reduce-only orders outside the mapped underlying market session",
    )
    trade.add_argument("--live", action="store_true", help="Send the order to Hyperliquid")
    trade.add_argument("--no-store", action="store_true")
    trade.set_defaults(handler=cmd_trade)

    journal = sub.add_parser("journal", help="Record and summarize completed trades")
    journal_sub = journal.add_subparsers(dest="journal_command")

    journal_add = journal_sub.add_parser("add", help="Record a completed trade journal entry")
    journal_add.add_argument("--venue", default="hyperliquid")
    journal_add.add_argument("--symbol", required=True)
    journal_add.add_argument("--strategy", default="manual")
    journal_add.add_argument("--side", choices=["long", "short", "buy", "sell"], required=True)
    journal_add.add_argument("--opened-at-ms", type=int, required=True)
    journal_add.add_argument("--closed-at-ms", type=int, required=True)
    journal_add.add_argument("--entry-price", required=True)
    journal_add.add_argument("--exit-price", required=True)
    journal_add.add_argument("--quantity", required=True)
    journal_add.add_argument("--fees", default="0")
    journal_add.add_argument("--realized-pnl")
    journal_add.add_argument(
        "--adjusted-outcome",
        choices=["success", "failure", "breakeven"],
        help="Legacy classification metadata; does not change required statistics",
    )
    journal_add.add_argument("--notes", default="")
    journal_add.set_defaults(handler=cmd_journal_add)

    journal_stats = journal_sub.add_parser("stats", help="Summarize completed trade journal entries")
    journal_stats.add_argument("--symbol")
    journal_stats.add_argument("--strategy")
    journal_stats.set_defaults(handler=cmd_journal_stats)

    resolve = sub.add_parser("resolve-symbol", help="Show Hyperliquid symbol resolution")
    resolve.add_argument("--symbol", required=True)
    resolve.add_argument("--dex")
    resolve.set_defaults(handler=cmd_resolve_symbol)

    xyz_assets = sub.add_parser("xyz-assets", help="Manage the local trade.xyz asset map")
    xyz_sub = xyz_assets.add_subparsers(dest="xyz_command")

    xyz_seed = xyz_sub.add_parser("seed", help="Create or refresh the trade.xyz asset map")
    xyz_seed.set_defaults(handler=cmd_xyz_assets_seed)

    xyz_list = xyz_sub.add_parser("list", help="List mapped trade.xyz assets")
    xyz_list.add_argument("--tradable-only", action="store_true")
    xyz_list.add_argument("--asset-class", choices=TRADE_XYZ_ASSET_CLASS_CHOICES)
    xyz_list.set_defaults(handler=cmd_xyz_assets_list)

    xyz_verify = xyz_sub.add_parser("verify", help="Verify mapped assets against Hyperliquid allMids")
    xyz_verify.add_argument("--all", action="store_true", help="Verify excluded assets too")
    xyz_verify.add_argument("--asset-class", choices=TRADE_XYZ_ASSET_CLASS_CHOICES)
    xyz_verify.set_defaults(handler=cmd_xyz_assets_verify)

    xyz_universe_collect = xyz_sub.add_parser(
        "universe-collect",
        help="Snapshot Hyperliquid xyz universe and detect newly listed markets",
    )
    xyz_universe_collect.add_argument("--no-store", action="store_true")
    xyz_universe_collect.set_defaults(handler=cmd_xyz_assets_universe_collect)

    xyz_funding_collect = xyz_sub.add_parser(
        "funding-collect",
        help="Collect Hyperliquid xyz funding history",
    )
    xyz_funding_collect.add_argument("--symbols", nargs="*", help="Optional xyz symbols to collect")
    xyz_funding_collect.add_argument("--lookback-hours", type=int, default=24)
    xyz_funding_collect.add_argument("--end-ms", type=int)
    xyz_funding_collect.add_argument("--no-store", action="store_true")
    xyz_funding_collect.add_argument("--delay-ms", type=int, default=0)
    xyz_funding_collect.add_argument("--fail-fast", action="store_true")
    xyz_funding_collect.set_defaults(handler=cmd_xyz_assets_funding_collect)

    xyz_spread_collect = xyz_sub.add_parser(
        "spread-collect",
        help="Collect Hyperliquid xyz top-of-book spread snapshots",
    )
    xyz_spread_collect.add_argument("--symbols", nargs="*", help="Optional xyz symbols to collect")
    xyz_spread_collect.add_argument("--no-store", action="store_true")
    xyz_spread_collect.add_argument("--delay-ms", type=int, default=0)
    xyz_spread_collect.add_argument("--fail-fast", action="store_true")
    xyz_spread_collect.set_defaults(handler=cmd_xyz_assets_spread_collect)

    xyz_seed_kis = xyz_sub.add_parser(
        "seed-kis",
        help="Create or refresh the trade.xyz to KIS market-data map",
    )
    xyz_seed_kis.set_defaults(handler=cmd_xyz_assets_seed_kis)

    xyz_kis_list = xyz_sub.add_parser("kis-list", help="List trade.xyz KIS quote mappings")
    xyz_kis_list.add_argument("--status", choices=["active", "excluded", "unsupported"])
    xyz_kis_list.add_argument(
        "--market",
        choices=["domestic", "overseas", "domestic_index", "overseas_index_time", "unsupported"],
    )
    xyz_kis_list.set_defaults(handler=cmd_xyz_assets_kis_list)

    xyz_kis_fetch = xyz_sub.add_parser("kis-fetch", help="Fetch a KIS quote by trade.xyz symbol")
    xyz_kis_fetch.add_argument("--symbol", required=True)
    xyz_kis_fetch.add_argument("--store", action="store_true")
    xyz_kis_fetch.set_defaults(handler=cmd_xyz_assets_kis_fetch)

    xyz_kis_collect = xyz_sub.add_parser(
        "kis-collect",
        help="Fetch KIS quotes for active trade.xyz mappings",
    )
    xyz_kis_collect.add_argument("--symbols", nargs="*", help="Optional trade.xyz symbols to collect")
    xyz_kis_collect.add_argument("--no-store", action="store_true")
    xyz_kis_collect.add_argument("--delay-ms", type=int, default=0)
    xyz_kis_collect.add_argument("--fail-fast", action="store_true")
    xyz_kis_collect.set_defaults(handler=cmd_xyz_assets_kis_collect)

    xyz_seed_ref = xyz_sub.add_parser(
        "seed-ref",
        help="Create or refresh secondary trade.xyz reference-data mappings",
    )
    xyz_seed_ref.set_defaults(handler=cmd_xyz_assets_seed_ref)

    xyz_ref_list = xyz_sub.add_parser("ref-list", help="List secondary reference-data mappings")
    xyz_ref_list.add_argument("--provider", default=REFERENCE_PROVIDER_YAHOO)
    xyz_ref_list.add_argument("--status", choices=["active", "excluded"])
    xyz_ref_list.add_argument("--asset-class", choices=TRADE_XYZ_ASSET_CLASS_CHOICES)
    xyz_ref_list.set_defaults(handler=cmd_xyz_assets_ref_list)

    xyz_ref_fetch = xyz_sub.add_parser(
        "ref-fetch",
        help="Fetch a secondary reference quote by trade.xyz symbol",
    )
    xyz_ref_fetch.add_argument("--symbol", required=True)
    xyz_ref_fetch.add_argument("--range", dest="range_name", default="1d")
    xyz_ref_fetch.add_argument("--interval", default="1m")
    xyz_ref_fetch.add_argument("--store", action="store_true")
    xyz_ref_fetch.set_defaults(handler=cmd_xyz_assets_ref_fetch)

    xyz_ref_collect = xyz_sub.add_parser(
        "ref-collect",
        help="Fetch secondary reference quotes for active trade.xyz mappings",
    )
    xyz_ref_collect.add_argument("--symbols", nargs="*", help="Optional trade.xyz symbols to collect")
    xyz_ref_collect.add_argument("--provider", default=REFERENCE_PROVIDER_YAHOO)
    xyz_ref_collect.add_argument("--asset-class", choices=TRADE_XYZ_ASSET_CLASS_CHOICES)
    xyz_ref_collect.add_argument("--range", dest="range_name", default="1d")
    xyz_ref_collect.add_argument("--interval", default="1m")
    xyz_ref_collect.add_argument("--no-store", action="store_true")
    xyz_ref_collect.add_argument("--delay-ms", type=int, default=0)
    xyz_ref_collect.add_argument("--fail-fast", action="store_true")
    xyz_ref_collect.set_defaults(handler=cmd_xyz_assets_ref_collect)

    xyz_daily_collect = xyz_sub.add_parser(
        "daily-collect",
        help="Fetch Yahoo Finance daily bars for tradable trade.xyz assets",
    )
    xyz_daily_collect.add_argument("--symbols", nargs="*", help="Optional trade.xyz symbols to collect")
    xyz_daily_collect.add_argument("--asset-class", choices=TRADE_XYZ_ASSET_CLASS_CHOICES)
    xyz_daily_collect.add_argument("--days", type=int, default=365)
    xyz_daily_collect.add_argument("--to", dest="date_to", help="Exclusive end date in YYYY-MM-DD")
    xyz_daily_collect.add_argument("--no-store", action="store_true")
    xyz_daily_collect.add_argument("--delay-ms", type=int, default=300)
    xyz_daily_collect.add_argument("--fail-fast", action="store_true")
    xyz_daily_collect.set_defaults(handler=cmd_xyz_assets_daily_collect)
    return parser


def cmd_kis_price(args: argparse.Namespace) -> dict[str, Any]:
    client = KisClient(load_kis_config())
    if args.market == "domestic":
        response = client.inquire_domestic_price(symbol=args.symbol, market_code=args.market_code)
        exchange_code = None
    else:
        response = client.inquire_overseas_price(
            exchange_code=args.exchange_code,
            symbol=args.symbol,
        )
        exchange_code = args.exchange_code
    _raise_on_kis_failure(response.status, response.body)
    result = _response_dict(response.status, response.body)
    if args.store:
        result["stored_id"] = store_market_payload(
            args.db,
            source="kis",
            market=args.market,
            symbol=args.symbol,
            exchange_code=exchange_code,
            payload=response.body,
        )
    return result


def cmd_kis_daily(args: argparse.Namespace) -> dict[str, Any]:
    client = KisClient(load_kis_config())
    response = client.inquire_overseas_daily_chartprice(
        symbol=args.symbol,
        date_from=args.date_from,
        date_to=args.date_to,
        period=args.period,
        market_code=args.market_code,
    )
    _raise_on_kis_failure(response.status, response.body)
    result = _response_dict(response.status, response.body)
    if args.store:
        result["stored_id"] = store_market_payload(
            args.db,
            source="kis",
            market="overseas_daily",
            symbol=args.symbol,
            exchange_code=args.market_code,
            payload=response.body,
        )
    return result


def cmd_hl_mids(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    mids = client.all_mids(dex=args.dex)
    if not args.symbols:
        return {"mids": mids}
    resolved = [resolve_hyperliquid_symbol(symbol, dex=args.dex) for symbol in args.symbols]
    spot_meta = None
    output_mids: dict[str, str | None] = {}
    resolved_payload = []
    for asset in resolved:
        order_coin = asset.coin
        value = mids.get(asset.coin)
        if value is None and asset.kind == "spot":
            if spot_meta is None:
                spot_meta = client.spot_meta()
            order_coin = resolve_spot_order_coin(spot_meta, asset.coin)
            value = mids.get(order_coin)
        output_mids[asset.coin] = value
        item = asdict(asset)
        item["order_coin"] = order_coin
        resolved_payload.append(item)
    return {
        "mids": output_mids,
        "resolved": resolved_payload,
    }


def cmd_hl_candles(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    candles = client.candle_snapshot(
        args.symbol,
        interval=args.interval,
        start_time_ms=args.start_ms,
        end_time_ms=args.end_ms,
        dex=args.dex,
    )
    return {"candles": candles}


def cmd_btc_3h_breakout(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    candles = client.candle_snapshot(
        args.symbol,
        interval=BTCUSDC_FUTURES_INTERVAL,
        start_time_ms=args.start_ms,
        end_time_ms=args.end_ms,
    )
    signal = evaluate_btcusdc_futures_3h_breakout(
        candles,
        symbol=args.symbol,
        lookback_candles=args.lookback_candles,
    )
    return asdict(signal)


def cmd_btc_3h_monitor(args: argparse.Namespace) -> dict[str, Any]:
    config = load_hyperliquid_config()
    info_client = HyperliquidInfoClient(config)
    atr_10d = (
        Decimal(args.atr_10d)
        if args.atr_10d
        else fetch_btc_perp_atr_10d(info_client, lookback_days=args.atr_lookback_days)
    )
    trading_client = HyperliquidTradingClient(
        config,
        verification_db_path=args.db,
        verification_max_age_hours=args.verification_max_age_hours,
    )
    executions: list[dict[str, Any]] = []

    def on_execution(execution: dict[str, Any]) -> None:
        if not args.no_store:
            execution["stored_ids"] = _store_btc_monitor_execution(args.db, execution)
        executions.append(execution)

    status = run_btc_spot_breakout_monitor(
        config=config,
        trading_client=trading_client,
        atr_10d=atr_10d,
        entry_notional_usdc=Decimal(args.entry_notional_usdc),
        stop_atr_multiple=Decimal(args.stop_atr_multiple),
        lookback_candles=args.lookback_candles,
        dry_run=not args.live,
        slippage=Decimal(args.slippage),
        max_messages=args.max_messages,
        max_reconnects=args.max_reconnects,
        on_execution=on_execution,
    )
    return {
        "status": asdict(status),
        "atr_10d": atr_10d,
        "entry_notional_usdc": args.entry_notional_usdc,
        "stop_atr_multiple": args.stop_atr_multiple,
        "executions": executions,
    }


def cmd_hl_account(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    return client.account_asset_info(
        user=args.user,
        include_spot=not args.no_spot,
        include_all_dexs=args.all_dexs and not args.no_all_dexs,
        dexes=args.dex,
    )


def cmd_trade(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidTradingClient(
        load_hyperliquid_config(),
        verification_db_path=args.db,
        verification_max_age_hours=args.verification_max_age_hours,
    )
    submission = client.place_order(
        symbol=args.symbol,
        dex=args.dex,
        side=args.side,
        order_type=args.order_type,
        size=Decimal(args.size),
        price=Decimal(args.price) if args.price else None,
        trigger_price=Decimal(args.trigger_price) if args.trigger_price else None,
        tpsl=args.tpsl,
        reduce_only=args.reduce_only,
        tif=args.tif,
        slippage=Decimal(args.slippage),
        dry_run=not args.live,
        allow_outside_session=args.allow_outside_session,
    )
    result = submission_to_dict(submission)
    stored_price = args.price if args.price is not None else args.trigger_price
    if not args.no_store:
        stored_id = store_order_submission(
            args.db,
            venue="hyperliquid",
            symbol=args.symbol,
            resolved_symbol=submission.resolved.coin,
            side=args.side,
            order_type=args.order_type,
            size=args.size,
            price=stored_price,
            dry_run=submission.dry_run,
            status=submission.status,
            response=result,
            submitted_at_ms=int(time.time() * 1000),
        )
        result["stored_id"] = stored_id
        if args.order_type == "stop-market" and args.reduce_only:
            result["protective_order_id"] = store_protective_order(
                args.db,
                venue="hyperliquid",
                symbol=args.symbol,
                resolved_symbol=submission.resolved.coin,
                side=args.side,
                order_type=args.order_type,
                trigger_price=args.trigger_price,
                covered_size=args.size,
                order_id=extract_hyperliquid_order_id(submission.response),
                client_request_id=submission.request.get("client_request_id"),
                source_order_submission_id=stored_id,
                dry_run=submission.dry_run,
                active=(not submission.dry_run and submission.status == "submitted"),
                status=submission.status,
                response=result,
                submitted_at_ms=result["submitted_at_ms"],
            )
    return result


def cmd_journal_add(args: argparse.Namespace) -> dict[str, Any]:
    record = create_trade_journal_record(
        venue=args.venue,
        symbol=args.symbol,
        strategy=args.strategy,
        side=args.side,
        opened_at_ms=args.opened_at_ms,
        closed_at_ms=args.closed_at_ms,
        entry_price=Decimal(args.entry_price),
        exit_price=Decimal(args.exit_price),
        quantity=Decimal(args.quantity),
        fees=Decimal(args.fees),
        realized_pnl=Decimal(args.realized_pnl) if args.realized_pnl else None,
        adjusted_outcome=args.adjusted_outcome,
        notes=args.notes,
    )
    existing = list_trade_journal_entries(args.db)
    stats = calculate_trade_journal_stats([*existing, record])
    stored_id = store_trade_journal_entry(args.db, record=record, stats=stats)
    return {"stored_id": stored_id, **trade_journal_report(record, stats)}


def cmd_journal_stats(args: argparse.Namespace) -> dict[str, Any]:
    entries = list_trade_journal_entries(
        args.db,
        symbol=args.symbol,
        strategy=args.strategy,
    )
    stats = calculate_trade_journal_stats(entries)
    return {
        "filters": {"symbol": args.symbol, "strategy": args.strategy},
        "statistics": asdict(stats),
        "entries": entries,
    }


def _store_btc_monitor_execution(db_path: str, execution: dict[str, Any]) -> dict[str, int]:
    entry = execution["entry_order"]
    stop = execution["stop_loss_order"]
    entry_id = _store_order_submission_from_payload(db_path, entry)
    stop_id = _store_order_submission_from_payload(db_path, stop)
    stop_request = stop["request"]
    protective_id = store_protective_order(
        db_path,
        venue="hyperliquid",
        symbol=stop_request["symbol"],
        resolved_symbol=stop["resolved"]["coin"],
        side=stop_request["side"],
        order_type=stop_request["order_type"],
        trigger_price=stop_request["trigger_price"],
        covered_size=stop_request["size"],
        order_id=extract_hyperliquid_order_id(stop["response"]),
        client_request_id=stop_request.get("client_request_id"),
        source_order_submission_id=stop_id,
        dry_run=stop["dry_run"],
        active=(not stop["dry_run"] and stop["status"] == "submitted"),
        status=stop["status"],
        response=stop,
        submitted_at_ms=stop["submitted_at_ms"],
    )
    return {
        "entry_order_submission_id": entry_id,
        "stop_order_submission_id": stop_id,
        "protective_order_id": protective_id,
    }


def _store_order_submission_from_payload(db_path: str, order: dict[str, Any]) -> int:
    request = order["request"]
    return store_order_submission(
        db_path,
        venue="hyperliquid",
        symbol=request["symbol"],
        resolved_symbol=order["resolved"]["coin"],
        side=request["side"],
        order_type=request["order_type"],
        size=request["size"],
        price=request["price"],
        dry_run=order["dry_run"],
        status=order["status"],
        response=order,
        submitted_at_ms=order["submitted_at_ms"],
    )


def cmd_resolve_symbol(args: argparse.Namespace) -> dict[str, Any]:
    return asdict(resolve_hyperliquid_symbol(args.symbol, dex=args.dex))


def cmd_xyz_assets_seed(args: argparse.Namespace) -> dict[str, Any]:
    count = seed_trade_xyz_assets(args.db)
    return {"seeded": count, "db": args.db}


def cmd_xyz_assets_list(args: argparse.Namespace) -> dict[str, Any]:
    assets = list_trade_xyz_assets(
        args.db,
        tradable_only=args.tradable_only,
        asset_class=args.asset_class,
    )
    return {"count": len(assets), "assets": assets}


def cmd_xyz_assets_verify(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    mids = client.all_mids(dex="xyz")
    checks = verify_trade_xyz_assets(
        args.db,
        mids=mids,
        tradable_only=not args.all,
        asset_class=args.asset_class,
    )
    summary = summarize_checks(checks)
    return {"db": args.db, **summary, "checks": checks}


def cmd_xyz_assets_universe_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    return collect_xyz_universe(
        args.db,
        client=client,
        store=not args.no_store,
    )


def cmd_xyz_assets_funding_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    return collect_xyz_funding_rates(
        args.db,
        client=client,
        symbols=args.symbols,
        lookback_hours=args.lookback_hours,
        end_time_ms=args.end_ms,
        store=not args.no_store,
        delay_ms=args.delay_ms,
        fail_fast=args.fail_fast,
    )


def cmd_xyz_assets_spread_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidInfoClient(load_hyperliquid_config())
    return collect_xyz_spreads(
        args.db,
        client=client,
        symbols=args.symbols,
        store=not args.no_store,
        delay_ms=args.delay_ms,
        fail_fast=args.fail_fast,
    )


def cmd_xyz_assets_seed_kis(args: argparse.Namespace) -> dict[str, Any]:
    count = seed_trade_xyz_kis_mappings(args.db)
    return {"seeded": count, "db": args.db}


def cmd_xyz_assets_kis_list(args: argparse.Namespace) -> dict[str, Any]:
    mappings = list_trade_xyz_kis_mappings(
        args.db,
        status=args.status,
        kis_market=args.market,
    )
    return {"count": len(mappings), "mappings": mappings}


def cmd_xyz_assets_kis_fetch(args: argparse.Namespace) -> dict[str, Any]:
    mapping = get_trade_xyz_kis_mapping(args.db, args.symbol)
    if mapping is None:
        raise RuntimeError(f"No trade.xyz KIS mapping found for {args.symbol}")
    if mapping["status"] != "active":
        reason = mapping["reason"] or "mapping is not active"
        raise RuntimeError(
            f"KIS mapping for {mapping['trade_symbol']} is {mapping['status']}: {reason}"
        )

    client = KisClient(load_kis_config())
    logger.info(
        "trade_xyz_kis_fetch_started",
        extra={
            "trade_symbol": mapping["trade_symbol"],
            "kis_market": mapping["kis_market"],
            "kis_symbol": mapping["kis_symbol"],
        },
    )
    mapped = fetch_mapped_kis_response(client, mapping)
    response = mapped.response
    result = {"mapping": mapping, **_response_dict(response.status, response.body)}
    if args.store:
        result["stored_id"] = store_market_payload(
            args.db,
            source="kis",
            market=mapped.storage_market,
            symbol=mapping["trade_symbol"],
            exchange_code=mapped.exchange_code,
            payload=response.body,
        )
        logger.info(
            "trade_xyz_kis_fetch_stored",
            extra={"trade_symbol": mapping["trade_symbol"], "stored_id": result["stored_id"]},
        )
    return result


def cmd_xyz_assets_kis_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = KisClient(load_kis_config())
    summary = collect_trade_xyz_kis_quotes(
        args.db,
        client=client,
        symbols=args.symbols,
        store=not args.no_store,
        delay_ms=args.delay_ms,
        fail_fast=args.fail_fast,
    )
    return {"db": args.db, **summary}


def cmd_xyz_assets_seed_ref(args: argparse.Namespace) -> dict[str, Any]:
    count = seed_trade_xyz_reference_mappings(args.db)
    return {"seeded": count, "db": args.db}


def cmd_xyz_assets_ref_list(args: argparse.Namespace) -> dict[str, Any]:
    mappings = list_trade_xyz_reference_mappings(
        args.db,
        provider=args.provider,
        status=args.status,
        asset_class=args.asset_class,
    )
    return {"count": len(mappings), "mappings": mappings}


def cmd_xyz_assets_ref_fetch(args: argparse.Namespace) -> dict[str, Any]:
    mapping = get_trade_xyz_reference_mapping(args.db, args.symbol)
    if mapping is None:
        raise RuntimeError(f"No trade.xyz reference mapping found for {args.symbol}")
    if mapping["status"] != "active":
        reason = mapping["reason"] or "mapping is not active"
        raise RuntimeError(
            f"Reference mapping for {mapping['trade_symbol']} is {mapping['status']}: {reason}"
        )

    client = YahooFinanceClient()
    logger.info(
        "trade_xyz_reference_fetch_started",
        extra={
            "trade_symbol": mapping["trade_symbol"],
            "provider": mapping["provider"],
            "provider_symbol": mapping["provider_symbol"],
        },
    )
    mapped = fetch_mapped_reference_response(
        client,
        mapping,
        range_name=args.range_name,
        interval=args.interval,
    )
    response = mapped.response
    result = {"mapping": mapping, **_response_dict(response.status, response.body)}
    if args.store:
        result["stored_id"] = store_market_payload(
            args.db,
            source=mapping["provider"],
            market=mapped.storage_market,
            symbol=mapping["trade_symbol"],
            exchange_code=mapped.exchange_code,
            payload=response.body,
            observed_at_ms=response.observed_at_ms,
        )
        logger.info(
            "trade_xyz_reference_fetch_stored",
            extra={"trade_symbol": mapping["trade_symbol"], "stored_id": result["stored_id"]},
        )
    return result


def cmd_xyz_assets_ref_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = YahooFinanceClient()
    summary = collect_trade_xyz_reference_quotes(
        args.db,
        client=client,
        symbols=args.symbols,
        provider=args.provider,
        asset_class=args.asset_class,
        store=not args.no_store,
        delay_ms=args.delay_ms,
        fail_fast=args.fail_fast,
        range_name=args.range_name,
        interval=args.interval,
    )
    return {"db": args.db, **summary}


def cmd_xyz_assets_daily_collect(args: argparse.Namespace) -> dict[str, Any]:
    client = YahooFinanceClient()
    summary = collect_trade_xyz_daily_bars(
        args.db,
        client=client,
        symbols=args.symbols,
        asset_class=args.asset_class,
        days=args.days,
        date_to=date.fromisoformat(args.date_to) if args.date_to else None,
        store=not args.no_store,
        delay_ms=args.delay_ms,
        fail_fast=args.fail_fast,
    )
    return {"db": args.db, **summary}


def _response_dict(status: int, body: Any) -> dict[str, Any]:
    return {"status": status, "body": body}


def _raise_on_kis_failure(status: int, body: Any) -> None:
    raise_on_kis_failure(status, body)


if __name__ == "__main__":
    raise SystemExit(main())
