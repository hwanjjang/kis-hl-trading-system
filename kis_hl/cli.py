from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.config import (
    load_env_file,
    load_hyperliquid_config,
    load_kis_config,
    load_runtime_config,
)
from kis_hl.hyperliquid.client import (
    HyperliquidInfoClient,
    HyperliquidTradingClient,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.kis.client import KisClient
from kis_hl.logging_utils import configure_logging, get_logger
from kis_hl.storage import store_market_payload, store_order_submission

logger = get_logger(__name__)


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

    trade = sub.add_parser("trade", help="Prepare or submit a Hyperliquid order")
    trade.add_argument("--symbol", required=True)
    trade.add_argument("--dex")
    trade.add_argument("--side", choices=["buy", "sell"], required=True)
    trade.add_argument("--order-type", choices=["limit", "market"], required=True)
    trade.add_argument("--size", required=True)
    trade.add_argument("--price")
    trade.add_argument("--reduce-only", action="store_true")
    trade.add_argument("--tif", default="Gtc")
    trade.add_argument("--slippage", default="0.05")
    trade.add_argument("--live", action="store_true", help="Send the order to Hyperliquid")
    trade.add_argument("--no-store", action="store_true")
    trade.set_defaults(handler=cmd_trade)

    resolve = sub.add_parser("resolve-symbol", help="Show Hyperliquid symbol resolution")
    resolve.add_argument("--symbol", required=True)
    resolve.add_argument("--dex")
    resolve.set_defaults(handler=cmd_resolve_symbol)
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


def cmd_trade(args: argparse.Namespace) -> dict[str, Any]:
    client = HyperliquidTradingClient(load_hyperliquid_config())
    submission = client.place_order(
        symbol=args.symbol,
        dex=args.dex,
        side=args.side,
        order_type=args.order_type,
        size=Decimal(args.size),
        price=Decimal(args.price) if args.price else None,
        reduce_only=args.reduce_only,
        tif=args.tif,
        slippage=Decimal(args.slippage),
        dry_run=not args.live,
    )
    result = submission_to_dict(submission)
    if not args.no_store:
        result["stored_id"] = store_order_submission(
            args.db,
            venue="hyperliquid",
            symbol=args.symbol,
            resolved_symbol=submission.resolved.coin,
            side=args.side,
            order_type=args.order_type,
            size=args.size,
            price=args.price,
            dry_run=submission.dry_run,
            status=submission.status,
            response=result,
            submitted_at_ms=int(time.time() * 1000),
        )
    return result


def cmd_resolve_symbol(args: argparse.Namespace) -> dict[str, Any]:
    return asdict(resolve_hyperliquid_symbol(args.symbol, dex=args.dex))


def _response_dict(status: int, body: Any) -> dict[str, Any]:
    return {"status": status, "body": body}


def _raise_on_kis_failure(status: int, body: Any) -> None:
    if status >= 400:
        raise RuntimeError(f"KIS request failed: HTTP {status}")
    if isinstance(body, dict):
        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            msg_cd = body.get("msg_cd", "unknown")
            msg = body.get("msg1", "")
            raise RuntimeError(f"KIS request failed: {msg_cd} {msg}".strip())


if __name__ == "__main__":
    raise SystemExit(main())
