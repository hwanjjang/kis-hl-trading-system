"""Fail-closed account-total capital reconciliation, separate from buying power."""

import hashlib

from kis_hl.journal_sync import decimal, encode


def capture_capital(info, *, scope, now_ms, max_age_ms):
    """Read the effective account only; callers recheck elapsed time after capture."""
    return {"scope": scope, "currency": "USDC", "asof_ms": now_ms, "max_age_ms": max_age_ms,
            "account_mode": info.user_abstraction(), "spot": info.spot_clearinghouse_state(),
            "source": "Hyperliquid account readback"}


def reconcile_capital(evidence, *, scope, now_ms, max_age_ms):
    if not isinstance(evidence, dict):
        raise ValueError("Reconciled account-total evidence required; segment equity is not capital")
    stamp = evidence.get("asof_ms")
    age = evidence.get("max_age_ms")
    if (type(stamp) is not int or type(age) is not int or age <= 0
            or not 0 <= now_ms - stamp <= min(age, max_age_ms)):
        raise ValueError("Account-total evidence is stale or invalid")
    if evidence.get("scope") != scope or evidence.get("currency") != "USDC":
        raise ValueError("Account-total scope/currency mismatch")
    if evidence.get("account_mode") != "unifiedAccount":
        raise ValueError("Account-total reconciliation requires verified unifiedAccount mode")
    spot = evidence.get("spot")
    if not isinstance(spot, dict):
        raise ValueError("Complete unified spot state required")
    if spot.get("portfolioMarginEnabled", False) is not False:
        raise ValueError("Contradictory or unknown portfolio-margin evidence")
    escrows = spot.get("evmEscrows", [])
    if not isinstance(escrows, list):
        raise ValueError("Unknown escrow collateral")
    for item in escrows:
        if (not isinstance(item, dict) or type(item.get("token")) is not int
                or item["token"] < 0 or not isinstance(item.get("coin"), str)
                or not item["coin"] or decimal(item.get("total")) != 0):
            raise ValueError("Escrow collateral requires supported account-total reconciliation")
    balances = spot.get("balances")
    if not isinstance(balances, list) or not balances:
        raise ValueError("Complete unified spot balances required")
    seen, total = set(), decimal("0")
    for item in balances:
        if not isinstance(item, dict):
            raise ValueError("Unknown collateral balance")
        for field in ("borrowed", "supplied"):
            if decimal(item.get(field, "0")) != 0:
                raise ValueError("Borrowed/supplied balance requires supported account-total reconciliation")
        token = item.get("token")
        if type(token) is not int or token < 0 or token in seen:
            raise ValueError("Overlapping or unknown collateral identity")
        seen.add(token)
        amount = decimal(item.get("total"))
        if amount < 0:
            raise ValueError("Negative collateral requires supported liability reconciliation")
        if token == 0 and item.get("coin") == "USDC":
            total += amount
        elif amount != 0:
            raise ValueError("Non-USDC balance requires explicit supported account-total valuation")
    if total <= 0:
        raise ValueError("Positive reconciled account-total balance required")
    return {"total_balance": str(total), "scope": scope, "currency": "USDC",
            "account_mode": "unifiedAccount", "asof_ms": stamp,
            "basis": "Unified spot balances; overlapping perp/dex values excluded",
            "source_sha256": hashlib.sha256(encode(evidence).encode()).hexdigest()}
