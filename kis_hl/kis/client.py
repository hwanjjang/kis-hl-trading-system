from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from kis_hl.config import KisConfig
from kis_hl.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class KisHttpResponse:
    status: int
    body: Any
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class TokenCache:
    access_token: str
    expires_at_ms: int
    last_issued_at_ms: int


class KisClient:
    def __init__(self, config: KisConfig) -> None:
        self.config = config
        self._next_available_at_ms = 0

    def inquire_domestic_price(self, *, symbol: str, market_code: str = "J") -> KisHttpResponse:
        return self._request_with_auth(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            query={
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": symbol,
            },
        )

    def inquire_overseas_price(self, *, exchange_code: str, symbol: str) -> KisHttpResponse:
        return self._request_with_auth(
            "GET",
            "/uapi/overseas-price/v1/quotations/price",
            tr_id="HHDFS00000300",
            query={
                "AUTH": "",
                "EXCD": exchange_code,
                "SYMB": symbol,
            },
        )

    def inquire_overseas_daily_chartprice(
        self,
        *,
        symbol: str,
        date_from: str,
        date_to: str,
        period: str = "D",
        market_code: str = "N",
    ) -> KisHttpResponse:
        return self._request_with_auth(
            "GET",
            "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
            tr_id="FHKST03030100",
            query={
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": date_from,
                "FID_INPUT_DATE_2": date_to,
                "FID_PERIOD_DIV_CODE": period,
            },
        )

    def get_access_token(self) -> str:
        cached = self._read_token_cache()
        now_ms = int(time.time() * 1000)
        if cached and cached.expires_at_ms - 30_000 > now_ms:
            return cached.access_token
        if cached and now_ms - cached.last_issued_at_ms < 60_000:
            wait_ms = 60_000 - (now_ms - cached.last_issued_at_ms)
            raise RuntimeError(f"KIS token refresh throttled; retry after {wait_ms}ms")
        fresh = self._issue_token()
        self._write_token_cache(fresh)
        return fresh.access_token

    def _request_with_auth(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        query: dict[str, str | int | float | None] | None = None,
        body: dict[str, Any] | None = None,
    ) -> KisHttpResponse:
        last_response: KisHttpResponse | None = None
        for attempt in range(self.config.rate_limit_retries + 1):
            self._throttle()
            token = self.get_access_token()
            response = self._request_json(
                method,
                path,
                headers=self._headers(token=token, tr_id=tr_id),
                query=query,
                body=body,
            )
            if response.status in (401, 403):
                logger.warning(
                    "kis_auth_retry",
                    extra={"status": response.status, "action": "invalidate_token"},
                )
                self._delete_token_cache()
                last_response = response
                continue
            if _is_rate_limited(response):
                last_response = response
                if attempt < self.config.rate_limit_retries:
                    delay_seconds = (self.config.rate_limit_delay_ms / 1000) * (2**attempt)
                    logger.warning(
                        "kis_rate_limit_retry",
                        extra={
                            "status": response.status,
                            "attempt": attempt + 1,
                            "delay_ms": int(delay_seconds * 1000),
                        },
                    )
                    time.sleep(delay_seconds)
                    continue
            return response
        if last_response:
            logger.error("kis_request_failed_after_retries", extra={"status": last_response.status})
            return last_response
        raise RuntimeError("KIS request failed without a response")

    def _issue_token(self) -> TokenCache:
        logger.info("issuing_kis_token", extra={"kis_mode": self.config.mode})
        response = self._request_json(
            "POST",
            "/oauth2/tokenP",
            headers={
                "content-type": "application/json; charset=utf-8",
                "accept": "application/json",
            },
            body={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
        )
        if response.status >= 400:
            raise RuntimeError(f"KIS token request failed: HTTP {response.status}")
        if not isinstance(response.body, dict) or "access_token" not in response.body:
            raise RuntimeError("KIS token response is missing access_token")
        expires_at = _parse_kis_expiry_ms(str(response.body["access_token_token_expired"]))
        return TokenCache(
            access_token=str(response.body["access_token"]),
            expires_at_ms=expires_at,
            last_issued_at_ms=int(time.time() * 1000),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        query: dict[str, str | int | float | None] | None = None,
        body: dict[str, Any] | None = None,
    ) -> KisHttpResponse:
        url = _build_url(self.config.base_url, path, query)
        encoded_body = None
        if body is not None:
            encoded_body = json.dumps(body, sort_keys=True).encode("utf-8")
        request = urllib.request.Request(url, data=encoded_body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.config.http_timeout_seconds) as res:
                text = res.read().decode("utf-8")
                parsed = json.loads(text) if text else {}
                return KisHttpResponse(res.status, parsed, dict(res.headers.items()))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8")
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {"raw": text}
            return KisHttpResponse(exc.code, parsed, dict(exc.headers.items()))
        except urllib.error.URLError as exc:
            logger.error("kis_http_error", extra={"reason": str(exc.reason)})
            raise

    def _headers(self, *, token: str, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "accept": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
        }

    def _throttle(self) -> None:
        interval = self.config.min_request_interval_ms
        if interval <= 0:
            return
        now_ms = int(time.time() * 1000)
        wait_ms = max(0, self._next_available_at_ms - now_ms)
        self._next_available_at_ms = max(self._next_available_at_ms, now_ms) + interval
        if wait_ms:
            time.sleep(wait_ms / 1000)

    def _token_path(self) -> Path:
        return self.config.token_dir / f"kis-token-{self.config.mode}.json"

    def _read_token_cache(self) -> TokenCache | None:
        try:
            raw = json.loads(self._token_path().read_text(encoding="utf-8"))
            return TokenCache(
                access_token=str(raw["access_token"]),
                expires_at_ms=int(raw["expires_at_ms"]),
                last_issued_at_ms=int(raw["last_issued_at_ms"]),
            )
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            return None

    def _write_token_cache(self, cache: TokenCache) -> None:
        self.config.token_dir.mkdir(parents=True, exist_ok=True)
        path = self._token_path()
        payload = json.dumps(
            {
                "access_token": cache.access_token,
                "expires_at_ms": cache.expires_at_ms,
                "last_issued_at_ms": cache.last_issued_at_ms,
            },
            sort_keys=True,
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
        finally:
            os.chmod(path, 0o600)

    def _delete_token_cache(self) -> None:
        try:
            self._token_path().unlink()
        except FileNotFoundError:
            pass


def _build_url(
    base_url: str,
    path: str,
    query: dict[str, str | int | float | None] | None,
) -> str:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        return url + "?" + urllib.parse.urlencode(clean_query)
    return url


def _parse_kis_expiry_ms(value: str) -> int:
    normalized = value.replace(" ", "T")
    parsed = datetime.fromisoformat(normalized)
    return int(parsed.timestamp() * 1000)


def _is_rate_limited(response: KisHttpResponse) -> bool:
    if response.status not in (429, 500):
        return False
    if isinstance(response.body, dict):
        if response.body.get("msg_cd") == "EGW00201":
            return True
        message = str(response.body.get("msg1", ""))
        return "초당 거래건수" in message
    return False
