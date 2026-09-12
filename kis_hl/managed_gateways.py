"""Venue-specific snapshots for the account supervisor; no inferred stop order names."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import time
from zoneinfo import ZoneInfo

from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.instruments import instrument, INSTRUMENTS
from kis_hl.journal_sync import Scope, decimal, encode
from kis_hl.journal_history import fetch_time_pages
from kis_hl.hyperliquid.client import (
    extract_hyperliquid_order_id,
    is_supported_live_asset,
)
from kis_hl.trading_hours import trading_session_decision_for_resolved_asset


def correlated(asset, symbol, venue):
    match = next(
        (x for x in INSTRUMENTS if x.venue == venue and x.symbol == symbol), None
    )
    # Unknown holdings are conservatively charged to the proposed group.
    if match is None:
        return True
    equities = {"S&P500", "Nasdaq100", "quantum", "memory", "memory_contract"}
    return (
        match.underlying == asset.underlying
        or {asset.underlying, match.underlying} <= equities
    )


class ManagedHyperliquidGateway:
    native_sl = True

    def __init__(self, info, trading):
        self.info, self.trading = info, trading
        self.network = info.config.base_url
        self.account = info.config.account_address
        self.scope = Scope(
            "hyperliquid",
            "testnet" if "testnet" in self.network else "mainnet",
            self.account,
        ).key

    def _market(self, key):
        asset = instrument(key)
        if asset.venue != "hyperliquid":
            raise ValueError("Venue mismatch")
        resolved = resolve_hyperliquid_symbol(asset.symbol)
        meta = self.info.meta_and_asset_ctxs(dex=resolved.dex)
        collateral = meta[0].get("collateralToken", 0 if not resolved.dex else None)
        if collateral != 0:
            raise ValueError("Only verified USDC collateral is supported")
        row = next(m for m in meta[0]["universe"] if m["name"] == resolved.coin)
        if row.get("isDelisted"):
            raise ValueError("Delisted execution asset")
        decimals = int(row["szDecimals"])
        if not 0 <= decimals <= 6:
            raise ValueError("Invalid perpetual quantity precision")
        # Conservative decimal tick; additionally enforce five significant figures below.
        return (
            asset,
            resolved,
            Decimal(10) ** (-decimals),
            Decimal(10) ** (-(6 - decimals)),
        )

    def _eligible(self, resolved):
        if not is_supported_live_asset(resolved):
            return False
        if resolved.dex != "xyz":
            return True
        from kis_hl.storage import list_trade_xyz_assets
        from datetime import date

        path = self.trading.verification_db_path
        if not path:
            return False
        matches = [
            x
            for x in list_trade_xyz_assets(path)
            if x["hyperliquid_coin"] == resolved.coin
        ]
        if len(matches) != 1:
            return False
        row = matches[0]
        if not row["tradable"] or row["listing_status"] not in {
            "listed",
            "not_applicable",
        }:
            return False
        if row["asset_class"] == "stock":
            if not row["listing_date"]:
                return False
            return (date.today() - date.fromisoformat(row["listing_date"])).days >= max(
                30, row["min_listing_age_weeks"]
            ) * 7
        return True

    def _quote(self, resolved):
        book = self.info.l2_book(resolved.coin)
        bid = decimal(book["levels"][0][0]["px"], positive=True)
        ask = decimal(book["levels"][1][0]["px"], positive=True)
        return bid, ask, int(book["time"])

    def _session(self, resolved, now):
        return trading_session_decision_for_resolved_asset(
            resolved, now=datetime.fromtimestamp(now / 1000, timezone.utc)
        ).allowed

    def preflight(self, p, now):
        asset, resolved, lot, tick = self._market(p["instrument"])
        price = decimal(p["limit_price"])
        if (
            price != price.to_integral_value()
            and len(price.normalize().as_tuple().digits) > 5
        ):
            raise ValueError("Hyperliquid price exceeds five significant figures")
        if price * decimal(p["quantity"]) < 10:
            raise ValueError("Order below minimum notional")
        self.trading._require_recent_verification(resolved)
        state = self.info.clearinghouse_state(dex=resolved.dex)
        positions = state["assetPositions"]
        current = next(
            (
                r["position"]["szi"]
                for r in positions
                if r["position"]["coin"] == resolved.coin
            ),
            "0",
        )
        bid, ask, timestamp = self._quote(resolved)
        portfolio = Decimal(0)
        group = Decimal(0)
        for dex in [None, "xyz"]:
            account = (
                state if dex == resolved.dex else self.info.clearinghouse_state(dex=dex)
            )
            for item in account["assetPositions"]:
                value = abs(decimal(item["position"]["positionValue"]))
                portfolio += value
                if correlated(asset, item["position"]["coin"], "hyperliquid"):
                    group += value
            for order in self.info.frontend_open_orders(dex=dex):
                if not order.get("reduceOnly", False):
                    value = decimal(order["sz"], positive=True) * decimal(
                        order["limitPx"], positive=True
                    )
                    portfolio += value
                    if correlated(asset, order["coin"], "hyperliquid"):
                        group += value
        from kis_hl.trailing_runner import fetch_trailing_atr

        atr, bars = fetch_trailing_atr(self.info, resolved.coin, now_ms=now)
        return {
            "price": str(bid),
            "ask": str(ask),
            "time_ms": timestamp,
            "position": current,
            "available_notional": state["withdrawable"],
            "open_orders": [
                o
                for o in self.info.frontend_open_orders(dex=resolved.dex)
                if o["coin"] == resolved.coin
            ],
            "eligible": self._eligible(resolved),
            "session_open": self._session(resolved, now),
            "portfolio_notional": str(portfolio),
            "correlated_notional": str(group),
            "atr": str(atr),
            "atr_source": {
                "instrument": asset.id,
                "basis": "Hyperliquid closed 1d bars / ATR(10)",
                "last_bar_end_ms": bars[-1]["T"],
                "sha256": hashlib.sha256(encode(bars).encode()).hexdigest(),
            },
            "quantity_step": str(lot),
            "price_step": str(tick),
            "observed_now_ms": int(time.time() * 1000),
        }

    def snapshot(self, row, attempts, now):
        asset, resolved, lot, tick = self._market(row["plan"]["instrument"])
        orders = {}
        for a in attempts:
            if a["kind"] == "cancel":
                continue
            query = a.get("order_id") or a["id"]
            result = self.info.order_status(
                oid=int(query) if str(query).isdigit() else query
            )
            if result["status"] == "unknownOid":
                continue
            status = result["order"]["status"]
            order = result["order"]["order"]
            if order["coin"] != resolved.coin:
                raise ValueError("Order identity mismatch")
            if a.get("order_id") and str(order["oid"]) != str(a["order_id"]):
                raise ValueError("Native order identifier mismatch")
            if not a.get("order_id") and order.get("cloid") != a["id"]:
                raise ValueError("Client order identifier mismatch")
            if order["side"] != ("B" if a["kind"] == "entry" else "A") or order.get(
                "reduceOnly"
            ) != (a["kind"] != "entry"):
                raise ValueError("Order direction or reduce-only contract mismatch")
            kind = (
                "stop"
                if (
                    order.get("isTrigger") is True
                    and order.get("orderType") == "Stop Market"
                    and order.get("reduceOnly") is True
                    and order.get("side") == "A"
                )
                else ("unverified" if a["kind"] == "stop" else a["kind"])
            )
            if a["kind"] == "stop" and kind != "stop":
                raise ValueError("Native SL semantics did not match")
            if status.endswith("Canceled"):
                status = "canceled"
            if status.endswith("Rejected"):
                status = "rejected"
            observed = {
                "status": status,
                "kind": kind,
                "native_id": str(order["oid"]),
                "size": str(order["sz"]),
                "trigger_price": str(order.get("triggerPx", "0")),
                "side": "sell" if order["side"] == "A" else "buy",
                "reduce_only": order.get("reduceOnly"),
                "trigger_type": "sl" if kind == "stop" else None,
            }
            orders[str(query)] = orders[str(order["oid"])] = observed
        fills = fetch_time_pages(
            lambda a, b: self.info.user_fills_by_time(start_time_ms=a, end_time_ms=b),
            row["created_ms"],
            now,
            limit=2000,
        )
        if len(fills) >= 10000:
            raise ValueError("Execution retention gap")
        for a in attempts:
            observed = orders.get(str(a.get("order_id") or a["id"]), {})
            if observed.get("native_id"):
                a["order_id"] = observed["native_id"]
        entries = {
            str(a.get("order_id"))
            for a in attempts
            if a["kind"] == "entry" and a.get("order_id")
        }
        owned = {str(a.get("order_id")) for a in attempts if a.get("order_id")}
        relevant = {str(f["tid"]): f for f in fills if f["coin"] == resolved.coin}
        net = Decimal(0)
        entry = Decimal(0)
        foreign = False
        for f in relevant.values():
            qty = decimal(f["sz"], positive=True)
            if f["side"] == "B":
                net += qty
                if str(f["oid"]) in entries:
                    entry += qty
                else:
                    foreign = True
            elif f["side"] == "A":
                net -= qty
            else:
                raise ValueError("Unknown execution side")
        opens = self.info.frontend_open_orders(dex=resolved.dex)
        foreign |= any(
            o["coin"] == resolved.coin and str(o["oid"]) not in owned for o in opens
        )
        state = self.info.clearinghouse_state(dex=resolved.dex)
        pos = next(
            (
                x["position"]
                for x in state["assetPositions"]
                if x["position"]["coin"] == resolved.coin
            ),
            None,
        )
        size = decimal(pos["szi"]) if pos else Decimal(0)
        try:
            bid, ask, timestamp = self._quote(resolved)
        except (ValueError, KeyError, IndexError, RuntimeError, OSError):
            bid, ask, timestamp = Decimal(0), Decimal(0), 0
        # HL reduce-only exits remain available outside the underlying entry session.
        return {
            "size": str(size),
            "entry_price": str(pos["entryPx"]) if pos and size else "0",
            "entry_filled": str(entry),
            "price": str(bid),
            "time_ms": timestamp,
            "sellable": str(max(size, 0)),
            "first_fill_time_ms": min(
                (f["time"] for f in relevant.values() if str(f["oid"]) in entries),
                default=None,
            ),
            "session_open": True,
            "foreign_add": foreign,
            "orders": orders,
            "consistent": net == size,
            "price_step": str(max(tick, Decimal(10) ** (bid.adjusted() - 4))),
            "quantity_step": str(lot),
            "observed_now_ms": int(time.time() * 1000),
        }

    def submit(self, row, a):
        asset = instrument(row["plan"]["instrument"])
        from kis_hl.managed_execution import entry_permit

        with entry_permit(self.scope, asset.id, a["id"]):
            result = self.trading.place_order(
                symbol=asset.symbol,
                side="buy" if a["kind"] == "entry" else "sell",
                order_type="stop-market" if a["kind"] == "stop" else "limit",
                size=decimal(a["quantity"]),
                price=decimal(a["price"]),
                trigger_price=(
                    decimal(a["trigger_price"]) if a["kind"] == "stop" else None
                ),
                reduce_only=a["kind"] != "entry",
                tif="Ioc" if a["kind"] == "exit" else "Gtc",
                cloid=a["id"],
                dry_run=False,
                expires_after_ms=a["created_ms"] + row["plan"]["max_quote_age_ms"],
            )
        return {
            "status": result.status,
            "order_id": extract_hyperliquid_order_id(result.response),
        }

    def cancel(self, row, a):
        result = self.trading.cancel_order(
            symbol=instrument(row["plan"]["instrument"]).symbol,
            oid=int(a["target_id"]),
            dry_run=False,
        )
        return {"status": result.status}


class ManagedKisGateway:
    native_sl = False

    def __init__(self, client):
        self.client = client
        self.network = client.config.base_url
        self.account = client.config.account_id
        self.scope = Scope("kis", client.config.mode, self.account).key

    def _asset(self, key):
        asset = instrument(key)
        if (
            asset.venue != "kis"
            or asset.market not in {"domestic", "overseas"}
            or not asset.order_exchange
        ):
            raise ValueError("KIS execution route is unverified")
        return asset

    def _session(self, asset, now):
        from kis_hl.trading_hours import trading_session_decision_for_symbol

        key = "xyz:KR200" if asset.market == "domestic" else "xyz:SP500"
        return trading_session_decision_for_symbol(
            key, now=datetime.fromtimestamp(now / 1000, timezone.utc)
        ).allowed

    def _history(self, asset, created, now):
        zone = ZoneInfo(
            "Asia/Seoul" if asset.market == "domestic" else "America/New_York"
        )
        start = datetime.fromtimestamp(created / 1000, zone).strftime("%Y%m%d")
        end = datetime.fromtimestamp(now / 1000, zone).strftime("%Y%m%d")
        r = self.client.account_pages(
            asset.market + "_history", date_from=start, date_to=end, exchange="NASD"
        )
        return r["output1"] if asset.market == "domestic" else r["output"]

    def _rows(self, asset):
        r = self.client.account_pages(asset.market + "_balance", exchange="NASD")
        return r["output1"]

    def _quote(self, asset):
        r = self.client.order_book(
            market=asset.market, symbol=asset.symbol, exchange=asset.quote_exchange
        )
        if (
            r.status >= 400
            or not isinstance(r.body, dict)
            or r.body.get("rt_cd") != "0"
        ):
            raise RuntimeError("KIS quote failed")

        def obj(value):
            if isinstance(value, list) and len(value) == 1:
                return value[0]
            if isinstance(value, dict):
                return value
            raise ValueError("Malformed KIS quote")

        if asset.market == "domestic":
            q = obj(r.body["output1"])
            local = datetime.now(ZoneInfo("Asia/Seoul"))
            bars = self.client.domestic_intraday_chart(
                symbol=asset.symbol, hour=local.strftime("%H%M%S")
            )
            if bars.status >= 400 or bars.body.get("rt_cd") != "0":
                raise RuntimeError("KIS quote date verification failed")
            dates = {x["stck_bsop_date"] for x in bars.body["output2"]}
            if local.strftime("%Y%m%d") not in dates:
                raise ValueError("No current-session execution date")
            rawdate = local.strftime("%Y%m%d")
            raw = q["aspr_acpt_hour"]
            price = q["bidp1"]
            ask = q["askp1"]
            zone = ZoneInfo("Asia/Seoul")
        else:
            header = obj(r.body["output1"])
            q = obj(r.body["output2"])
            if header["code"] != asset.symbol or header["curr"] != asset.currency:
                raise ValueError("KIS quote instrument/currency mismatch")
            rawdate = header["dymd"]
            raw = header["dhms"]
            price = q["pbid1"]
            ask = q["pask1"]
            # KIS REST quote receipt clock; distinct from the US execution calendar.
            zone = ZoneInfo("Asia/Seoul")
        stamp = int(
            datetime.strptime(rawdate + raw, "%Y%m%d%H%M%S")
            .replace(tzinfo=zone)
            .timestamp()
            * 1000
        )
        return decimal(price, positive=True), decimal(ask, positive=True), stamp

    def _atr(self, asset, now):
        zone = ZoneInfo(
            "Asia/Seoul" if asset.market == "domestic" else "America/New_York"
        )
        today = datetime.fromtimestamp(now / 1000, zone).date()
        end = today - timedelta(days=1)
        if asset.market == "domestic":
            result = self.client.domestic_chart(
                symbol=asset.symbol,
                date_from=(today - timedelta(days=60)).strftime("%Y%m%d"),
                date_to=end.strftime("%Y%m%d"),
            )
            names = ("stck_bsop_date", "stck_hgpr", "stck_lwpr", "stck_clpr")
        else:
            result = self.client.overseas_stock_chart(
                symbol=asset.symbol,
                exchange=asset.quote_exchange,
                end_date=end.strftime("%Y%m%d"),
            )
            names = ("xymd", "high", "low", "clos")
        if result.status >= 400 or result.body.get("rt_cd") != "0":
            raise ValueError("ATR source unavailable")
        bars = []
        for raw in result.body["output2"]:
            day = datetime.strptime(raw[names[0]], "%Y%m%d").date()
            if day >= today:
                continue
            high, low, close = [decimal(raw[n], positive=True) for n in names[1:]]
            if not low <= close <= high:
                raise ValueError("Invalid execution-instrument OHLC")
            bars.append(
                {
                    "date": day.isoformat(),
                    "high": str(high),
                    "low": str(low),
                    "close": str(close),
                }
            )
        bars = sorted(bars, key=lambda b: b["date"])[-11:]
        if (
            len(bars) != 11
            or len({b["date"] for b in bars}) != 11
            or (today - datetime.fromisoformat(bars[-1]["date"]).date()).days > 7
        ):
            raise ValueError("Eleven recent unique closed daily bars required")
        from kis_hl.risk import calculate_atr_10d

        return str(calculate_atr_10d(bars)), {
            "instrument": asset.id,
            "basis": "KIS adjusted closed 1d bars / ATR(10)",
            "last_bar_date": bars[-1]["date"],
            "sha256": hashlib.sha256(encode(bars).encode()).hexdigest(),
        }

    @staticmethod
    def _quantity(r, market):
        return decimal(r["tot_ccld_qty"] if market == "domestic" else r["ft_ccld_qty"])

    def preflight(self, p, now):
        asset = self._asset(p["instrument"])
        rows = self._rows(asset)
        if asset.market == "overseas":
            r = self.client.overseas_instrument_info(
                symbol=asset.symbol, exchange=asset.order_exchange
            )
            if r.status >= 400 or r.body.get("rt_cd") != "0":
                raise ValueError("KIS instrument metadata unavailable")
            m = r.body["output"]
            if (
                m["ovrs_excg_cd"] != asset.order_exchange
                or m["tr_crcy_cd"] != asset.currency
                or m["lstg_yn"] != "Y"
                or m["lstg_abol_item_yn"] != "N"
                or decimal(m["buy_unit_qty"]) != 1
                or decimal(m["sll_unit_qty"]) != 1
            ):
                raise ValueError("KIS execution metadata mismatch")
        pos = next((r for r in rows if r["pdno"] == asset.symbol), None)
        size = (
            pos["hldg_qty" if asset.market == "domestic" else "ovrs_cblc_qty"]
            if pos
            else "0"
        )
        orders = self.client.account_pages(asset.market + "_orders", exchange="NASD")[
            "output"
        ]
        power = self.client.account_pages(
            asset.market + "_buying_power",
            exchange=asset.order_exchange,
            symbol=asset.symbol,
            price=p["limit_price"],
        )["output"][0]
        available = (
            power["ord_psbl_cash"]
            if asset.market == "domestic"
            else power["ovrs_ord_psbl_amt"]
        )
        price, ask, stamp = self._quote(asset)
        portfolio = Decimal(0)
        group = Decimal(0)
        for holding in rows:
            value = abs(
                decimal(
                    holding[
                        (
                            "evlu_amt"
                            if asset.market == "domestic"
                            else "ovrs_stck_evlu_amt"
                        )
                    ]
                )
            )
            portfolio += value
            if correlated(asset, holding["pdno"], "kis"):
                group += value
        for order in orders:
            value = decimal(
                order["psbl_qty" if asset.market == "domestic" else "nccs_qty"]
            ) * decimal(
                order["ord_unpr" if asset.market == "domestic" else "ft_ord_unpr3"]
            )
            portfolio += value
            if correlated(asset, order["pdno"], "kis"):
                group += value
        atr, atr_source = self._atr(asset, now)
        history = self._history(asset, now, now)
        baseline = {
            str(r["odno"]): str(self._quantity(r, asset.market))
            for r in history
            if r["pdno"] == asset.symbol
        }
        return {
            "price": str(price),
            "ask": str(ask),
            "time_ms": stamp,
            "position": size,
            "available_notional": available,
            "portfolio_notional": str(portfolio),
            "correlated_notional": str(group),
            "atr": atr,
            "atr_source": atr_source,
            "open_orders": [o for o in orders if o["pdno"] == asset.symbol],
            "eligible": True,
            "session_open": self._session(asset, now),
            "quantity_step": "1",
            "price_step": p.get("verified_price_step", "0"),
            "baseline": baseline,
            "observed_now_ms": int(time.time() * 1000),
        }

    def snapshot(self, row, attempts, now):
        asset = self._asset(row["plan"]["instrument"])
        history = self._history(asset, row["created_ms"], now)
        owned = {
            str(a["order_id"]): a
            for a in attempts
            if a.get("order_id") and a["kind"] != "cancel"
        }
        entries = {k for k, a in owned.items() if a["kind"] == "entry"}
        orders = {}
        net = Decimal(0)
        entry = Decimal(0)
        foreign = False
        for r in history:
            if r["pdno"] != asset.symbol:
                continue
            oid = str(r["odno"])
            cum = self._quantity(r, asset.market)
            if (
                sum(
                    str(x["odno"]) == oid and x["pdno"] == asset.symbol for x in history
                )
                > 1
            ):
                raise ValueError("Ambiguous reused KIS order identity")
            old = decimal(row.get("baseline", {}).get(oid, "0"))
            delta = cum - old
            if delta < 0:
                raise ValueError("KIS cumulative history revised")
            side = r.get("sll_buy_dvsn_cd", r.get("sll_buy_dvsn"))
            if side == "02":
                net += delta
                if oid in entries:
                    entry += delta
                elif delta:
                    foreign = True
            elif side == "01":
                net -= delta
            else:
                raise ValueError("Unknown KIS execution side")
            if oid in owned:
                qty = decimal(r["ord_qty"])
                status = (
                    "canceled"
                    if r.get("cncl_yn") == "Y"
                    else ("filled" if cum == qty else "open")
                )
                orders[oid] = {
                    "status": status,
                    "kind": owned[oid]["kind"],
                    "size": str(qty - cum),
                }
        open_rows = self.client.account_pages(
            asset.market + "_orders", exchange="NASD"
        )["output"]
        foreign |= any(
            r["pdno"] == asset.symbol and str(r["odno"]) not in owned for r in open_rows
        )
        positions = self._rows(asset)
        pos = next((r for r in positions if r["pdno"] == asset.symbol), None)
        size = (
            decimal(pos["hldg_qty" if asset.market == "domestic" else "ovrs_cblc_qty"])
            if pos
            else Decimal(0)
        )
        entry_price = (
            pos["pchs_avg_pric" if asset.market == "domestic" else "pchs_avg_pric"]
            if pos and size
            else "0"
        )
        sellable = pos["ord_psbl_qty"] if pos else "0"
        try:
            price, ask, stamp = self._quote(asset)
        except (ValueError, KeyError, IndexError, RuntimeError, OSError):
            price, ask, stamp = Decimal(0), Decimal(0), 0
        return {
            "size": str(size),
            "entry_price": entry_price,
            "entry_filled": str(entry),
            "price": str(price),
            "time_ms": stamp,
            "sellable": sellable,
            "session_open": self._session(asset, now),
            "foreign_add": foreign,
            "consistent": net == size,
            "orders": orders,
            "quantity_step": "1",
            "price_step": row["plan"].get("verified_price_step", "0"),
            "observed_now_ms": int(time.time() * 1000),
        }

    def submit(self, row, a):
        asset = self._asset(row["plan"]["instrument"])
        if a["kind"] == "stop":
            raise ValueError("Native KIS protection is unverified")
        return self.client.cash_order(
            market=asset.market,
            symbol=asset.symbol,
            side="buy" if a["kind"] == "entry" else "sell",
            quantity=a["quantity"],
            price=a["price"],
            exchange=asset.order_exchange,
            dry_run=False,
        )

    def cancel(self, row, a):
        asset = self._asset(row["plan"]["instrument"])
        return self.client.revise_cash_order(
            market=asset.market,
            symbol=asset.symbol,
            order_id=a["target_id"],
            quantity=a["quantity"],
            exchange=asset.order_exchange,
            organization_id=a.get("organization_id", ""),
            dry_run=False,
        )
