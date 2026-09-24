"""Bounded add admission on an existing owner; no scheduling or order transport."""

from kis_hl.journal_sync import decimal
from kis_hl.strategy_tools import evaluate_setup, size_position


def size_add(plan, scope, evidence, now, *, quantity_step="0.00000001"):
    return size_position(dict(venue="hyperliquid", scope=scope, currency="USDC",
        instrument=plan["instrument"], capital_evidence=evidence,
        asof_ms=evidence["asof_ms"], max_age_ms=plan["max_quote_age_ms"],
        entry=plan["limit_price"], stop=plan["fixed_stop_price"], units=plan["units"],
        quantity_step=quantity_step, minimum_quantity=quantity_step, minimum_notional="10"), now_ms=now)


def validate_add(plan, owner, signal, now):
    required = {"units", "quantity_step", "fixed_stop_price", "capital_evidence",
                "expected_size", "expected_entry_filled", "condition_snapshot_id", "condition_bar_end_ms"}
    if not required <= plan.keys() or not isinstance(plan["capital_evidence"], dict):
        raise ValueError("Add plan is missing bounded sizing/condition evidence")
    original = owner["plan"]
    if (plan.get("action") != "add" or signal.get("action") != "add"
            or not plan["instrument"].startswith("hl:")
            or plan.get("position_id") != owner["id"]
            or plan["instrument"] != original["instrument"]):
        raise ValueError("Add requires the identified Hyperliquid position owner")
    if owner["state"] != "PROTECTED" or owner["exit_requested_ms"] or owner["cancel_entry"]:
        raise ValueError("Add requires a protected owner without an exit/cancel request")
    for key in ("atr", "atr_multiple", "local_atr_multiple", "native_atr_multiple",
                "trailing_provider", "local_trailing_backup", "protection_grace_ms",
                "max_exit_attempts", "exit_deadline_ms", "exit_reprice_ms", "slippage",
                "allow_local_sl", "max_quote_age_ms"):
        if plan.get(key) != original.get(key):
            raise ValueError("Add must preserve frozen ATR and independent protection parameters")
    fixed = decimal(plan.get("fixed_stop_price"), positive=True)
    original_fixed = decimal(original.get("fixed_stop_price",
                             decimal(owner["trail"]["entry"]) - decimal(original["stop_distance"])))
    if fixed != original_fixed:
        raise ValueError("Add fixed stop must match the confirmed owner stop")
    if original.get("trailing_provider") == "native" and not original.get("local_trailing_backup"):
        raise ValueError("migration-required: add requires preserved full-position local trailing backup")
    for expected, observed in (("expected_size", "observed_size"), ("expected_entry_filled", "entry_filled")):
        if decimal(plan.get(expected), positive=True) != decimal(owner[observed], positive=True):
            raise ValueError("Add authority exposure changed")
    setup = signal.get("setup_input", {})
    snapshot = setup.get("snapshot", {})
    position = setup.get("position", {})
    if (setup.get("setup") not in {"pullback", "rebreakout"}
            or snapshot.get("instrument") != plan["signal_instrument"]
            or position.get("id") != owner["id"] or position.get("scope") != owner["scope"]
            or position.get("instrument") != plan["instrument"]
            or position.get("opened_ms") != owner["first_fill_ms"]
            or decimal(position.get("quantity")) != decimal(plan["expected_size"])
            or decimal(position.get("stop")) != fixed
            or snapshot.get("id") != plan.get("condition_snapshot_id")
            or type(plan.get("condition_bar_end_ms")) is not int
            or not snapshot.get("candles")
            or snapshot["candles"][-1].get("end_ms") != plan["condition_bar_end_ms"]):
        raise ValueError("Add requires identified completed-bar and position evidence")
    if not evaluate_setup(setup, now_ms=now)["predicate_passed"]:
        raise ValueError("Add completed-bar confirmation is unfinished, stale or failed")
    result = size_add(plan, owner["scope"], plan.get("capital_evidence", {}), now,
                      quantity_step=plan["quantity_step"])
    if result["below_minimum"] or decimal(result["quantity"]) != decimal(plan["quantity"]):
        raise ValueError("Add quantity differs from authorized units and fixed-stop risk")
    return result


def preflight_add(gateway, store, owner, tranche, now):
    """Re-read exposure, source identity, total balance and independent funds before send."""
    from kis_hl.managed_execution import validate_plan
    from kis_hl.strategy_signals import Signals
    p = tranche["plan"]
    pre = gateway.preflight(p, now)
    now = int(pre.get("observed_now_ms", now))
    validate_plan(p, now)
    Signals(store).check_authority({**owner, "plan": p}, now_ms=now)
    if (not pre["eligible"] or not pre["session_open"]
            or not 0 <= now - int(pre["time_ms"]) <= p["max_quote_age_ms"]
            or decimal(pre["position"]) != decimal(p["expected_size"])):
        raise ValueError("Fresh add exposure/eligibility/quote changed")
    owned = {str(a.get("order_id")) for a in store.attempts(owner["id"]) if a.get("order_id")}
    if any(str(o["oid"]) not in owned for o in pre["open_orders"]):
        raise ValueError("migration-required: external protection/order needs explicit supported migration")
    evidence = pre.get("capital_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("Fresh account-total evidence required before add")
    result = size_add(p, owner["scope"], evidence, now, quantity_step=pre["quantity_step"])
    if result["below_minimum"] or decimal(result["quantity"]) != decimal(p["quantity"]):
        raise ValueError("Fresh account-total sizing changed; new authority required")
    price, size = decimal(p["limit_price"]), decimal(p["quantity"])
    if size % decimal(pre["quantity_step"], positive=True) or price % decimal(pre["price_step"], positive=True):
        raise ValueError("Add violates current lot/tick")
    notional = price * size
    if notional > decimal(pre["available_notional"]):
        raise ValueError("Insufficient available funds for add")
    for field in ("portfolio_notional", "correlated_notional"):
        if notional + decimal(pre[field]) > decimal(p["max_"+field]):
            raise ValueError("Add exceeds explicit notional limit")
    bid, ask = decimal(pre["price"], positive=True), decimal(pre["ask"], positive=True)
    if (ask < bid or (ask-bid)/bid*10000 > decimal(p["max_spread_bps"])
            or abs(price-ask)/ask*10000 > decimal(p["max_entry_deviation_bps"])):
        raise ValueError("Add price/spread limit failed")
    # Frozen daily ATR belongs to the owner, not a newly calculated entry ATR.
    if pre["atr_source"]["instrument"] != p["instrument"]:
        raise ValueError("Add source instrument mismatch")
    return result, now
