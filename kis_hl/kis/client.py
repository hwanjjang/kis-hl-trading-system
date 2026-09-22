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
    raw_body: bytes | None = None


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

    def inquire_domestic_index_price(
        self,
        *,
        index_code: str,
        market_code: str = "U",
    ) -> KisHttpResponse:
        return self._request_with_auth(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            tr_id="FHPUP02100000",
            query={
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": index_code,
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

    def inquire_overseas_time_indexchartprice(
        self,
        *,
        symbol: str,
        market_code: str = "N",
        hour_cls_code: str = "0",
        include_past_data: bool = True,
    ) -> KisHttpResponse:
        return self._request_with_auth(
            "GET",
            "/uapi/overseas-price/v1/quotations/inquire-time-indexchartprice",
            tr_id="FHKST03030200",
            query={
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": symbol,
                "FID_HOUR_CLS_CODE": hour_cls_code,
                "FID_PW_DATA_INCU_YN": "Y" if include_past_data else "N",
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

    def inquire_domestic_balance(self) -> KisHttpResponse:
        """Read the first domestic balance page, including the account summary."""
        return self._request_with_auth(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id="VTTC8434R" if self.config.mode == "sim" else "TTTC8434R",
            query={
                "CANO": self.config.account8,
                "ACNT_PRDT_CD": self.config.product_code2,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )

    def order_book(self, *, market: str, symbol: str, exchange: str = '') -> KisHttpResponse:
        if market == 'domestic':
            return self._request_with_auth('GET', '/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn',
                tr_id='FHKST01010200', query={'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':symbol})
        if market != 'overseas': raise ValueError('Unsupported quote market')
        return self._request_with_auth('GET', '/uapi/overseas-price/v1/quotations/inquire-asking-price',
            tr_id='HHDFS76200100', query={'AUTH':'','EXCD':exchange,'SYMB':symbol})

    def domestic_intraday_chart(self, *, symbol: str, hour: str) -> KisHttpResponse:
        return self._request_with_auth('GET', '/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice',
            tr_id='FHKST03010200', query={'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':symbol,
                'FID_INPUT_HOUR_1':hour,'FID_PW_DATA_INCU_YN':'N','FID_ETC_CLS_CODE':''})

    def overseas_intraday_chart(self, *, symbol: str, exchange: str, cursor: str = '') -> KisHttpResponse:
        """One page of local-time minute bars; KEYB is prior oldest minute minus one."""
        if cursor and (len(cursor)!=14 or not cursor.isdigit()):
            raise ValueError('Minute cursor must be YYYYMMDDHHMMSS')
        return self._request_with_auth('GET', '/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice',
            tr_id='HHDFS76950200', query={'AUTH':'','EXCD':exchange,'SYMB':symbol,
                'NMIN':'1','PINC':'1','NEXT':'1' if cursor else '',
                'NREC':'120','FILL':'','KEYB':cursor})

    def domestic_chart(self, *, symbol: str, date_from: str, date_to: str,
                       index: bool = False, adjusted: bool = True, period: str = 'D') -> KisHttpResponse:
        if period not in {'D', 'W', 'M', 'Y'}: raise ValueError('Invalid chart period')
        query = {'FID_COND_MRKT_DIV_CODE': 'U' if index else 'J', 'FID_INPUT_ISCD': symbol,
                 'FID_INPUT_DATE_1': date_from, 'FID_INPUT_DATE_2': date_to, 'FID_PERIOD_DIV_CODE': period}
        if not index: query['FID_ORG_ADJ_PRC'] = '0' if adjusted else '1'
        return self._request_with_auth('GET', '/uapi/domestic-stock/v1/quotations/' +
            ('inquire-daily-indexchartprice' if index else 'inquire-daily-itemchartprice'),
            tr_id='FHKUP03500100' if index else 'FHKST03010100', query=query)

    def overseas_stock_chart(self, *, symbol: str, exchange: str, end_date: str = '',
                             adjusted: bool = True, period: str = 'D') -> KisHttpResponse:
        if period not in {'D', 'W', 'M'}: raise ValueError('Invalid chart period')
        return self._request_with_auth('GET', '/uapi/overseas-price/v1/quotations/dailyprice',
            tr_id='HHDFS76240000', query={'AUTH':'','EXCD':exchange,'SYMB':symbol,
                                        'GUBN':{'D':'0','W':'1','M':'2'}[period],'BYMD':end_date,'MODP':'1' if adjusted else '0'})

    def account_pages(self, kind: str, *, exchange: str = 'NASD', symbol: str = '',
                      date_from: str = '', date_to: str = '', price: str = '0',
                      older_history: bool = False, max_pages: int = 100,
                      page_observer=None) -> dict[str, Any]:
        """Collect all pages; incomplete pagination is an error, never a partial success."""
        from kis_hl.kis.routes import account_route
        path, live_tr, paper_tr, query, width = account_route(kind, exchange=exchange,
            symbol=symbol, date_from=date_from, date_to=date_to, price=price,
            paper=self.config.mode=='sim', older_history=older_history)
        tr_id = paper_tr if self.config.mode=='sim' else live_tr
        if not tr_id: raise ValueError('This KIS inquiry has no verified paper route')
        if type(max_pages) is not int or max_pages <= 0: raise ValueError('Invalid page limit')
        query.update(CANO=self.config.account8, ACNT_PRDT_CD=self.config.product_code2)
        result = {'output':[], 'output1':[], 'output2':[]}
        seen=set(); continuation=''
        for page in range(max_pages):
            response=self._request_with_auth('GET',path,tr_id=tr_id,query=dict(query),tr_cont=continuation)
            body=response.body
            if response.status>=400 or not isinstance(body,dict) or body.get('rt_cd')!='0':
                raise RuntimeError('KIS account inquiry failed')
            if page_observer is not None:
                page_observer(response)
            for field in result:
                value=body.get(field,[])
                if isinstance(value,dict):value=[value]
                if not isinstance(value,list) or not all(isinstance(x,dict) for x in value):
                    raise RuntimeError('Malformed KIS account page')
                result[field].extend(value)
            headers={k.lower():v for k,v in response.headers.items()}
            if headers.get('tr_cont','').strip() not in {'F','M'}:
                return {**result,'pages':page+1,'complete':True}
            if not width: raise RuntimeError('Unexpected KIS pagination')
            fk,nk=f'CTX_AREA_FK{width}',f'CTX_AREA_NK{width}'
            cursor=(str(body.get(fk.lower(),body.get(fk,''))).strip(),str(body.get(nk.lower(),body.get(nk,''))).strip())
            if not any(cursor) or cursor in seen: raise RuntimeError('KIS pagination did not progress')
            seen.add(cursor);query[fk],query[nk]=cursor;continuation='N'
        raise RuntimeError('KIS pagination limit reached')

    def overseas_instrument_info(self, *, symbol: str, exchange: str) -> KisHttpResponse:
        products={'NASD':'512','NYSE':'513','AMEX':'529'}
        if exchange not in products:raise ValueError('Explicit US instrument route required')
        return self._request_with_auth('GET','/uapi/overseas-price/v1/quotations/search-info',
            tr_id='CTPF1702R',query={'PRDT_TYPE_CD':products[exchange],'PDNO':symbol})

    def cash_order(self, *, market: str, symbol: str, side: str, quantity: str,
                   price: str, exchange: str = 'KRX', order_type: str = 'limit',
                   dry_run: bool = True) -> dict[str, Any]:
        """Explicit cash limit orders only; supervisory risk gates belong to the caller."""
        from decimal import Decimal, InvalidOperation
        from kis_hl.execution_lock import account_lock
        try:q,p=Decimal(quantity),Decimal(price)
        except InvalidOperation:raise ValueError('Invalid order numbers') from None
        if not q.is_finite() or q<=0 or q!=q.to_integral_value() or not p.is_finite() or p<=0:
            raise ValueError('Positive whole-share quantity and price required')
        if order_type!='limit' or side not in {'buy','sell'} or market not in {'domestic','overseas'}:
            raise ValueError('Only explicit domestic/US cash limit orders are supported')
        if not symbol or not symbol.replace('.','').isalnum():raise ValueError('Invalid order symbol')
        if market=='domestic':
            if exchange!='KRX' or not symbol.isdigit() or len(symbol)!=6 or p!=p.to_integral_value():
                raise ValueError('Domestic orders require KRX, a six-digit symbol and integer KRW price')
            tr_id='TTTC0012U' if side=='buy' else 'TTTC0011U'
            body={'PDNO':symbol,'ORD_DVSN':'00','ORD_QTY':str(q),'ORD_UNPR':str(p),
                  'EXCG_ID_DVSN_CD':'KRX','SLL_TYPE':'01' if side=='sell' else '', 'CNDT_PRIC':''}
            path='/uapi/domestic-stock/v1/trading/order-cash'
        else:
            if exchange not in {'NASD','NYSE','AMEX'}:raise ValueError('Explicit US order exchange required')
            if self.config.mode=='sim' and side=='sell' and not dry_run:
                raise ValueError('US paper sell TR ID is unverified')
            tr_id='TTTT1002U' if side=='buy' else 'TTTT1006U'
            body={'PDNO':symbol,'OVRS_EXCG_CD':exchange,'ORD_QTY':str(q),'OVRS_ORD_UNPR':str(p),
                  'ORD_DVSN':'00','CTAC_TLNO':'','MGCO_APTM_ODNO':'','SLL_TYPE':'00' if side=='sell' else '', 'ORD_SVR_DVSN_CD':'0'}
            path='/uapi/overseas-stock/v1/trading/order'
        if self.config.mode=='sim':tr_id='V'+tr_id[1:]
        preview={'dry_run':dry_run,'market':market,'tr_id':tr_id,'request':dict(body)}
        if dry_run:return preview
        body.update(CANO=self.config.account8,ACNT_PRDT_CD=self.config.product_code2)
        with account_lock(self.config.base_url,self.config.account_id):
            response=self._request_with_auth('POST',path,tr_id=tr_id,body=body)
        if response.status>=400:raise RuntimeError('KIS order outcome is unknown; reconcile before retry')
        if not isinstance(response.body,dict) or 'rt_cd' not in response.body:
            raise RuntimeError('KIS order outcome is unknown; reconcile before retry')
        if response.body['rt_cd']!='0':return {**preview,'status':'rejected'}
        output=response.body.get('output',{})
        if not isinstance(output,dict) or not output.get('ODNO',output.get('odno')):
            raise RuntimeError('KIS order identifier missing; reconcile before retry')
        return {**preview,'status':'submitted','order_id':str(output.get('ODNO',output.get('odno'))),
                'organization_id':str(output.get('KRX_FWDG_ORD_ORGNO',output.get('krx_fwdg_ord_orgno','')))}

    def revise_cash_order(self, *, market: str, symbol: str, order_id: str,
                          quantity: str, price: str = '0', cancel: bool = True,
                          exchange: str = 'KRX', organization_id: str = '',
                          dry_run: bool = True) -> dict[str, Any]:
        from decimal import Decimal
        from kis_hl.execution_lock import account_lock
        q,p=Decimal(quantity),Decimal(price)
        if not q.is_finite() or q<=0 or q!=q.to_integral_value() or not p.is_finite() or p<0 or (not cancel and p<=0):
            raise ValueError('Invalid amend/cancel quantity or price')
        if not order_id.isdigit():raise ValueError('Native order ID required')
        if market=='domestic':
            if exchange!='KRX' or not organization_id:raise ValueError('Original KRX organization ID required')
            tr='VTTC0013U' if self.config.mode=='sim' else 'TTTC0013U'
            path='/uapi/domestic-stock/v1/trading/order-rvsecncl'
            body={'KRX_FWDG_ORD_ORGNO':organization_id,'ORGN_ODNO':order_id,'ORD_DVSN':'00',
                  'RVSE_CNCL_DVSN_CD':'02' if cancel else '01','ORD_QTY':str(q),'ORD_UNPR':str(p),
                  'QTY_ALL_ORD_YN':'N','EXCG_ID_DVSN_CD':'KRX'}
        elif market=='overseas' and exchange in {'NASD','NYSE','AMEX'}:
            tr='VTTT1004U' if self.config.mode=='sim' else 'TTTT1004U'
            path='/uapi/overseas-stock/v1/trading/order-rvsecncl'
            body={'OVRS_EXCG_CD':exchange,'PDNO':symbol,'ORGN_ODNO':order_id,
                  'RVSE_CNCL_DVSN_CD':'02' if cancel else '01','ORD_QTY':str(q),
                  'OVRS_ORD_UNPR':str(p),'MGCO_APTM_ODNO':'','ORD_SVR_DVSN_CD':'0'}
        else:raise ValueError('Unsupported cash order market')
        result={'dry_run':dry_run,'tr_id':tr,'request':dict(body)}
        if dry_run:return result
        body.update(CANO=self.config.account8,ACNT_PRDT_CD=self.config.product_code2)
        with account_lock(self.config.base_url,self.config.account_id):
            r=self._request_with_auth('POST',path,tr_id=tr,body=body)
        if r.status>=400 or not isinstance(r.body,dict) or 'rt_cd' not in r.body:
            raise RuntimeError('KIS amendment outcome unknown; reconcile before retry')
        return {**result,'status':'submitted' if r.body['rt_cd']=='0' else 'rejected'}

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

    def get_websocket_approval_key(self) -> str:
        response = self._request_json(
            "POST",
            "/oauth2/Approval",
            headers={
                "content-type": "application/json; charset=utf-8",
                "accept": "application/json",
            },
            body={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "secretkey": self.config.app_secret,
            },
        )
        if response.status >= 400:
            raise RuntimeError(f"KIS websocket approval request failed: HTTP {response.status}")
        if not isinstance(response.body, dict) or "approval_key" not in response.body:
            raise RuntimeError("KIS websocket approval response is missing approval_key")
        return str(response.body["approval_key"])

    def _request_with_auth(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        query: dict[str, str | int | float | None] | None = None,
        body: dict[str, Any] | None = None,
        tr_cont: str = "",
    ) -> KisHttpResponse:
        last_response: KisHttpResponse | None = None
        for attempt in range(self.config.rate_limit_retries + 1 if method == "GET" else 1):
            self._throttle()
            token = self.get_access_token()
            response = self._request_json(
                method,
                path,
                headers={**self._headers(token=token, tr_id=tr_id), "tr_cont": tr_cont, "custtype": "P"},
                query=query,
                body=body,
            )
            if method != "GET":
                return response
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
                raw_body = res.read()
                text = raw_body.decode("utf-8")
                parsed = json.loads(text) if text else {}
                return KisHttpResponse(res.status, parsed, dict(res.headers.items()), raw_body)
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
