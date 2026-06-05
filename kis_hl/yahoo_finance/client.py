from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timezone
from typing import Any

from kis_hl.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class YahooFinanceQuote:
    ticker: str
    status: int
    price: str | None
    observed_at_ms: int
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class YahooFinanceDailyBars:
    ticker: str
    status: int
    bars: list[dict[str, Any]]
    observed_at_ms: int
    body: dict[str, Any]


class YahooFinanceClient:
    def __init__(
        self,
        *,
        base_url: str = "https://query2.finance.yahoo.com",
        timeout_seconds: float = 10,
        user_agent: str = "Mozilla/5.0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def chart_quote(
        self,
        *,
        ticker: str,
        range_name: str = "1d",
        interval: str = "1m",
    ) -> YahooFinanceQuote:
        body = self._request_json(
            f"/v8/finance/chart/{urllib.parse.quote(ticker, safe='')}",
            query={"range": range_name, "interval": interval},
        )
        result = _extract_chart_result(body)
        meta = result.get("meta", {})
        quote = _extract_quote_block(result)
        price = _coerce_price(meta.get("regularMarketPrice"))
        chart_last_close = _last_non_null(quote.get("close") if quote else None)
        if price is None:
            price = _coerce_price(chart_last_close)
        if price is None:
            raise RuntimeError(f"Yahoo Finance chart response for {ticker} did not include a price")

        observed_at_ms = _observed_at_ms(meta)
        payload = {
            "provider": "yahoo_finance",
            "ticker": ticker,
            "price": price,
            "regular_market_price": _coerce_price(meta.get("regularMarketPrice")),
            "chart_last_close": _coerce_price(chart_last_close),
            "currency": meta.get("currency"),
            "exchange_name": meta.get("exchangeName"),
            "instrument_type": meta.get("instrumentType"),
            "timezone": meta.get("timezone"),
            "regular_market_time": meta.get("regularMarketTime"),
            "observed_at_ms": observed_at_ms,
            "raw": body,
        }
        return YahooFinanceQuote(
            ticker=ticker,
            status=200,
            price=price,
            observed_at_ms=observed_at_ms,
            body=payload,
        )

    def chart_daily_bars(
        self,
        *,
        ticker: str,
        date_from: date,
        date_to: date,
    ) -> YahooFinanceDailyBars:
        body = self._request_json(
            f"/v8/finance/chart/{urllib.parse.quote(ticker, safe='')}",
            query={
                "period1": str(_date_to_epoch_seconds(date_from)),
                "period2": str(_date_to_epoch_seconds(date_to)),
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            },
        )
        result = _extract_chart_result(body)
        bars = _extract_daily_bars(result)
        observed_at_ms = int(time.time() * 1000)
        payload = {
            "provider": "yahoo_finance",
            "ticker": ticker,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "bar_count": len(bars),
            "meta": result.get("meta", {}),
            "raw": body,
        }
        return YahooFinanceDailyBars(
            ticker=ticker,
            status=200,
            bars=bars,
            observed_at_ms=observed_at_ms,
            body=payload,
        )

    def _request_json(self, path: str, *, query: dict[str, str]) -> dict[str, Any]:
        url = _build_url(self.base_url, path, query)
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"accept": "application/json", "user-agent": self.user_agent},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as res:
                text = res.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8")
            try:
                payload = json.loads(text) if text else {}
            except json.JSONDecodeError:
                payload = {"raw": text}
            logger.warning(
                "yahoo_finance_http_error",
                extra={"status": exc.code, "path": path},
            )
            raise RuntimeError(f"Yahoo Finance request failed: HTTP {exc.code} {payload}") from exc
        except urllib.error.URLError as exc:
            logger.error("yahoo_finance_url_error", extra={"reason": str(exc.reason)})
            raise


def _build_url(base_url: str, path: str, query: dict[str, str]) -> str:
    encoded = urllib.parse.urlencode(query)
    return base_url.rstrip("/") + "/" + path.lstrip("/") + "?" + encoded


def _extract_chart_result(body: dict[str, Any]) -> dict[str, Any]:
    chart = body.get("chart")
    if not isinstance(chart, dict):
        raise RuntimeError("Yahoo Finance chart response is missing chart")
    error = chart.get("error")
    if error:
        raise RuntimeError(f"Yahoo Finance chart error: {error}")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Yahoo Finance chart response is missing result")
    result = results[0]
    if not isinstance(result, dict):
        raise RuntimeError("Yahoo Finance chart result is not an object")
    return result


def _extract_quote_block(result: dict[str, Any]) -> dict[str, Any]:
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        return {}
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        return {}
    return quotes[0]


def _extract_daily_bars(result: dict[str, Any]) -> list[dict[str, Any]]:
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list):
        return []
    quote = _extract_quote_block(result)
    adjclose = _extract_adjclose_block(result)
    bars: list[dict[str, Any]] = []
    for index, raw_timestamp in enumerate(timestamps):
        if raw_timestamp is None:
            continue
        close = _list_value(quote.get("close"), index)
        if close is None:
            continue
        bar = {
            "date": datetime.fromtimestamp(int(raw_timestamp), timezone.utc).date().isoformat(),
            "timestamp": int(raw_timestamp),
            "open": _list_value(quote.get("open"), index),
            "high": _list_value(quote.get("high"), index),
            "low": _list_value(quote.get("low"), index),
            "close": close,
            "adj_close": _list_value(adjclose.get("adjclose"), index),
            "volume": _list_value(quote.get("volume"), index),
        }
        bars.append(bar)
    return bars


def _extract_adjclose_block(result: dict[str, Any]) -> dict[str, Any]:
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        return {}
    adjcloses = indicators.get("adjclose")
    if not isinstance(adjcloses, list) or not adjcloses or not isinstance(adjcloses[0], dict):
        return {}
    return adjcloses[0]


def _observed_at_ms(meta: dict[str, Any]) -> int:
    raw_market_time = meta.get("regularMarketTime")
    try:
        if raw_market_time is not None:
            return int(float(raw_market_time) * 1000)
    except (TypeError, ValueError):
        pass
    return int(time.time() * 1000)


def _date_to_epoch_seconds(value: date) -> int:
    return int(datetime.combine(value, datetime_time.min, tzinfo=timezone.utc).timestamp())


def _list_value(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _last_non_null(values: Any) -> Any:
    if not isinstance(values, list):
        return None
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _coerce_price(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
