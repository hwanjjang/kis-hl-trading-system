from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from kis_hl.reference_mappings import REFERENCE_PROVIDER_YAHOO
from kis_hl.storage import (
    get_trade_xyz_reference_mapping,
    list_trade_xyz_reference_mappings,
    store_market_payload,
)


@dataclass(frozen=True, slots=True)
class MappedReferenceResponse:
    response: Any
    exchange_code: str | None
    storage_market: str


def fetch_mapped_reference_response(
    client: Any,
    mapping: dict[str, Any],
    *,
    range_name: str = "1d",
    interval: str = "1m",
) -> MappedReferenceResponse:
    if mapping["status"] != "active":
        reason = mapping["reason"] or "mapping is not active"
        raise RuntimeError(
            f"Reference mapping for {mapping['trade_symbol']} is {mapping['status']}: {reason}"
        )

    provider = mapping["provider"]
    if provider != REFERENCE_PROVIDER_YAHOO:
        raise RuntimeError(f"Unsupported reference provider: {provider}")
    response = client.chart_quote(
        ticker=_require_mapping_value(mapping, "provider_symbol"),
        range_name=range_name,
        interval=interval,
    )
    return MappedReferenceResponse(
        response=response,
        exchange_code=mapping.get("provider_market"),
        storage_market=f"trade_xyz_reference_{provider}",
    )


def collect_trade_xyz_reference_quotes(
    db_path: str | Path,
    *,
    client: Any,
    symbols: Iterable[str] | None = None,
    provider: str | None = REFERENCE_PROVIDER_YAHOO,
    asset_class: str | None = None,
    store: bool = True,
    delay_ms: int = 0,
    fail_fast: bool = False,
    range_name: str = "1d",
    interval: str = "1m",
) -> dict[str, Any]:
    mappings = _resolve_collection_mappings(db_path, symbols, provider, asset_class)
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
            mapped = fetch_mapped_reference_response(
                client,
                mapping,
                range_name=range_name,
                interval=interval,
            )
            stored_id = None
            if store:
                stored_id = store_market_payload(
                    db_path,
                    source=mapping["provider"],
                    market=mapped.storage_market,
                    symbol=mapping["trade_symbol"],
                    exchange_code=mapped.exchange_code,
                    payload=mapped.response.body,
                    observed_at_ms=mapped.response.observed_at_ms,
                )
            results.append(
                {
                    "trade_symbol": mapping["trade_symbol"],
                    "status": "success",
                    "response_status": mapped.response.status,
                    "stored_id": stored_id,
                    "last_price": mapped.response.price,
                    "provider": mapping["provider"],
                    "provider_symbol": mapping["provider_symbol"],
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
                    "provider": mapping.get("provider"),
                    "provider_symbol": mapping.get("provider_symbol"),
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


def _resolve_collection_mappings(
    db_path: str | Path,
    symbols: Iterable[str] | None,
    provider: str | None,
    asset_class: str | None,
) -> list[dict[str, Any]]:
    if symbols:
        mappings: list[dict[str, Any]] = []
        for symbol in symbols:
            mapping = get_trade_xyz_reference_mapping(db_path, symbol)
            if mapping is None:
                mappings.append(
                    {
                        "trade_symbol": symbol,
                        "status": "missing",
                        "reason": "No trade.xyz reference mapping found.",
                    }
                )
            elif provider and mapping["provider"] != provider:
                mappings.append(
                    {
                        "trade_symbol": symbol,
                        "status": "missing",
                        "reason": f"No {provider} reference mapping found.",
                    }
                )
            elif asset_class and mapping["asset_class"] != asset_class:
                mappings.append(
                    {
                        "trade_symbol": symbol,
                        "status": "skipped",
                        "reason": f"Reference mapping is asset_class={mapping['asset_class']}.",
                    }
                )
            else:
                mappings.append(mapping)
        return mappings
    return list_trade_xyz_reference_mappings(
        db_path,
        provider=provider,
        status="active",
        asset_class=asset_class,
    )


def _require_mapping_value(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not value:
        raise RuntimeError(f"Reference mapping for {mapping['trade_symbol']} is missing {key}")
    return str(value)
