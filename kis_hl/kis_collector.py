from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from kis_hl.storage import (
    get_trade_xyz_kis_mapping,
    list_trade_xyz_kis_mappings,
    store_market_payload,
)


@dataclass(frozen=True, slots=True)
class MappedKisResponse:
    response: Any
    exchange_code: str | None
    storage_market: str


def fetch_mapped_kis_response(client: Any, mapping: dict[str, Any]) -> MappedKisResponse:
    if mapping["status"] != "active":
        reason = mapping["reason"] or "mapping is not active"
        raise RuntimeError(
            f"KIS mapping for {mapping['trade_symbol']} is {mapping['status']}: {reason}"
        )

    kis_symbol = _require_mapping_value(mapping, "kis_symbol")
    kis_market = mapping["kis_market"]
    if kis_market == "domestic":
        response = client.inquire_domestic_price(
            symbol=kis_symbol,
            market_code=mapping["kis_market_code"] or "J",
        )
        exchange_code = None
    elif kis_market == "overseas":
        exchange_code = _require_mapping_value(mapping, "kis_exchange_code")
        response = client.inquire_overseas_price(
            exchange_code=exchange_code,
            symbol=kis_symbol,
        )
    elif kis_market == "domestic_index":
        market_code = mapping["kis_market_code"] or "U"
        response = client.inquire_domestic_index_price(
            index_code=kis_symbol,
            market_code=market_code,
        )
        exchange_code = market_code
    elif kis_market == "overseas_index_time":
        market_code = mapping["kis_market_code"] or "N"
        response = client.inquire_overseas_time_indexchartprice(
            symbol=kis_symbol,
            market_code=market_code,
            hour_cls_code="0",
            include_past_data=True,
        )
        exchange_code = market_code
    else:
        raise RuntimeError(f"Unsupported KIS market route: {kis_market}")

    raise_on_kis_failure(response.status, response.body)
    return MappedKisResponse(
        response=response,
        exchange_code=exchange_code,
        storage_market=f"trade_xyz_{kis_market}",
    )


def collect_trade_xyz_kis_quotes(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None = None,
    store: bool = True,
    delay_ms: int = 0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    mappings = _resolve_collection_mappings(db_path, symbols)
    results: list[dict[str, Any]] = []
    for index, mapping in enumerate(mappings):
        if index and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if mapping["status"] != "active":
            results.append(
                {
                    "trade_symbol": mapping["trade_symbol"],
                    "status": "skipped",
                    "reason": mapping["reason"] or f"mapping is {mapping['status']}",
                    "mapping_status": mapping["status"],
                }
            )
            continue
        try:
            mapped = fetch_mapped_kis_response(client, mapping)
            stored_id = None
            if store:
                stored_id = store_market_payload(
                    db_path,
                    source="kis",
                    market=mapped.storage_market,
                    symbol=mapping["trade_symbol"],
                    exchange_code=mapped.exchange_code,
                    payload=mapped.response.body,
                )
            results.append(
                {
                    "trade_symbol": mapping["trade_symbol"],
                    "status": "success",
                    "response_status": mapped.response.status,
                    "stored_id": stored_id,
                    "last_price": _extract_last_price(mapped.response.body),
                    "kis_market": mapping["kis_market"],
                    "kis_symbol": mapping["kis_symbol"],
                }
            )
        except Exception as exc:
            if fail_fast:
                raise
            results.append(
                {
                    "trade_symbol": mapping["trade_symbol"],
                    "status": "failed",
                    "error": str(exc),
                    "kis_market": mapping["kis_market"],
                    "kis_symbol": mapping["kis_symbol"],
                }
            )

    return {
        "requested": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "stored": sum(1 for item in results if item.get("stored_id") is not None),
        "results": results,
    }


def raise_on_kis_failure(status: int, body: Any) -> None:
    if status >= 400:
        raise RuntimeError(f"KIS request failed: HTTP {status}")
    if isinstance(body, dict):
        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            msg_cd = body.get("msg_cd", "unknown")
            msg = body.get("msg1", "")
            raise RuntimeError(f"KIS request failed: {msg_cd} {msg}".strip())


def _resolve_collection_mappings(
    db_path: str | Path,
    symbols: Iterable[str] | None,
) -> list[dict[str, Any]]:
    if symbols:
        mappings: list[dict[str, Any]] = []
        for symbol in symbols:
            mapping = get_trade_xyz_kis_mapping(db_path, symbol)
            if mapping is None:
                mappings.append(
                    {
                        "trade_symbol": symbol,
                        "status": "missing",
                        "reason": "No trade.xyz KIS mapping found.",
                    }
                )
            else:
                mappings.append(mapping)
        return mappings
    return list_trade_xyz_kis_mappings(db_path, status="active")


def _require_mapping_value(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not value:
        raise RuntimeError(f"KIS mapping for {mapping['trade_symbol']} is missing {key}")
    return str(value)


def _extract_last_price(payload: Any) -> str | None:
    from kis_hl.storage import _extract_last_price as extract_last_price

    return extract_last_price(payload)
