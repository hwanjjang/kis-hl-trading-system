from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from kis_hl.trade_xyz_assets import TRADE_XYZ_ASSETS, TradeXyzAsset, is_asset_tradable


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
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
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO market_ticks (
              source, market, symbol, exchange_code, observed_at_ms, last_price, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (source, market, symbol, exchange_code, observed_at, last_price, payload_json),
        )
        return int(cur.lastrowid)


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
    with sqlite3.connect(db_path) as conn:
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
        return int(cur.lastrowid)


def seed_trade_xyz_assets(db_path: str | Path, *, updated_at_ms: int | None = None) -> int:
    init_db(db_path)
    updated_at = updated_at_ms or int(time.time() * 1000)
    with sqlite3.connect(db_path) as conn:
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
    with sqlite3.connect(db_path) as conn:
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


def _extract_last_price(payload: Any) -> str | None:
    if isinstance(payload, dict):
        output = payload.get("output")
        if isinstance(output, dict):
            for key in ("last", "LAST", "stck_prpr", "ovrs_now_pric", "clos"):
                if key in output and output[key] not in (None, ""):
                    return str(output[key])
        for key in ("last", "LAST", "price"):
            if key in payload and payload[key] not in (None, ""):
                return str(payload[key])
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


def _asset_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tradable"] = bool(item["tradable"])
    item["aliases"] = json.loads(item.pop("aliases_json"))
    return item


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
