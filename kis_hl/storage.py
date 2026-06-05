from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from kis_hl.kis_mappings import KisMarketDataMapping, build_trade_xyz_kis_mappings
from kis_hl.reference_mappings import (
    ReferenceMarketDataMapping,
    build_trade_xyz_reference_mappings,
)
from kis_hl.trade_journal import TradeJournalRecord, TradeJournalStats
from kis_hl.trade_xyz_assets import TRADE_XYZ_ASSETS, TradeXyzAsset, is_asset_tradable
from kis_hl.trade_xyz_assets import normalize_trade_symbol


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_ticks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              market TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange_code TEXT,
              observed_at_ms INTEGER NOT NULL,
              last_price TEXT,
              payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_daily_bars (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              market TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange_code TEXT,
              bar_date TEXT NOT NULL,
              open_price TEXT,
              high_price TEXT,
              low_price TEXT,
              close_price TEXT,
              adj_close_price TEXT,
              volume TEXT,
              observed_at_ms INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              UNIQUE(source, market, symbol, bar_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_funding_rates (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              dex TEXT NOT NULL,
              symbol TEXT NOT NULL,
              funding_time_ms INTEGER NOT NULL,
              funding_rate TEXT NOT NULL,
              premium TEXT,
              observed_at_ms INTEGER NOT NULL,
              raw_json TEXT NOT NULL,
              UNIQUE(source, dex, symbol, funding_time_ms)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_spread_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              dex TEXT NOT NULL,
              symbol TEXT NOT NULL,
              observed_at_ms INTEGER NOT NULL,
              best_bid TEXT NOT NULL,
              best_ask TEXT NOT NULL,
              mid_price TEXT NOT NULL,
              spread_abs TEXT NOT NULL,
              spread_bps TEXT NOT NULL,
              bid_size TEXT,
              ask_size TEXT,
              raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_submissions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              venue TEXT NOT NULL,
              symbol TEXT NOT NULL,
              resolved_symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              order_type TEXT NOT NULL,
              size TEXT NOT NULL,
              price TEXT,
              dry_run INTEGER NOT NULL,
              submitted_at_ms INTEGER NOT NULL,
              status TEXT NOT NULL,
              response_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS protective_orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              venue TEXT NOT NULL,
              symbol TEXT NOT NULL,
              resolved_symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              order_type TEXT NOT NULL,
              trigger_price TEXT NOT NULL,
              covered_size TEXT NOT NULL,
              order_id TEXT,
              client_request_id TEXT,
              source_order_submission_id INTEGER,
              dry_run INTEGER NOT NULL,
              active INTEGER NOT NULL,
              status TEXT NOT NULL,
              submitted_at_ms INTEGER NOT NULL,
              response_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_journal_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              venue TEXT NOT NULL,
              symbol TEXT NOT NULL,
              strategy TEXT NOT NULL,
              side TEXT NOT NULL,
              opened_at_ms INTEGER NOT NULL,
              closed_at_ms INTEGER NOT NULL,
              entry_price TEXT NOT NULL,
              exit_price TEXT NOT NULL,
              quantity TEXT NOT NULL,
              realized_pnl TEXT NOT NULL,
              realized_pnl_pct TEXT NOT NULL,
              fees TEXT NOT NULL,
              holding_days TEXT NOT NULL,
              outcome TEXT NOT NULL,
              adjusted_outcome TEXT,
              notes TEXT NOT NULL,
              stats_json TEXT NOT NULL,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_assets (
              trade_symbol TEXT PRIMARY KEY,
              hyperliquid_coin TEXT NOT NULL UNIQUE,
              asset_class TEXT NOT NULL,
              underlying_name TEXT NOT NULL,
              underlying_symbol TEXT NOT NULL,
              underlying_exchange TEXT NOT NULL,
              listing_status TEXT NOT NULL,
              tradable INTEGER NOT NULL,
              listing_date TEXT,
              min_listing_age_weeks INTEGER NOT NULL DEFAULT 30,
              aliases_json TEXT NOT NULL,
              duplicate_group TEXT,
              preferred_symbol TEXT,
              exclusion_reason TEXT,
              source_url TEXT NOT NULL,
              notes TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        _ensure_column(conn, "trade_xyz_assets", "listing_date", "TEXT")
        _ensure_column(
            conn,
            "trade_xyz_assets",
            "min_listing_age_weeks",
            "INTEGER NOT NULL DEFAULT 30",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_asset_checks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              trade_symbol TEXT NOT NULL,
              hyperliquid_coin TEXT NOT NULL,
              dex TEXT NOT NULL,
              available INTEGER NOT NULL,
              last_mid TEXT,
              mid_source_key TEXT,
              checked_at_ms INTEGER NOT NULL,
              failure_reason TEXT,
              raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_kis_mappings (
              trade_symbol TEXT PRIMARY KEY,
              hyperliquid_coin TEXT NOT NULL,
              asset_class TEXT NOT NULL,
              kis_market TEXT NOT NULL,
              kis_symbol TEXT,
              kis_exchange_code TEXT,
              kis_market_code TEXT,
              status TEXT NOT NULL,
              reason TEXT,
              source TEXT NOT NULL,
              notes TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_reference_mappings (
              trade_symbol TEXT PRIMARY KEY,
              hyperliquid_coin TEXT NOT NULL,
              asset_class TEXT NOT NULL,
              provider TEXT NOT NULL,
              provider_symbol TEXT NOT NULL,
              provider_market TEXT NOT NULL,
              provider_instrument_type TEXT NOT NULL,
              status TEXT NOT NULL,
              reason TEXT,
              source TEXT NOT NULL,
              notes TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_universe_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              dex TEXT NOT NULL,
              observed_at_ms INTEGER NOT NULL,
              asset_count INTEGER NOT NULL,
              new_symbols_json TEXT NOT NULL,
              missing_symbols_json TEXT NOT NULL,
              raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_xyz_universe_assets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              snapshot_id INTEGER NOT NULL,
              source TEXT NOT NULL,
              dex TEXT NOT NULL,
              symbol TEXT NOT NULL,
              sz_decimals INTEGER,
              max_leverage INTEGER,
              margin_table_id INTEGER,
              only_isolated INTEGER,
              margin_mode TEXT,
              day_base_volume TEXT,
              day_notional_volume TEXT,
              open_interest TEXT,
              observed_at_ms INTEGER NOT NULL,
              asset_context_json TEXT NOT NULL,
              raw_json TEXT NOT NULL,
              UNIQUE(snapshot_id, symbol)
            )
            """
        )
        _ensure_column(conn, "trade_xyz_universe_assets", "day_base_volume", "TEXT")
        _ensure_column(conn, "trade_xyz_universe_assets", "day_notional_volume", "TEXT")
        _ensure_column(conn, "trade_xyz_universe_assets", "open_interest", "TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_xyz_kis_mappings_status
            ON trade_xyz_kis_mappings (status, kis_market)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_xyz_reference_mappings_status
            ON trade_xyz_reference_mappings (provider, status, asset_class)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_xyz_asset_checks_coin_time
            ON trade_xyz_asset_checks (hyperliquid_coin, checked_at_ms DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_daily_bars_symbol_date
            ON market_daily_bars (source, market, symbol, bar_date DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_funding_rates_symbol_time
            ON market_funding_rates (source, dex, symbol, funding_time_ms DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_spread_snapshots_symbol_time
            ON market_spread_snapshots (source, dex, symbol, observed_at_ms DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_xyz_universe_snapshots_dex_time
            ON trade_xyz_universe_snapshots (source, dex, observed_at_ms DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_xyz_universe_assets_snapshot_symbol
            ON trade_xyz_universe_assets (snapshot_id, symbol)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_protective_orders_symbol_active_time
            ON protective_orders (venue, resolved_symbol, active, submitted_at_ms DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_journal_entries_symbol_closed
            ON trade_journal_entries (symbol, closed_at_ms DESC)
            """
        )
        conn.commit()


def store_market_payload(
    db_path: str | Path,
    *,
    source: str,
    market: str,
    symbol: str,
    exchange_code: str | None,
    payload: Any,
    observed_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    observed_at = observed_at_ms or int(time.time() * 1000)
    payload_json = json.dumps(payload, default=str, sort_keys=True)
    last_price = _extract_last_price(payload)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO market_ticks (
              source, market, symbol, exchange_code, observed_at_ms, last_price, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (source, market, symbol, exchange_code, observed_at, last_price, payload_json),
        )
        conn.commit()
        return int(cur.lastrowid)


def store_market_daily_bars(
    db_path: str | Path,
    *,
    source: str,
    market: str,
    symbol: str,
    exchange_code: str | None,
    bars: list[dict[str, Any]],
    observed_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    observed_at = observed_at_ms or int(time.time() * 1000)
    rows = [
        _daily_bar_row(
            source=source,
            market=market,
            symbol=symbol,
            exchange_code=exchange_code,
            bar=bar,
            observed_at_ms=observed_at,
        )
        for bar in bars
    ]
    if not rows:
        return 0
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO market_daily_bars (
              source, market, symbol, exchange_code, bar_date, open_price, high_price,
              low_price, close_price, adj_close_price, volume, observed_at_ms, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, market, symbol, bar_date) DO UPDATE SET
              exchange_code = excluded.exchange_code,
              open_price = excluded.open_price,
              high_price = excluded.high_price,
              low_price = excluded.low_price,
              close_price = excluded.close_price,
              adj_close_price = excluded.adj_close_price,
              volume = excluded.volume,
              observed_at_ms = excluded.observed_at_ms,
              payload_json = excluded.payload_json
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def upsert_market_funding_rates(
    db_path: str | Path,
    *,
    dex: str,
    symbol: str,
    rows: list[dict[str, Any]],
    observed_at_ms: int | None = None,
    source: str = "hyperliquid",
) -> int:
    init_db(db_path)
    observed_at = observed_at_ms or int(time.time() * 1000)
    values = [
        _funding_rate_row(
            source=source,
            dex=dex,
            symbol=symbol,
            row=row,
            observed_at_ms=observed_at,
        )
        for row in rows
    ]
    if not values:
        return 0
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO market_funding_rates (
              source, dex, symbol, funding_time_ms, funding_rate, premium,
              observed_at_ms, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, dex, symbol, funding_time_ms) DO UPDATE SET
              funding_rate = excluded.funding_rate,
              premium = excluded.premium,
              observed_at_ms = excluded.observed_at_ms,
              raw_json = excluded.raw_json
            """,
            values,
        )
        conn.commit()
    return len(values)


def list_market_funding_rates(
    db_path: str | Path,
    *,
    symbol: str | None = None,
    dex: str | None = None,
    since_ms: int | None = None,
    limit: int | None = None,
    source: str = "hyperliquid",
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses = ["source = ?"]
    params: list[Any] = [source]
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if dex:
        clauses.append("dex = ?")
        params.append(dex)
    if since_ms is not None:
        clauses.append("funding_time_ms >= ?")
        params.append(since_ms)
    limit_sql = " LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(limit)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, source, dex, symbol, funding_time_ms, funding_rate, premium,
                   observed_at_ms, raw_json
            FROM market_funding_rates
            WHERE {" AND ".join(clauses)}
            ORDER BY funding_time_ms DESC, id DESC
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [_funding_rate_dict(row) for row in rows]


def store_market_spread_snapshot(
    db_path: str | Path,
    *,
    dex: str,
    symbol: str,
    observed_at_ms: int,
    best_bid: str,
    best_ask: str,
    mid_price: str,
    spread_abs: str,
    spread_bps: str,
    bid_size: str | None,
    ask_size: str | None,
    raw: Any,
    source: str = "hyperliquid",
) -> int:
    init_db(db_path)
    raw_json = json.dumps(raw, default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO market_spread_snapshots (
              source, dex, symbol, observed_at_ms, best_bid, best_ask, mid_price,
              spread_abs, spread_bps, bid_size, ask_size, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                dex,
                symbol,
                observed_at_ms,
                best_bid,
                best_ask,
                mid_price,
                spread_abs,
                spread_bps,
                bid_size,
                ask_size,
                raw_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_market_spread_snapshots(
    db_path: str | Path,
    *,
    symbol: str | None = None,
    dex: str | None = None,
    since_ms: int | None = None,
    limit: int | None = None,
    source: str = "hyperliquid",
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses = ["source = ?"]
    params: list[Any] = [source]
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if dex:
        clauses.append("dex = ?")
        params.append(dex)
    if since_ms is not None:
        clauses.append("observed_at_ms >= ?")
        params.append(since_ms)
    limit_sql = " LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(limit)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, source, dex, symbol, observed_at_ms, best_bid, best_ask,
                   mid_price, spread_abs, spread_bps, bid_size, ask_size, raw_json
            FROM market_spread_snapshots
            WHERE {" AND ".join(clauses)}
            ORDER BY observed_at_ms DESC, id DESC
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [_spread_snapshot_dict(row) for row in rows]


def store_order_submission(
    db_path: str | Path,
    *,
    venue: str,
    symbol: str,
    resolved_symbol: str,
    side: str,
    order_type: str,
    size: str,
    price: str | None,
    dry_run: bool,
    status: str,
    response: Any,
    submitted_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    submitted_at = submitted_at_ms or int(time.time() * 1000)
    response_json = json.dumps(response, default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO order_submissions (
              venue, symbol, resolved_symbol, side, order_type, size, price, dry_run,
              submitted_at_ms, status, response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venue,
                symbol,
                resolved_symbol,
                side,
                order_type,
                size,
                price,
                1 if dry_run else 0,
                submitted_at,
                status,
                response_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def store_protective_order(
    db_path: str | Path,
    *,
    venue: str,
    symbol: str,
    resolved_symbol: str,
    side: str,
    order_type: str,
    trigger_price: str,
    covered_size: str,
    order_id: str | None,
    client_request_id: str | None,
    source_order_submission_id: int | None,
    dry_run: bool,
    active: bool,
    status: str,
    response: Any,
    submitted_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    submitted_at = submitted_at_ms or int(time.time() * 1000)
    response_json = json.dumps(response, default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO protective_orders (
              venue, symbol, resolved_symbol, side, order_type, trigger_price,
              covered_size, order_id, client_request_id, source_order_submission_id,
              dry_run, active, status, submitted_at_ms, response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venue,
                symbol,
                resolved_symbol,
                side,
                order_type,
                trigger_price,
                covered_size,
                order_id,
                client_request_id,
                source_order_submission_id,
                1 if dry_run else 0,
                1 if active else 0,
                status,
                submitted_at,
                response_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_protective_orders(
    db_path: str | Path,
    *,
    active_only: bool = False,
    symbol: str | None = None,
    resolved_symbol: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if active_only:
        clauses.append("active = 1")
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if resolved_symbol:
        clauses.append("resolved_symbol = ?")
        params.append(resolved_symbol)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, venue, symbol, resolved_symbol, side, order_type, trigger_price,
                   covered_size, order_id, client_request_id, source_order_submission_id,
                   dry_run, active, status, submitted_at_ms, response_json
            FROM protective_orders
            {where}
            ORDER BY submitted_at_ms DESC, id DESC
            """,
            params,
        ).fetchall()
    return [_protective_order_dict(row) for row in rows]


def store_trade_journal_entry(
    db_path: str | Path,
    *,
    record: TradeJournalRecord,
    stats: TradeJournalStats,
    created_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    created_at = created_at_ms or int(time.time() * 1000)
    stats_json = json.dumps(asdict(stats), default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_journal_entries (
              venue, symbol, strategy, side, opened_at_ms, closed_at_ms,
              entry_price, exit_price, quantity, realized_pnl, realized_pnl_pct,
              fees, holding_days, outcome, adjusted_outcome, notes, stats_json,
              created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.venue,
                record.symbol,
                record.strategy,
                record.side,
                record.opened_at_ms,
                record.closed_at_ms,
                str(record.entry_price),
                str(record.exit_price),
                str(record.quantity),
                str(record.realized_pnl),
                str(record.realized_pnl_pct),
                str(record.fees),
                str(record.holding_days),
                record.outcome,
                record.adjusted_outcome,
                record.notes,
                stats_json,
                created_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_trade_journal_entries(
    db_path: str | Path,
    *,
    symbol: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if strategy:
        clauses.append("strategy = ?")
        params.append(strategy)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, venue, symbol, strategy, side, opened_at_ms, closed_at_ms,
                   entry_price, exit_price, quantity, realized_pnl, realized_pnl_pct,
                   fees, holding_days, outcome, adjusted_outcome, notes, stats_json,
                   created_at_ms
            FROM trade_journal_entries
            {where}
            ORDER BY closed_at_ms DESC, id DESC
            """,
            params,
        ).fetchall()
    return [_trade_journal_entry_dict(row) for row in rows]


def seed_trade_xyz_assets(db_path: str | Path, *, updated_at_ms: int | None = None) -> int:
    init_db(db_path)
    updated_at = updated_at_ms or int(time.time() * 1000)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO trade_xyz_assets (
              trade_symbol, hyperliquid_coin, asset_class, underlying_name, underlying_symbol,
              underlying_exchange, listing_status, tradable, listing_date,
              min_listing_age_weeks, aliases_json, duplicate_group, preferred_symbol,
              exclusion_reason, source_url, notes, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_symbol) DO UPDATE SET
              hyperliquid_coin = excluded.hyperliquid_coin,
              asset_class = excluded.asset_class,
              underlying_name = excluded.underlying_name,
              underlying_symbol = excluded.underlying_symbol,
              underlying_exchange = excluded.underlying_exchange,
              listing_status = excluded.listing_status,
              tradable = excluded.tradable,
              listing_date = excluded.listing_date,
              min_listing_age_weeks = excluded.min_listing_age_weeks,
              aliases_json = excluded.aliases_json,
              duplicate_group = excluded.duplicate_group,
              preferred_symbol = excluded.preferred_symbol,
              exclusion_reason = excluded.exclusion_reason,
              source_url = excluded.source_url,
              notes = excluded.notes,
              updated_at_ms = excluded.updated_at_ms
            """,
            [_asset_row(asset, updated_at) for asset in TRADE_XYZ_ASSETS],
        )
        conn.commit()
        return len(TRADE_XYZ_ASSETS)


def list_trade_xyz_assets(
    db_path: str | Path,
    *,
    tradable_only: bool = False,
    asset_class: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if tradable_only:
        clauses.append("tradable = 1")
    if asset_class:
        clauses.append("asset_class = ?")
        params.append(asset_class)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT trade_symbol, hyperliquid_coin, asset_class, underlying_name,
                   underlying_symbol, underlying_exchange, listing_status, tradable,
                   listing_date, min_listing_age_weeks, aliases_json, duplicate_group,
                   preferred_symbol, exclusion_reason, source_url, notes, updated_at_ms
            FROM trade_xyz_assets
            {where}
            ORDER BY asset_class, trade_symbol
            """,
            params,
        ).fetchall()
    return [_asset_dict(row) for row in rows]


def store_trade_xyz_universe_snapshot(
    db_path: str | Path,
    *,
    dex: str,
    observed_at_ms: int,
    assets: list[dict[str, Any]],
    asset_contexts: list[dict[str, Any]] | None = None,
    new_symbols: list[str] | None = None,
    missing_symbols: list[str] | None = None,
    raw: Any | None = None,
    source: str = "hyperliquid",
) -> int:
    init_db(db_path)
    contexts = asset_contexts or []
    new_symbols_json = json.dumps(new_symbols or [], sort_keys=True)
    missing_symbols_json = json.dumps(missing_symbols or [], sort_keys=True)
    raw_json = json.dumps(raw or {}, default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_xyz_universe_snapshots (
              source, dex, observed_at_ms, asset_count, new_symbols_json,
              missing_symbols_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                dex,
                observed_at_ms,
                len(assets),
                new_symbols_json,
                missing_symbols_json,
                raw_json,
            ),
        )
        snapshot_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO trade_xyz_universe_assets (
              snapshot_id, source, dex, symbol, sz_decimals, max_leverage,
              margin_table_id, only_isolated, margin_mode, day_base_volume,
              day_notional_volume, open_interest, observed_at_ms, asset_context_json,
              raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _trade_xyz_universe_asset_row(
                    snapshot_id=snapshot_id,
                    source=source,
                    dex=dex,
                    asset=asset,
                    asset_context=contexts[index] if index < len(contexts) else {},
                    observed_at_ms=observed_at_ms,
                )
                for index, asset in enumerate(assets)
            ],
        )
        conn.commit()
        return snapshot_id


def get_latest_trade_xyz_universe_symbols(
    db_path: str | Path,
    *,
    dex: str = "xyz",
    source: str = "hyperliquid",
) -> set[str]:
    return {
        item["symbol"]
        for item in list_latest_trade_xyz_universe_assets(db_path, dex=dex, source=source)
    }


def list_latest_trade_xyz_universe_assets(
    db_path: str | Path,
    *,
    dex: str = "xyz",
    source: str = "hyperliquid",
) -> list[dict[str, Any]]:
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        snapshot = conn.execute(
            """
            SELECT id
            FROM trade_xyz_universe_snapshots
            WHERE source = ? AND dex = ?
            ORDER BY observed_at_ms DESC, id DESC
            LIMIT 1
            """,
            (source, dex),
        ).fetchone()
        if snapshot is None:
            return []
        rows = conn.execute(
            """
            SELECT id, snapshot_id, source, dex, symbol, sz_decimals, max_leverage,
                   margin_table_id, only_isolated, margin_mode, day_base_volume,
                   day_notional_volume, open_interest, observed_at_ms, asset_context_json,
                   raw_json
            FROM trade_xyz_universe_assets
            WHERE snapshot_id = ?
            ORDER BY symbol
            """,
            (snapshot["id"],),
        ).fetchall()
    return [_trade_xyz_universe_asset_dict(row) for row in rows]


def seed_trade_xyz_kis_mappings(db_path: str | Path, *, updated_at_ms: int | None = None) -> int:
    init_db(db_path)
    updated_at = updated_at_ms or int(time.time() * 1000)
    mappings = build_trade_xyz_kis_mappings()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO trade_xyz_kis_mappings (
              trade_symbol, hyperliquid_coin, asset_class, kis_market, kis_symbol,
              kis_exchange_code, kis_market_code, status, reason, source, notes,
              updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_symbol) DO UPDATE SET
              hyperliquid_coin = excluded.hyperliquid_coin,
              asset_class = excluded.asset_class,
              kis_market = excluded.kis_market,
              kis_symbol = excluded.kis_symbol,
              kis_exchange_code = excluded.kis_exchange_code,
              kis_market_code = excluded.kis_market_code,
              status = excluded.status,
              reason = excluded.reason,
              source = excluded.source,
              notes = excluded.notes,
              updated_at_ms = excluded.updated_at_ms
            """,
            [_kis_mapping_row(mapping, updated_at) for mapping in mappings],
        )
        conn.commit()
        return len(mappings)


def list_trade_xyz_kis_mappings(
    db_path: str | Path,
    *,
    status: str | None = None,
    kis_market: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if kis_market:
        clauses.append("kis_market = ?")
        params.append(kis_market)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT trade_symbol, hyperliquid_coin, asset_class, kis_market, kis_symbol,
                   kis_exchange_code, kis_market_code, status, reason, source, notes,
                   updated_at_ms
            FROM trade_xyz_kis_mappings
            {where}
            ORDER BY status, asset_class, trade_symbol
            """,
            params,
        ).fetchall()
    return [_kis_mapping_dict(row) for row in rows]


def get_trade_xyz_kis_mapping(db_path: str | Path, symbol: str) -> dict[str, Any] | None:
    mappings = list_trade_xyz_kis_mappings(db_path)
    normalized = normalize_trade_symbol(symbol)
    for mapping in mappings:
        if normalize_trade_symbol(mapping["trade_symbol"]) == normalized:
            return mapping
        if normalize_trade_symbol(mapping["hyperliquid_coin"]) == normalized:
            return mapping
    return None


def seed_trade_xyz_reference_mappings(
    db_path: str | Path,
    *,
    updated_at_ms: int | None = None,
) -> int:
    init_db(db_path)
    updated_at = updated_at_ms or int(time.time() * 1000)
    mappings = build_trade_xyz_reference_mappings()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO trade_xyz_reference_mappings (
              trade_symbol, hyperliquid_coin, asset_class, provider, provider_symbol,
              provider_market, provider_instrument_type, status, reason, source, notes,
              updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_symbol) DO UPDATE SET
              hyperliquid_coin = excluded.hyperliquid_coin,
              asset_class = excluded.asset_class,
              provider = excluded.provider,
              provider_symbol = excluded.provider_symbol,
              provider_market = excluded.provider_market,
              provider_instrument_type = excluded.provider_instrument_type,
              status = excluded.status,
              reason = excluded.reason,
              source = excluded.source,
              notes = excluded.notes,
              updated_at_ms = excluded.updated_at_ms
            """,
            [_reference_mapping_row(mapping, updated_at) for mapping in mappings],
        )
        conn.commit()
        return len(mappings)


def list_trade_xyz_reference_mappings(
    db_path: str | Path,
    *,
    provider: str | None = None,
    status: str | None = None,
    asset_class: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if asset_class:
        clauses.append("asset_class = ?")
        params.append(asset_class)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT trade_symbol, hyperliquid_coin, asset_class, provider,
                   provider_symbol, provider_market, provider_instrument_type,
                   status, reason, source, notes, updated_at_ms
            FROM trade_xyz_reference_mappings
            {where}
            ORDER BY provider, status, asset_class, trade_symbol
            """,
            params,
        ).fetchall()
    return [_reference_mapping_dict(row) for row in rows]


def get_trade_xyz_reference_mapping(db_path: str | Path, symbol: str) -> dict[str, Any] | None:
    mappings = list_trade_xyz_reference_mappings(db_path)
    normalized = normalize_trade_symbol(symbol)
    for mapping in mappings:
        if normalize_trade_symbol(mapping["trade_symbol"]) == normalized:
            return mapping
        if normalize_trade_symbol(mapping["hyperliquid_coin"]) == normalized:
            return mapping
        if normalize_trade_symbol(mapping["provider_symbol"]) == normalized:
            return mapping
    return None


def store_trade_xyz_asset_check(
    db_path: str | Path,
    *,
    trade_symbol: str,
    hyperliquid_coin: str,
    dex: str,
    available: bool,
    last_mid: str | None,
    mid_source_key: str | None,
    checked_at_ms: int | None = None,
    failure_reason: str | None = None,
    raw: Any | None = None,
) -> int:
    init_db(db_path)
    checked_at = checked_at_ms or int(time.time() * 1000)
    raw_json = json.dumps(raw or {}, default=str, sort_keys=True)
    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_xyz_asset_checks (
              trade_symbol, hyperliquid_coin, dex, available, last_mid, mid_source_key,
              checked_at_ms, failure_reason, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_symbol,
                hyperliquid_coin,
                dex,
                1 if available else 0,
                last_mid,
                mid_source_key,
                checked_at,
                failure_reason,
                raw_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_latest_trade_xyz_asset_check(
    db_path: str | Path,
    *,
    hyperliquid_coin: str,
) -> dict[str, Any] | None:
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, trade_symbol, hyperliquid_coin, dex, available, last_mid,
                   mid_source_key, checked_at_ms, failure_reason, raw_json
            FROM trade_xyz_asset_checks
            WHERE hyperliquid_coin = ?
            ORDER BY checked_at_ms DESC, id DESC
            LIMIT 1
            """,
            (hyperliquid_coin,),
        ).fetchone()
    return _check_dict(row) if row else None


def has_recent_successful_trade_xyz_check(
    db_path: str | Path,
    *,
    hyperliquid_coin: str,
    max_age_ms: int,
    now_ms: int | None = None,
) -> bool:
    latest = get_latest_trade_xyz_asset_check(db_path, hyperliquid_coin=hyperliquid_coin)
    if not latest or not latest["available"]:
        return False
    now = now_ms or int(time.time() * 1000)
    return now - int(latest["checked_at_ms"]) <= max_age_ms


def _extract_last_price(payload: Any) -> str | None:
    price_keys = (
        "last",
        "LAST",
        "price",
        "stck_prpr",
        "ovrs_now_pric",
        "clos",
        "bstp_nmix_prpr",
        "ovrs_nmix_prpr",
        "regularMarketPrice",
        "regular_market_price",
        "chart_last_close",
    )
    if isinstance(payload, dict):
        for key in price_keys:
            if key in payload and payload[key] not in (None, ""):
                return str(payload[key])
        for nested_key in ("output", "output1", "output2"):
            if nested_key in payload:
                value = _extract_last_price(payload[nested_key])
                if value is not None:
                    return value
    if isinstance(payload, list):
        for item in payload:
            value = _extract_last_price(item)
            if value is not None:
                return value
    return None


def _asset_row(asset: TradeXyzAsset, updated_at_ms: int) -> tuple[Any, ...]:
    return (
        asset.trade_symbol,
        asset.hyperliquid_coin,
        asset.asset_class,
        asset.underlying_name,
        asset.underlying_symbol,
        asset.underlying_exchange,
        asset.listing_status,
        1 if is_asset_tradable(asset) else 0,
        asset.listing_date,
        asset.min_listing_age_weeks,
        json.dumps(list(asset.aliases), sort_keys=True),
        asset.duplicate_group,
        asset.preferred_symbol,
        asset.exclusion_reason,
        asset.source_url,
        asset.notes,
        updated_at_ms,
    )


def _daily_bar_row(
    *,
    source: str,
    market: str,
    symbol: str,
    exchange_code: str | None,
    bar: dict[str, Any],
    observed_at_ms: int,
) -> tuple[Any, ...]:
    payload_json = json.dumps(bar, default=str, sort_keys=True)
    return (
        source,
        market,
        symbol,
        exchange_code,
        str(bar["date"]),
        _optional_text(bar.get("open")),
        _optional_text(bar.get("high")),
        _optional_text(bar.get("low")),
        _optional_text(bar.get("close")),
        _optional_text(bar.get("adj_close")),
        _optional_text(bar.get("volume")),
        observed_at_ms,
        payload_json,
    )


def _funding_rate_row(
    *,
    source: str,
    dex: str,
    symbol: str,
    row: dict[str, Any],
    observed_at_ms: int,
) -> tuple[Any, ...]:
    return (
        source,
        dex,
        symbol,
        int(row["time"]),
        str(row["fundingRate"]),
        _optional_text(row.get("premium")),
        observed_at_ms,
        json.dumps(row, default=str, sort_keys=True),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _asset_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tradable"] = bool(item["tradable"])
    item["aliases"] = json.loads(item.pop("aliases_json"))
    return item


def _funding_rate_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["raw"] = json.loads(item.pop("raw_json"))
    return item


def _spread_snapshot_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["raw"] = json.loads(item.pop("raw_json"))
    return item


def _kis_mapping_row(mapping: KisMarketDataMapping, updated_at_ms: int) -> tuple[Any, ...]:
    return (
        mapping.trade_symbol,
        mapping.hyperliquid_coin,
        mapping.asset_class,
        mapping.kis_market,
        mapping.kis_symbol,
        mapping.kis_exchange_code,
        mapping.kis_market_code,
        mapping.status,
        mapping.reason,
        mapping.source,
        mapping.notes,
        updated_at_ms,
    )


def _kis_mapping_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _reference_mapping_row(
    mapping: ReferenceMarketDataMapping,
    updated_at_ms: int,
) -> tuple[Any, ...]:
    return (
        mapping.trade_symbol,
        mapping.hyperliquid_coin,
        mapping.asset_class,
        mapping.provider,
        mapping.provider_symbol,
        mapping.provider_market,
        mapping.provider_instrument_type,
        mapping.status,
        mapping.reason,
        mapping.source,
        mapping.notes,
        updated_at_ms,
    )


def _reference_mapping_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _trade_xyz_universe_asset_row(
    *,
    snapshot_id: int,
    source: str,
    dex: str,
    asset: dict[str, Any],
    asset_context: dict[str, Any],
    observed_at_ms: int,
) -> tuple[Any, ...]:
    return (
        snapshot_id,
        source,
        dex,
        str(asset["name"]),
        _optional_int(asset.get("szDecimals")),
        _optional_int(asset.get("maxLeverage")),
        _optional_int(asset.get("marginTableId")),
        _optional_bool_int(asset.get("onlyIsolated")),
        _optional_text(asset.get("marginMode")),
        _optional_text(asset_context.get("dayBaseVlm")),
        _optional_text(asset_context.get("dayNtlVlm")),
        _optional_text(asset_context.get("openInterest")),
        observed_at_ms,
        json.dumps(asset_context, default=str, sort_keys=True),
        json.dumps(asset, default=str, sort_keys=True),
    )


def _trade_xyz_universe_asset_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    if item["only_isolated"] is not None:
        item["only_isolated"] = bool(item["only_isolated"])
    item["asset_context"] = json.loads(item.pop("asset_context_json"))
    item["raw"] = json.loads(item.pop("raw_json"))
    return item


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _check_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["available"] = bool(item["available"])
    item["raw"] = json.loads(item.pop("raw_json"))
    return item


def _protective_order_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["dry_run"] = bool(item["dry_run"])
    item["active"] = bool(item["active"])
    item["response"] = json.loads(item.pop("response_json"))
    return item


def _trade_journal_entry_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["stats"] = json.loads(item.pop("stats_json"))
    return item


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
