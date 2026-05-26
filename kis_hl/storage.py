from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


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

