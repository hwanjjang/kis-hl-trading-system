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
    balances = evidence.get("spot", {}).get("balances")
    if not isinstance(balances, list) or not balances:
        raise ValueError("Complete unified spot balances required")
    seen, total = set(), decimal("0")
    for item in balances:
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
