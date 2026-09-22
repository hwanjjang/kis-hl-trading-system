"""Trailing action/readback observed in the official app; see API skill references."""
from decimal import Decimal, InvalidOperation
import re


def positive(value):
    try:
        value = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Trailing values must be finite positive decimals") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("Trailing values must be finite positive decimals")
    return value


def wire_decimal(value):
    return format(value.normalize(), "f")


def retracement_wire(value, unit):
    value = positive(value)
    if unit == "quote":
        return {"px": wire_decimal(value)}
    if unit != "percent" or value >= 100 or value % Decimal("0.0001"):
        raise ValueError("Percent retracement must be below 100 with at most four decimals")
    return {"pct": f"{value:.4f}%"}


def send_trailing_action(exchange, action, nonce, expires_after):
    # Preserve insertion order: msgpack field order is part of the signed hash.
    from hyperliquid.utils.signing import sign_l1_action
    from hyperliquid.utils.constants import MAINNET_API_URL
    signature = sign_l1_action(exchange.wallet, action, exchange.vault_address,
                               nonce, expires_after, exchange.base_url == MAINNET_API_URL)
    return exchange.post("/exchange", {"action": action, "nonce": nonce,
        "signature": signature, "vaultAddress": exchange.vault_address,
        "expiresAfter": expires_after})


def trailing_readback(order, *, retracement):
    """Verify managed long protective quote-distance semantics, never infer ownership."""
    if (order.get("orderType") != "Trailing Stop Market" or order.get("isTrigger") is not True
            or order.get("reduceOnly") is not True or order.get("side") != "A"):
        raise ValueError("Native trailing order semantics did not match")
    condition = order.get("triggerCondition")
    if not isinstance(condition, str):
        raise ValueError("Missing native trailing condition")
    fields = {}
    for part in condition.split(","):
        match = re.fullmatch(r"\s*(retracement|best)\s+(\S+)\s*", part, re.IGNORECASE)
        if not match or match[1].lower() in fields:
            raise ValueError("Unverified native trailing condition format")
        fields[match[1].lower()] = match[2]
    if set(fields) != {"retracement", "best"}:
        raise ValueError("Incomplete native trailing condition")
    distance = positive(fields["retracement"])
    if distance != positive(retracement):
        raise ValueError("Native trailing retracement mismatch")
    result = {"retracement": wire_decimal(distance), "retracement_unit": "quote",
              "active": fields["best"].lower() != "waiting"}
    if result["active"]:
        best = positive(fields["best"])
        threshold = best - distance
        if threshold <= 0:
            raise ValueError("Invalid native trailing threshold")
        result.update(best_price=wire_decimal(best), trigger_price=wire_decimal(threshold))
    return result
