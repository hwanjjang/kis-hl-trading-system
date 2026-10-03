"""Directly authorized, once-only UTC nine-minute additions (not weekly signals)."""
from decimal import Decimal, ROUND_DOWN
from kis_hl.journal_sync import decimal

NINE_MINUTES = 540_000


class AddConditionPending(ValueError):
    """No completed qualifying bar yet; no submission attempt may be created."""


def check_intraday_authority(owner, p, now):
    a = p["intraday_authorization"]
    original = owner["plan"]
    if (a.get("manual") is not True or a.get("scope") != owner["scope"]
            or a.get("mode") != owner["mode"] or a.get("position_id") != owner["id"]
            or p.get("action") != "add" or p.get("position_id") != owner["id"]
            or p.get("signal_id") or p.get("grant_id")
            or p.get("instrument") != original["instrument"]
            or not p["instrument"].startswith("hl:")
            or owner["state"] != "PROTECTED" or owner.get("exit_requested_ms")
            or owner.get("cancel_entry") or owner.get("native_trailing_intervention")
            or type(a.get("authorized_ms")) is not int or not 0 <= a["authorized_ms"] <= now
            or p["expires_ms"] != a["expires_ms"] or now >= a["expires_ms"]
            or decimal(p["units"], positive=True) != decimal(a["units"], positive=True)
            or not original.get("native_trailing_percent") or original.get("local_trailing_backup") is not False):
        raise ValueError("Explicit intraday add authority or protected owner changed")
    for field in ("atr", "atr_multiple", "local_atr_multiple", "native_atr_multiple",
                  "native_trailing_percent", "trailing_provider", "local_trailing_backup",
                  "fixed_stop_price", "protection_grace_ms", "max_exit_attempts",
                  "exit_deadline_ms", "exit_reprice_ms", "slippage", "allow_local_sl", "max_quote_age_ms"):
        if p.get(field) != original.get(field):
            raise ValueError("Intraday add must preserve protection policy")
    if (decimal(owner["observed_size"]) != decimal(p["expected_size"])
            or decimal(owner["entry_filled"]) != decimal(p["expected_entry_filled"])):
        raise ValueError("Intraday add exposure changed")


def confirm_breakout(bars, authorized_ms, now, max_age_ms):
    if len(bars) != 2:
        raise AddConditionPending("Waiting for two complete adjacent UTC nine-minute bars")
    previous, current = bars
    for bar in bars:
        start, end = bar.get("start_ms"), bar.get("end_ms")
        if (type(start) is not int or type(end) is not int or start % NINE_MINUTES
                or end-start != NINE_MINUTES or end > now):
            raise AddConditionPending("Unfinished or unaligned UTC nine-minute bars")
        if decimal(bar["close"], positive=True) > decimal(bar["high"], positive=True):
            raise ValueError("Invalid completed bar prices")
    if (previous["end_ms"] != current["start_ms"] or current["end_ms"] <= authorized_ms
            or not 0 <= now-current["end_ms"] <= max_age_ms
            or decimal(current["close"]) <= decimal(previous["high"])):
        raise AddConditionPending("Waiting for new adjacent completed high breakout")
    return current


def prepare_intraday_add(gateway, store, owner, tranche, now):
    from kis_hl.conditional_add import preflight_add, size_add
    from kis_hl.managed_execution import validate_plan
    p = tranche["plan"]
    check_intraday_authority(owner, p, now)
    bars = gateway.completed_nine_minute_bars(p["instrument"], now)
    bar = confirm_breakout(bars, p["intraday_authorization"]["authorized_ms"], now, p["max_quote_age_ms"])
    pre = gateway.preflight(p, now)
    now = int(pre.get("observed_now_ms", now))
    check_intraday_authority(owner, p, now)
    confirm_breakout(bars, p["intraday_authorization"]["authorized_ms"], now, p["max_quote_age_ms"])
    # Hard exchange limit, rounded inward for tick AND five significant figures.
    cap = decimal(bar["close"]) * Decimal("1.003")
    tick = max(decimal(pre["price_step"], positive=True), min(Decimal(1), Decimal(10)**(cap.adjusted()-4)))
    price = (cap/tick).to_integral_value(rounding=ROUND_DOWN)*tick
    p = dict(p, limit_price=str(price), capital_evidence=pre["capital_evidence"],
             quantity_step=pre["quantity_step"], condition_bar_end_ms=bar["end_ms"],
             condition_bars=bars, hard_price_cap=str(cap), entry_route="limit")
    sizing = size_add(p, owner["scope"], p["capital_evidence"], now, quantity_step=p["quantity_step"])
    if sizing["below_minimum"]:
        raise ValueError("Intraday add below exchange minimum")
    p = validate_plan(dict(p, quantity=sizing["quantity"]), now)
    candidate = dict(tranche, plan=p)
    sizing, now = preflight_add(gateway, store, owner, candidate, now)
    # Persist the exact evidence and cap before creating a signed attempt.
    tranche["plan"] = p
    store.save_tranche(tranche)
    return sizing, now
