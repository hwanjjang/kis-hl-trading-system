"""Deterministic evidence tools for strategy skills; no network or order side effects."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json

from kis_hl.instruments import instrument
from kis_hl.journal_sync import decimal, encode
from kis_hl.risk import (
    calculate_atr_10d, calculate_operating_capital, calculate_risk_units,
    calculate_30w_ema_status,
    n_multiplier_for_asset_class,
)
from kis_hl.signals import evaluate_btcusdc_futures_3h_breakout

DAY_MS = 86_400_000


def initial_stop(request):
    """Derive a proposed ATR stop; the caller must use execution-instrument units."""
    entry, atr = decimal(request.get("entry"), positive=True), decimal(request.get("atr"), positive=True)
    multiple = (decimal(request["multiple"], positive=True) if "multiple" in request
                else n_multiplier_for_asset_class(request.get("asset_class")))
    side = request.get("side", "long")
    if side not in {"long", "short"}:
        raise ValueError("Side must be long or short")
    distance = atr * multiple
    stop = entry - distance if side == "long" else entry + distance
    if stop <= 0:
        raise ValueError("Initial stop must be positive")
    return dict(stop=str(stop), distance=str(distance), multiple=str(multiple), side=side,
                order_authorized=False)


def _integer(value, name, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer")
    return value


def _fresh(record, now_ms):
    stamp = _integer(record.get("asof_ms"), "asof_ms")
    age = _integer(record.get("max_age_ms"), "max_age_ms", positive=True)
    if not 0 <= now_ms - stamp <= age:
        raise ValueError("Snapshot is stale or from the future")


def _bars(rows, now_ms, *, count, name, max_age_ms, duration=None):
    if not isinstance(rows, list) or len(rows) < count:
        raise ValueError(f"{name} requires {count} closed bars")
    result = []
    for raw in rows:
        start = _integer(raw.get("start_ms"), "bar start_ms")
        end = _integer(raw.get("end_ms"), "bar end_ms", positive=True)
        if raw.get("complete") is not True or not start < end <= now_ms:
            raise ValueError(f"{name} contains an incomplete or future bar")
        if duration is not None and end - start != duration:
            raise ValueError(f"{name} has an unexpected timeframe")
        prices = {k: decimal(raw.get(k), positive=True) for k in ("open", "high", "low", "close")}
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
            raise ValueError(f"{name} has inconsistent OHLC")
        if result and start < result[-1]["end_ms"]:
            raise ValueError(f"{name} has duplicate, overlapping or unordered bars")
        result.append(dict(start_ms=start, end_ms=end, **prices,
                           date=datetime.fromtimestamp(start/1000, timezone.utc).date().isoformat()))
    age = _integer(max_age_ms, f"{name} maximum age", positive=True)
    if now_ms - result[-1]["end_ms"] > age:
        raise ValueError(f"{name} is stale")
    return result


def _position(record, snapshot, now_ms):
    if not isinstance(record, dict) or not record.get("id") or not record.get("scope"):
        raise ValueError("Add/management evaluation requires an identified account position")
    _fresh(record, now_ms)
    if record.get("instrument") != snapshot["instrument"]:
        raise ValueError("Position and price instrument differ; conversion is not inferred")
    decimal(record.get("quantity"), positive=True)
    decimal(record.get("stop"), positive=True)
    opened = _integer(record.get("opened_ms"), "opened_ms")
    if opened > now_ms:
        raise ValueError("Position opening time is in the future")
    return record


def evaluate_setup(request, *, now_ms):
    """Return numeric setup evidence, not a trade decision or authorization.

    Missing/stale evidence yields unavailable. Qualitative confluence and actual
    execution readiness remain the skill's and existing supervisor's responsibilities.
    """
    _integer(now_ms, "now_ms")
    snapshot = request.get("snapshot", {})
    result = dict(schema_version=1, snapshot_id=snapshot.get("id"),
                  input_sha256=hashlib.sha256(encode(request).encode()).hexdigest(),
                  setup=request.get("setup"), status="unavailable", predicate_passed=False,
                  facts={}, reasons=[], order_authorized=False)
    try:
        kind = request.get("setup")
        if kind not in {"breakout", "pullback", "rebreakout", "btc_3h", "management"}:
            raise ValueError("Unknown setup")
        for key in ("id", "instrument", "source", "currency"):
            if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
                raise ValueError(f"Snapshot {key} required")
        if snapshot["instrument"] != "hl:UBTC/USDC":
            asset = instrument(snapshot["instrument"])
            if snapshot["currency"] != asset.currency:
                raise ValueError("Snapshot currency differs from instrument")
        elif snapshot["currency"] != "USDC":
            raise ValueError("BTC spot evidence requires USDC")
        _fresh(snapshot, now_ms)
        result["source"] = {k: snapshot[k] for k in ("instrument", "source", "currency", "asof_ms")}
        if kind == "management":
            position = _position(request.get("position"), snapshot, now_ms)
            price, stop = decimal(snapshot.get("price"), positive=True), decimal(position["stop"])
            result.update(status="available", predicate_passed=price <= stop,
                          facts={"price": str(price), "effective_stop": str(stop), "stop_crossed": price <= stop})
            return result

        duration = _integer(snapshot.get("timeframe_ms"), "timeframe_ms", positive=True)
        candles = _bars(snapshot.get("candles"), now_ms, count=2, name="confirmation candles",
                        max_age_ms=snapshot["max_age_ms"], duration=duration)
        # These tools consume complete, contiguous confirmation bars; gaps are not signals.
        if any(b["start_ms"] != a["end_ms"] for a, b in zip(candles, candles[1:])):
            raise ValueError("Confirmation candles have a gap")
        facts = result["facts"]
        if kind == "btc_3h":
            if duration != 10_800_000 or snapshot["instrument"] != "hl:UBTC/USDC":
                raise ValueError("BTC exception requires explicit spot 3h evidence")
        else:
            indicators = indicator_facts(snapshot, now_ms=now_ms)
            if indicators["unavailable"]:
                raise ValueError("; ".join(indicators["unavailable"].values()))
            facts.update({key: indicators[key] for key in
                          ("atr_10d", "ema_30w", "weekly_close", "above_30w_ema")})
        current, previous = candles[-1], candles[-2]
        position = None
        if kind in {"pullback", "rebreakout"}:
            position = _position(request.get("position"), snapshot, now_ms)
            candles = [c for c in candles if c["start_ms"] >= position["opened_ms"]]
            if len(candles) < 2:
                raise ValueError("At least two complete post-entry bars required")
            current, previous = candles[-1], candles[-2]
            facts["above_effective_stop"] = current["close"] > decimal(position["stop"])
        if kind == "pullback":
            reference = decimal(request.get("reference"), positive=True)
            tolerance = decimal(request.get("tolerance"))
            if tolerance < 0:
                raise ValueError("Pullback tolerance must be non-negative")
            touched = previous["low"] <= reference + tolerance and previous["high"] >= reference - tolerance
            resumed = current["close"] > max(previous["high"], reference, current["open"])
            facts.update(reference=str(reference), touched_reference=touched, closed_rebound=resumed)
            passed = touched and resumed
        else:
            lookback = _integer(request.get("lookback", 1), "lookback", positive=True)
            if len(candles) < lookback+1:
                raise ValueError("Insufficient post-entry/lookback confirmation bars")
            if kind == "btc_3h":
                breakout = evaluate_btcusdc_futures_3h_breakout(candles, lookback_candles=lookback)
                level, passed = breakout.breakout_level, breakout.should_enter
            else:
                level = max(c["high"] for c in candles[-lookback-1:-1])
                passed = current["close"] > level
            facts.update(breakout_level=str(level), closed_above_level=passed)
        facts["close"] = str(current["close"])
        if kind != "btc_3h":
            passed = passed and facts["above_30w_ema"]
        if position:
            passed = passed and facts["above_effective_stop"]
        result.update(status="available", predicate_passed=bool(passed))
        if not passed:
            result["reasons"].append("Numeric setup conditions did not pass")
    except (ValueError, KeyError, TypeError) as exc:
        result["reasons"].append(str(exc))
    return result


def size_position(request, *, now_ms):
    """Account-local advisory sizing; actual funds/metadata remain execution preflight."""
    _fresh(request, now_ms)
    asset = instrument(request["instrument"])
    venue = request["venue"]
    if venue not in {"hyperliquid", "kis"} or asset.venue != venue or "index" in asset.market:
        raise ValueError("Explicit execution instrument and venue must match")
    if not isinstance(request.get("scope"), str) or not request["scope"].strip():
        raise ValueError("Account scope required")
    if request.get("currency") != asset.currency:
        raise ValueError("Account equity must have an explicit execution-currency valuation")
    reconciliation = None
    if venue == "hyperliquid":
        from kis_hl.account_capital import reconcile_capital
        reconciliation = reconcile_capital(request.get("capital_evidence"), scope=request["scope"],
                                            now_ms=now_ms, max_age_ms=request["max_age_ms"])
        equity = decimal(reconciliation["total_balance"], positive=True)
    else:
        equity = decimal(request.get("equity"), positive=True)
    capital = calculate_operating_capital(equity, multiple=Decimal(10 if venue == "hyperliquid" else 1))
    sizing = request.get("sizing", "units")
    if sizing not in {"units", "btc_fixed_80"}:
        raise ValueError("Unknown sizing policy")
    result = calculate_risk_units(capital=capital, units=request["units"] if sizing == "units" else "1", **{k: request[k] for k in
        ("entry", "stop", "quantity_step", "minimum_quantity", "minimum_notional")},
        side=request.get("side", "long"))
    if sizing == "btc_fixed_80":
        if asset.id != "hl:BTC" or request.get("side", "long") != "long" or "units" in request:
            raise ValueError("BTC fixed-notional exception is long BTC only and takes no unit count")
        entry, step = decimal(request["entry"]), decimal(request["quantity_step"])
        quantity = (Decimal(80)/entry/step).to_integral_value(rounding=ROUND_DOWN)*step
        notional, risk = quantity*entry, quantity*result["stop_distance"]
        result.update(quantity=quantity, notional=notional, risk=risk,
                      risk_budget=None, units=None,
                      below_minimum=quantity <= 0 or quantity < decimal(request["minimum_quantity"])
                      or notional < decimal(request["minimum_notional"]))
    result.update(operating_capital=capital, equity=equity, venue=venue,
                  scope=request["scope"], instrument=asset.id, currency=asset.currency,
                  asof_ms=request["asof_ms"], fixed_stop=request["stop"],
                  risk_pct_equity=result["risk"]/equity*100,
                  risk_pct_operating_capital=result["risk"]/capital*100,
                  sizing=sizing, order_authorized=False)
    if reconciliation is not None:
        result["capital_reconciliation"] = reconciliation
    return json.loads(encode(result))


def indicator_facts(snapshot, *, now_ms):
    """Inspect ATR and weekly trend independently for an explicitly named price basis."""
    result = dict(snapshot_id=snapshot.get("id"), source={k: snapshot.get(k) for k in
                  ("instrument", "source", "currency", "asof_ms")},
                  atr_10d=None, ema_30w=None, weekly_close=None, above_30w_ema=None,
                  unavailable={})
    try:
        _fresh(snapshot, now_ms)
        for key in ("id", "instrument", "source", "currency"):
            if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
                raise ValueError(f"Snapshot {key} required")
        asset = instrument(snapshot["instrument"])
        if asset.currency != snapshot["currency"]:
            raise ValueError("Snapshot currency differs from instrument")
    except (ValueError, KeyError, TypeError) as exc:
        result["unavailable"] = {"atr_10d": str(exc), "ema_30w": str(exc)}
        return result
    ages = snapshot.get("history_max_age_ms", {})
    try:
        bars = _bars(snapshot.get("daily_bars"), now_ms, count=11, name="daily history",
                     max_age_ms=ages.get("daily"), duration=DAY_MS)
        atr = calculate_atr_10d(bars)
        if atr <= 0:
            raise ValueError("ATR must be positive")
        result["atr_10d"] = str(atr)
    except (ValueError, KeyError, TypeError) as exc:
        result["unavailable"]["atr_10d"] = str(exc)
    try:
        bars = _bars(snapshot.get("weekly_bars"), now_ms, count=30, name="weekly history",
                     max_age_ms=ages.get("weekly"), duration=7*DAY_MS)
        if any(b["start_ms"] != a["end_ms"] for a, b in zip(bars, bars[1:])):
            raise ValueError("Weekly history has a gap")
        ema = calculate_30w_ema_status(bars)
        result.update(ema_30w=str(ema.ema), weekly_close=str(ema.latest_close), above_30w_ema=ema.above)
    except (ValueError, KeyError, TypeError) as exc:
        result["unavailable"]["ema_30w"] = str(exc)
    return result


def ingest_decision(signals, record, *, now_ms):
    """Retain skill rationale plus recomputed evidence in the existing immutable registry."""
    action = record.get("action")
    if action not in {"enter", "add", "hold", "reduce", "exit", "no_trade"}:
        raise ValueError("Explicit strategy decision action required")
    evidence = evaluate_setup(record["setup_input"], now_ms=now_ms)
    signal_instrument = record.get("signal_instrument")
    source_instrument = record["setup_input"]["snapshot"].get("instrument")
    btc = record["setup_input"].get("setup") == "btc_3h"
    if (not btc and source_instrument != signal_instrument) or (btc and (
            signal_instrument != "hl:BTC" or record.get("execution_instruments") != ["hl:BTC"])):
        raise ValueError("Decision and evidence instruments differ")
    expected_action = {"breakout": "enter", "btc_3h": "enter", "pullback": "add", "rebreakout": "add"}
    if action in {"enter", "add"}:
        if action != expected_action.get(record["setup_input"].get("setup")):
            raise ValueError("Setup does not match the decision action")
        if not evidence["predicate_passed"]:
            raise ValueError("Entry/add predicate did not pass")
        factors = record.get("confluence")
        if not isinstance(factors, list) or len({f.strip() for f in factors if isinstance(f, str) and f.strip()}) < 2:
            raise ValueError("Record at least two distinct confluence reasons")
        if not isinstance(record.get("management"), str) or not record["management"].strip():
            raise ValueError("Management rationale required")
    if action not in {"hold", "no_trade"} and evidence["status"] != "available":
        raise ValueError("Actionable decision requires available evidence")
    return signals.ingest({**record, "evidence": evidence}, now_ms=now_ms)
