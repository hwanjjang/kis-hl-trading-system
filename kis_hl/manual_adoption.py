"""Read-only admission of an explicitly identified existing Hyperliquid long."""
from decimal import Decimal
from uuid import uuid4

from kis_hl.journal_sync import decimal
from kis_hl.journal_history import fetch_time_pages
from kis_hl.hyperliquid.trailing import normalize_quote_retracement, wire_decimal
from kis_hl.trailing import Trail
from kis_hl.trailing_storage import has_managed_position


def verify_adoption(gateway, row, now):
    p, request = row["plan"], row["adoption"]
    asset, resolved, lot, tick = gateway._market(p["instrument"])
    if has_managed_position(gateway.trading.verification_db_path,
                            network=gateway.network, account=gateway.account, coin=resolved.coin):
        raise ValueError("Legacy trailing already owns this position")
    gateway.trading._require_credentials()
    pre = gateway.preflight(p, now, existing_position=True)
    now = int(pre.get("observed_now_ms", now))
    if (not pre["eligible"] or not 0 <= now - int(pre["time_ms"]) <= p["max_quote_age_ms"]
            or decimal(pre["portfolio_notional"]) > decimal(p["max_portfolio_notional"])
            or decimal(pre["correlated_notional"]) > decimal(p["max_correlated_notional"])):
        raise ValueError("Adoption eligibility, quote or portfolio limit failed")
    if (pre["atr_source"]["instrument"] != asset.id
            or abs(decimal(pre["atr"]) - decimal(p["atr"])) > decimal(p["atr"]) * Decimal("0.000001")):
        raise ValueError("Adoption ATR differs from current execution history")
    entry_id, stop_id = request["entry_order_id"], request["stop_order_id"]
    response = gateway.info.order_status(oid=entry_id)
    entry = response["order"]["order"]
    if (response["status"] != "order" or response["order"]["status"] != "filled"
            or str(entry["oid"]) != str(entry_id) or entry["coin"] != resolved.coin
            or entry["side"] != "B" or entry.get("reduceOnly") is not False):
        raise ValueError("Adoption requires the identified fully filled long entry")
    start = entry["timestamp"]
    if type(start) is not int or not 0 <= start <= now:
        raise ValueError("Invalid entry timestamp")
    raw = fetch_time_pages(lambda a,b: gateway.info.user_fills_by_time(start_time_ms=a,end_time_ms=b),
                           start, now, limit=2000)
    tail = gateway.info.user_fills()
    if not tail or any(type(f.get("time")) is not int for f in tail):
        raise ValueError("Missing retention evidence")
    fills = {}
    for f in raw:
        if f["coin"] != resolved.coin:
            continue
        if (str(f["oid"]) != str(entry_id) or f["side"] != "B"
                or type(f["time"]) is not int or not start <= f["time"] <= now):
            raise ValueError("Position history includes other executions")
        key = str(f["tid"])
        if key in fills and fills[key] != f:
            raise ValueError("Conflicting duplicate execution")
        fills[key] = f
    ordered = sorted(fills.values(), key=lambda f: (f["time"], int(f["tid"])))
    if not ordered or min(f["time"] for f in tail) > ordered[0]["time"]:
        raise ValueError("Entry predates retained execution history")
    quantity, cost = Decimal(0), Decimal(0)
    for f in ordered:
        if decimal(f["startPosition"]) != quantity:
            raise ValueError("Entry does not establish a complete flat-to-long generation")
        size = decimal(f["sz"], positive=True)
        quantity += size
        cost += size * decimal(f["px"], positive=True)
    average = cost / quantity
    if (quantity != decimal(entry["origSz"]) or quantity != decimal(p["quantity"])
            or average != decimal(p["limit_price"]) or quantity % lot):
        raise ValueError("Adoption plan does not match entry executions")
    attempts = [{"id":"0x"+uuid4().hex, "position_id":row["id"], "kind":kind,
                 "order_id":str(oid), "status":status, "created_ms":now,
                 "quantity":str(quantity), "price":str(average), "imported":True}
                for kind,oid,status in (("entry",entry_id,"FILLED"),("stop",stop_id,"SUBMITTED"))]
    candidate = row | {"fill_history_start_ms": start}
    snap = gateway.snapshot(candidate, attempts, now)
    now = int(snap.get("observed_now_ms", now))
    # Account/history reads can outlive preflight freshness; recheck before import.
    if any(not 0 <= now - int(observation["time_ms"]) <= p["max_quote_age_ms"]
           for observation in (pre, snap)):
        raise ValueError("Adoption quote freshness failed after account reads")
    stop = snap["orders"].get(str(stop_id), {})
    distance = decimal(p["stop_distance"])
    if (not snap["consistent"] or snap["foreign_add"] or decimal(snap["size"]) != quantity
            or decimal(snap["entry_filled"]) != quantity or decimal(snap["entry_price"]) != average
            or stop.get("status") != "open" or stop.get("kind") != "stop"
            or decimal(stop.get("size", "0")) != quantity
            or decimal(stop.get("trigger_price", "0")) < average-distance):
        raise ValueError("Current position or fixed SL cannot be reconciled")
    trail = Trail.create(entry=average, atr=decimal(p["atr"]),
                         multiple=decimal(p.get("local_atr_multiple", p["atr_multiple"])), opened_ms=now)
    if "local_atr_multiple" not in p and "fixed_stop_price" not in p:
        trail.threshold = max(trail.threshold, decimal(stop["trigger_price"]))
    native = p["trailing_provider"] == "native"
    updates = {"state":"PROTECTING", "reason":"Manual position admitted; awaiting protection supervision",
               "adopted_ms":now, "fill_history_start_ms":start, "first_fill_ms":ordered[0]["time"],
               "entry_filled":str(quantity), "observed_size":str(quantity), "covered_size":str(quantity),
               "trailing_covered_size":"0", "trail":trail.to_dict(), "atr_source":pre["atr_source"],
               "adopted_entry_fill_ids":sorted(fills),
               "providers":{"stop_loss":"native", "trailing":p["trailing_provider"],
                            "local_trailing_backup":p.get("local_trailing_backup",False)}}
    if native:
        native_distance = decimal(p["atr"]) * decimal(p.get("native_atr_multiple", p["atr_multiple"]))
        updates["native_trailing_distance"] = wire_decimal(normalize_quote_retracement(native_distance,tick))
    attempts[1]["trigger_price"] = stop["trigger_price"]
    return updates, attempts
