"""Venue-specific snapshots for the account supervisor; no inferred stop order names."""

from dataclasses import asdict
from datetime import datetime, timezone, timedelta, time as dt_time
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
from kis_hl.trading_hours import (
    SESSION_KRX_CASH, SESSION_US_CASH, regular_cash_session_elapsed_ms,
    trading_session_decision_for_resolved_asset,
)

KRX_BAR_FINAL = dt_time(15, 40)


class KisSessionClosed(ValueError):
    """The KIS execution session is not trading (closed, holiday or pre-first-trade)."""


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
    native_trailing = True

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

    def _entry_quote(self, resolved, quantity):
        """Use market only when visible full-size impact is within 50 bps."""
        book = self.info.l2_book(resolved.coin)
        bid = decimal(book["levels"][0][0]["px"], positive=True)
        asks = book["levels"][1]
        ask = decimal(asks[0]["px"], positive=True)
        if ask < bid:
            raise ValueError("Crossed execution book")
        remaining, cost = quantity, Decimal(0)
        for level in asks:
            price = decimal(level["px"], positive=True)
            depth = decimal(level["sz"], positive=True)
            take = min(remaining, depth)
            cost += take * price
            remaining -= take
            if remaining == 0:
                break
        # Incomplete depth cannot justify a market order.
        market = remaining == 0 and (cost / quantity - bid) / bid <= Decimal("0.005")
        return bid, ask, int(book["time"]), "market" if market else "limit"

    def _session(self, resolved, now):
        # Hyperliquid is a 24h venue; the underlying-market session is advisory
        # for HL (including trade.xyz RWA) entries and never blocks execution.
        return True

    def _session_advisory(self, resolved, now):
        return asdict(trading_session_decision_for_resolved_asset(
            resolved, now=datetime.fromtimestamp(now / 1000, timezone.utc)
        ))

    def preflight(self, p, now, *, existing_position=False):
        asset, resolved, lot, tick = self._market(p["instrument"])
        price = decimal(p["limit_price"])
        if (
            not existing_position and price != price.to_integral_value()
            and len(price.normalize().as_tuple().digits) > 5
        ):
            raise ValueError("Hyperliquid price exceeds five significant figures")
        if not existing_position and price * decimal(p["quantity"]) < 10:
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
        if existing_position:
            bid, ask, timestamp = self._quote(resolved)
            entry_type = None
        else:
            bid, ask, timestamp, entry_type = self._entry_quote(resolved, decimal(p["quantity"], positive=True))
            if p.get("entry_route") == "limit":
                entry_type = "limit"
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

        if p.get('percentage_entry_authorization'):
            atr, bars = decimal(p['atr']), []  # Schema compatibility only; no ATR exit policy.
        else:
            atr, bars = fetch_trailing_atr(self.info, resolved.coin, now_ms=now)
        capital = {}
        if p.get("action") == "add" or p.get('percentage_entry_authorization'):
            from kis_hl.account_capital import capture_capital
            capital = {"capital_evidence": capture_capital(self.info, scope=self.scope,
                now_ms=now, max_age_ms=p["max_quote_age_ms"])}
        # Buying power is account/instrument-bound: with a unified (portfolio-margin)
        # account the per-dex ``withdrawable`` can read 0 while the instrument is
        # still tradable, so entries and adds both use activeAssetData.
        buying_power = self.info.active_asset_data(asset.symbol)
        sizes = buying_power.get("maxTradeSzs")
        margins = buying_power.get("availableToTrade")
        if any(not isinstance(values, list) or len(values) != 2 for values in (sizes, margins)):
            raise ValueError("Account/instrument buying power unavailable")
        sizes, margins = [decimal(x) for x in sizes], [decimal(x) for x in margins]
        if min(sizes + margins) < 0:
            raise ValueError("Invalid account/instrument buying power")
        # Conservatively bound by both directional limits; never infer 10x buying power.
        available_notional = str(min(sizes) * price)
        capital["buying_power"] = buying_power
        return {
            **capital,
            "price": str(bid),
            "ask": str(ask),
            "time_ms": timestamp,
            "entry_order_type": entry_type,
            "position": current,
            "available_notional": available_notional,
            "open_orders": [
                o
                for o in self.info.frontend_open_orders(dex=resolved.dex)
                if o["coin"] == resolved.coin
            ],
            "eligible": self._eligible(resolved),
            "session_open": self._session(resolved, now),
            "session_advisory": self._session_advisory(resolved, now),
            "portfolio_notional": str(portfolio),
            "correlated_notional": str(group),
            "atr": str(atr),
            "atr_source": {
                "instrument": asset.id,
                "basis": "Manual fixed SL / native percent; ATR not used" if not bars else "Hyperliquid closed 1d bars / ATR(10)",
                "last_bar_end_ms": bars[-1]["T"] if bars else None,
                "sha256": hashlib.sha256(encode(bars).encode()).hexdigest(),
            },
            "quantity_step": str(lot),
            "price_step": str(tick),
            "trailing_price_step": str(tick),
            "observed_now_ms": int(time.time() * 1000),
        }

    def completed_nine_minute_bars(self, instrument_id, now):
        """Derive two adjacent UTC-aligned 9m bars from complete native 1m bars."""
        from kis_hl.intraday_add import NINE_MINUTES
        asset, resolved, _, _ = self._market(instrument_id)
        end = now // NINE_MINUTES * NINE_MINUTES
        start = end - 2*NINE_MINUTES
        raw = self.info.candle_snapshot(resolved.coin, interval="1m",
                                       start_time_ms=start, end_time_ms=end)
        minutes = {}
        for bar in raw:
            t = bar.get("t")
            if type(t) is not int or t % 60000:
                raise ValueError("Invalid native one-minute candle timestamp")
            if not start <= t < end:
                continue
            if (bar.get("s") != resolved.coin or bar.get("i") != "1m"
                    or bar.get("T") not in {t+59999, t+60000} or t in minutes):
                raise ValueError("Invalid or duplicate native candle identity")
            minutes[t] = bar
        if set(minutes) != set(range(start, end, 60000)):
            return []  # Incomplete history never establishes a breakout.
        result = []
        for left in (start, start+NINE_MINUTES):
            rows = [minutes[t] for t in range(left, left+NINE_MINUTES, 60000)]
            for bar in rows:
                low, high = decimal(bar["l"], positive=True), decimal(bar["h"], positive=True)
                if not low <= decimal(bar["c"], positive=True) <= high or not low <= decimal(bar["o"], positive=True) <= high:
                    raise ValueError("Invalid native candle prices")
            result.append(dict(start_ms=left, end_ms=left+NINE_MINUTES,
                high=str(max(decimal(r["h"]) for r in rows)), close=str(decimal(rows[-1]["c"]))))
        return result

    def snapshot(self, row, attempts, now):
        # These endpoints are not atomic. Retry the entire read set, never just
        # relabel a truncated history with the later account observation time.
        for readback in range(1, 4):
            row["reconciliation_context"] = {
                "tick_ms": now, "snapshot_started_ms": max(now, int(time.time() * 1000)),
                "readback_attempt": readback, "phase": "orders",
            }
            try:
                snap = self._snapshot_once(row, [dict(a) for a in attempts], now)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, IndexError, StopIteration):
                row["reconciliation_context"]["observed_now_ms"] = max(now, int(time.time() * 1000))
                raise
            if snap["consistent"] or snap["foreign_add"]:
                return snap
        return snap

    def _snapshot_once(self, row, attempts, now):
        context = row["reconciliation_context"]
        asset, resolved, lot, tick = self._market(row["plan"]["instrument"])
        orders = {}
        original_sizes = {}
        for a in attempts:
            if a["kind"] == "cancel":
                continue
            # trailingStop has no client ID in the observed official contract.
            if a["kind"] == "trailing" and not a.get("order_id"):
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
            if order["side"] != ("B" if a["kind"] in {"entry", "add"} else "A") or order.get(
                "reduceOnly"
            ) is not (a["kind"] not in {"entry", "add"}):
                raise ValueError("Order direction or reduce-only contract mismatch")
            kind = (
                "stop"
                if (
                    # A triggered/filled HL stop is read back with isTrigger=false.
                    (order.get("isTrigger") is True or status in {"filled", "triggered"})
                    and order.get("orderType") == "Stop Market"
                    and order.get("reduceOnly") is True
                    and order.get("side") == "A"
                )
                else ("unverified" if a["kind"] == "stop" else a["kind"])
            )
            if a["kind"] == "stop" and kind != "stop":
                raise ValueError("Native SL semantics did not match")
            trailing = {}
            if a["kind"] == "trailing":
                from kis_hl.hyperliquid.trailing import TrailingConditionError, trailing_readback
                if status == "filled" and a.get("retracement_unit") == "percent":
                    if order.get("orderType") != "Trailing Stop Market":
                        raise ValueError("Filled percentage trailing order type mismatch")
                else:
                    try:
                        trailing = trailing_readback(order, retracement=decimal(a["retracement"]),
                            retracement_unit=a.get("retracement_unit", "quote"))
                    except TrailingConditionError as exc:
                        # Preserve independent SL/account evidence without claiming trail coverage.
                        trailing = {"trailing_readback_error": str(exc)}
                if decimal(order["sz"]) < 0 or decimal(order["sz"]) > decimal(a["quantity"]):
                    raise ValueError("Trailing order size mismatch")
                kind = "trailing"
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
                "position_tpsl": (a["kind"] == "stop" and kind == "stop"
                                  and status == "open" and order.get("isPositionTpsl") is True
                                  and decimal(order["sz"]) == 0),
            }
            observed.update(trailing)
            orders[str(query)] = orders[str(order["oid"])] = observed
            if a["kind"] in {"entry", "add"}:
                original_sizes[str(order["oid"])] = decimal(order["origSz"], positive=True)
        context.update(phase="fills", fill_cutoff_ms=max(now, int(time.time() * 1000)))
        fills = fetch_time_pages(
            lambda a, b: self.info.user_fills_by_time(start_time_ms=a, end_time_ms=b),
            row.get("fill_history_start_ms", row["created_ms"]),
            context["fill_cutoff_ms"],
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
            if a["kind"] in {"entry", "add"} and a.get("order_id")
        }
        owned = {str(a.get("order_id")) for a in attempts if a.get("order_id")}
        relevant = {}
        for f in fills:
            if f["coin"] != resolved.coin:
                continue
            key = str(f["tid"])
            if key in relevant and relevant[key] != f:
                raise ValueError("Conflicting duplicate account fill")
            relevant[key] = f
        net = Decimal(0)
        entry = Decimal(0)
        foreign = False
        fill_sizes = {}
        protective_ids = {str(a.get("order_id")) for a in attempts if a["kind"] in {"stop", "trailing"} and a.get("order_id")}
        protective_filled = Decimal(0)
        fixed_stop_filled = Decimal(0)
        fixed_ids = {str(a.get("order_id")) for a in attempts if a["kind"] == "stop"}
        for f in sorted(relevant.values(), key=lambda f: (f["time"], int(f["tid"]))):
            if row["plan"].get("native_trailing_percent") and decimal(f["startPosition"]) != net:
                raise ValueError("Percentage tranche account fill generation is incomplete")
            qty = decimal(f["sz"], positive=True)
            if f["side"] == "B":
                net += qty
                if str(f["oid"]) in entries:
                    entry += qty
                    fill_sizes[str(f["oid"])] = fill_sizes.get(str(f["oid"]), Decimal(0)) + qty
                else:
                    foreign = True
            elif f["side"] == "A":
                net -= qty
                if str(f["oid"]) in protective_ids:
                    protective_filled += qty
                if str(f["oid"]) in fixed_ids:
                    fixed_stop_filled += qty
            else:
                raise ValueError("Unknown execution side")
        order_fills_match = True
        for oid, original in original_sizes.items():
            observed = orders[oid]
            filled = fill_sizes.get(oid, Decimal(0))
            if observed["status"] == "filled":
                order_fills_match &= filled == original
            elif observed["status"] == "open":
                order_fills_match &= filled + decimal(observed["size"]) == original
        context["phase"] = "open_orders"
        opens = self.info.frontend_open_orders(dex=resolved.dex)
        foreign |= any(
            o["coin"] == resolved.coin and str(o["oid"]) not in owned for o in opens
        )
        context["phase"] = "exposure"
        state = self.info.clearinghouse_state(dex=resolved.dex)
        context["exposure_observed_ms"] = max(now, int(time.time() * 1000))
        pos = next(
            (
                x["position"]
                for x in state["assetPositions"]
                if x["position"]["coin"] == resolved.coin
            ),
            None,
        )
        size = decimal(pos["szi"]) if pos else Decimal(0)
        # Zero is a position-level sentinel only for an exact verified live SL.
        # Preserve wire size separately; coverage comes from reconciled account size.
        for observed in orders.values():
            observed["coverage_size"] = (str(size) if observed["position_tpsl"]
                and size > 0 and net == size and not foreign else observed["size"])
        context.update(history_net=str(net), observed_size=str(size), foreign_evidence=foreign,
                       mismatch="exposure" if net != size else "order_fills" if not order_fills_match else None,
                       phase="quote")
        try:
            bid, ask, timestamp = self._quote(resolved)
        except (ValueError, KeyError, IndexError, RuntimeError, OSError):
            bid, ask, timestamp = Decimal(0), Decimal(0), 0
        context.update(phase="complete", observed_now_ms=max(now, int(time.time() * 1000)))
        # HL reduce-only exits remain available outside the underlying entry session.
        return {
            "size": str(size),
            "entry_price": str(pos["entryPx"]) if pos and size else "0",
            "entry_filled": str(entry),
            "protective_filled": str(protective_filled),
            "fixed_stop_filled": str(fixed_stop_filled),
            "fills_by_attempt": {a["id"]: str(fill_sizes.get(str(a.get("order_id")), 0))
                                 for a in attempts if a["kind"] in {"entry", "add"}},
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
            "consistent": net == size and order_fills_match,
            "reconciliation_context": dict(context),
            "price_step": str(max(tick, Decimal(10) ** (bid.adjusted() - 4))),
            "trailing_price_step": str(tick),
            "quantity_step": str(lot),
            "observed_now_ms": context["observed_now_ms"],
        }

    def submit(self, row, a):
        asset = instrument(row["plan"]["instrument"])
        from kis_hl.managed_execution import entry_permit

        if a['kind'] == 'entry' and row['plan'].get('percentage_entry_authorization'):
            if row['scope'] != self.scope or row['mode'] != 'live':
                raise ValueError('NEW percentage transport requires the exact live account scope')
            from kis_hl.percentage_entry import check_send
            check_send(row, a, int(time.time()*1000))
        if a["kind"] == "trailing":
            result = self.trading.place_trailing_stop_order(
                symbol=asset.symbol, side="sell", size=decimal(a["quantity"]),
                retracement=decimal(a["retracement"]), dry_run=False,
                retracement_unit=a.get("retracement_unit", "quote"),
                expires_after_ms=a["created_ms"] + row["plan"]["max_quote_age_ms"],
            )
            return {"status": result.status,
                    "order_id": extract_hyperliquid_order_id(result.response) if result.status == "submitted" else None}
        with entry_permit(self.scope, asset.id, a["id"]):
            entry_market = a["kind"] == "entry" and a.get("order_type") == "market"
            result = self.trading.place_order(
                symbol=asset.symbol,
                side="buy" if a["kind"] in {"entry", "add"} else "sell",
                order_type="stop-market" if a["kind"] == "stop" else "market" if entry_market else "limit",
                size=decimal(a["quantity"]),
                price=decimal(a["price"]),
                trigger_price=(
                    decimal(a["trigger_price"]) if a["kind"] == "stop" else None
                ),
                reduce_only=a["kind"] not in {"entry", "add"},
                slippage=Decimal("0.005") if entry_market else decimal(row["plan"]["slippage"]),
                tif="Ioc" if a["kind"] == "exit" else "Gtc",
                cloid=a["id"],
                dry_run=False,
                expires_after_ms=min(a["created_ms"] + row["plan"]["max_quote_age_ms"],
                                     a.get("expires_ms", a["created_ms"] + row["plan"]["max_quote_age_ms"])),
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

    def execution_session_open(self, instrument_id, now):
        """Clock-only KIS session check used when account reads are unavailable."""
        return self._session(self._asset(instrument_id), now)

    def _session(self, asset, now):
        from kis_hl.trading_hours import trading_session_decision_for_symbol

        key = "xyz:KR200" if asset.market == "domestic" else "xyz:SP500"
        return trading_session_decision_for_symbol(
            key, now=datetime.fromtimestamp(now / 1000, timezone.utc)
        ).allowed

    def _same_execution_session(self, asset, previous, now):
        """Whether an observation gap stayed inside one regular cash session."""
        zone = ZoneInfo("Asia/Seoul" if asset.market == "domestic" else "America/New_York")
        return (
            datetime.fromtimestamp(previous / 1000, zone).date()
            == datetime.fromtimestamp(now / 1000, zone).date()
            and self._session(asset, previous)
            and self._session(asset, now)
        )

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
                # Holiday or pre-first-trade: the venue cannot execute local protection.
                raise KisSessionClosed("No current-session execution date")
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
        local = datetime.fromtimestamp(now / 1000, zone)
        today = local.date()
        # After the KRX regular close (15:30 KST) the day's regular-session bar is final.
        closed_today = asset.market == "domestic" and local.time() >= KRX_BAR_FINAL
        end = today if closed_today else today - timedelta(days=1)
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
            if day > end:
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
            "baseline_start_ms": now,
            "observed_now_ms": int(time.time() * 1000),
        }

    def snapshot(self, row, attempts, now):
        asset = self._asset(row["plan"]["instrument"])
        history = self._history(
            asset, row.get("baseline_start_ms", row["created_ms"]), now
        )
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
        session_open = self._session(asset, now)
        session_unavailable_reason = None
        previous = row.get("last_observed_ms", now)
        same_session = self._same_execution_session(asset, previous, now)
        try:
            price, ask, stamp = self._quote(asset)
        except KisSessionClosed:
            session_unavailable_reason = (
                "No current-session execution date; execution availability unverified "
                "(holiday, suspended instrument, or delayed data); local protection unavailable"
                if session_open else "Execution session closed; local protection unavailable"
            )
            price, ask, stamp, session_open = Decimal(0), Decimal(0), 0, False
        except (ValueError, KeyError, IndexError, RuntimeError, OSError):
            price, ask, stamp = Decimal(0), Decimal(0), 0
        observed_now = int(time.time() * 1000)
        session_gap_ms = regular_cash_session_elapsed_ms(
            previous, observed_now,
            session_group=SESSION_KRX_CASH if asset.market == "domestic" else SESSION_US_CASH,
        )
        return {
            "size": str(size),
            "entry_price": entry_price,
            "entry_filled": str(entry),
            "price": str(price),
            "time_ms": stamp,
            "sellable": sellable,
            "session_open": session_open,
            "same_execution_session": same_session,
            "regular_session_gap_ms": session_gap_ms,
            "session_unavailable_reason": session_unavailable_reason,
            "foreign_add": foreign,
            "consistent": net == size,
            "orders": orders,
            "quantity_step": "1",
            "price_step": row["plan"].get("verified_price_step", "0"),
            "observed_now_ms": observed_now,
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
