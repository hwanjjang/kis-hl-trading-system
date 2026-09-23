"""Trailing action/readback observed in the official app; see API skill references."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import re


class TrailingConditionError(ValueError):
    """Condition parsing failed; independently verified order identity is unchanged."""


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


def price_increment(value, decimal_tick):
    """HL decimal precision and five significant figures, with integer exemption."""
    value, decimal_tick = positive(value), positive(decimal_tick)
    if decimal_tick not in {Decimal(1).scaleb(-n) for n in range(7)}:
        raise ValueError("Invalid perpetual decimal tick")
    return max(decimal_tick, min(Decimal(1), Decimal(1).scaleb(value.adjusted() - 4)))


def normalize_quote_retracement(value, decimal_tick):
    value = positive(value)
    tick = price_increment(value, decimal_tick)
    return positive((value / tick).to_integral_value(rounding=ROUND_DOWN) * tick)


def send_trailing_action(exchange, action, nonce, expires_after):
    # Preserve insertion order: msgpack field order is part of the signed hash.
    from hyperliquid.utils.signing import sign_l1_action
    from hyperliquid.utils.constants import MAINNET_API_URL
    signature = sign_l1_action(exchange.wallet, action, exchange.vault_address,
                               nonce, expires_after, exchange.base_url == MAINNET_API_URL)
    return exchange.post("/exchange", {"action": action, "nonce": nonce,
        "signature": signature, "vaultAddress": exchange.vault_address,
        "expiresAfter": expires_after})


def parse_trailing_condition(condition):
    """Parse known app clauses without treating their syntax as requested protection."""
    if not isinstance(condition, str):
        raise ValueError("Missing native trailing condition")
    fields = {}
    for part in condition.split(","):
        match = re.fullmatch(r"\s*(retracement|best|activation\s+(above|below))\s+(\S+)\s*", part, re.IGNORECASE)
        if not match:
            raise ValueError("Unverified native trailing condition format")
        key = "activation" if match[2] else match[1].lower()
        if key in fields:
            raise ValueError("Duplicate native trailing condition clause")
        fields[key] = match[3]
        if key == "activation":
            fields["activation_direction"] = match[2].lower()
    if "retracement" not in fields:
        raise ValueError("Incomplete native trailing condition")
    raw = fields["retracement"]
    unit = "percent" if raw.endswith("%") else "quote"
    distance = positive(raw[:-1] if unit == "percent" else raw)
    retracement_wire(distance, unit)
    best = fields.get("best", "waiting")
    result = {"retracement": wire_decimal(distance), "retracement_unit": unit,
              "active": best.lower() != "waiting"}
    if "activation" in fields:
        result.update(activation_price=wire_decimal(positive(fields["activation"])),
                      activation_direction=fields["activation_direction"])
    if result["active"]:
        result["best_price"] = wire_decimal(positive(best))
    return result


def trailing_readback(order, *, retracement):
    """Verify managed long protective quote-distance semantics, never infer ownership."""
    if (order.get("orderType") != "Trailing Stop Market" or order.get("isTrigger") is not True
            or order.get("reduceOnly") is not True or order.get("side") != "A"):
        raise ValueError("Native trailing order semantics did not match")
    try:
        result = parse_trailing_condition(order.get("triggerCondition"))
    except ValueError as exc:
        raise TrailingConditionError(str(exc)) from exc
    if result["retracement_unit"] != "quote" or positive(result["retracement"]) != positive(retracement):
        raise ValueError("Native trailing retracement mismatch")
    if "activation_price" in result:
        raise ValueError("Native trailing activation mismatch; immediate activation required")
    if result["active"]:
        threshold = positive(result["best_price"]) - positive(result["retracement"])
        if threshold <= 0:
            raise ValueError("Invalid native trailing threshold")
        result["trigger_price"] = wire_decimal(threshold)
    return result
