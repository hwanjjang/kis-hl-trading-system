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
    if any(o.get("orderType") == "Trailing Stop Market" for o in pre["open_orders"]):
        raise ValueError("migration-required: external trailing order needs an explicit supported migration plan")
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


def verify_kis_adoption(gateway, row, now):
    """Admit an existing KIS long bought by one identified, fully filled buy order.

    KIS has no verified native protective order, so admission only proves the
    position and hands it to the local fixed-SL and nine-minute trailing loop.
    """
    p, request = row["plan"], row["adoption"]
    asset = gateway._asset(p["instrument"])
    if asset.market != "domestic":
        raise ValueError("KIS handoff supports domestic listings only")
    if not p.get("allow_local_sl") or p.get("trailing_provider", "local") != "local":
        raise ValueError("KIS handoff requires local SL and local trailing")
    if "fixed_stop_price" not in p:
        raise ValueError("KIS handoff requires an explicit fixed_stop_price")
    entry_id = str(request["entry_order_id"])
    since = int(request["entry_since_ms"])
    if not 0 < since <= now:
        raise ValueError("Invalid handoff history start")
    history = [r for r in gateway._history(asset, since, now) if r["pdno"] == asset.symbol]
    # The admitted generation must be exactly the identified buy: no other buy may
    # contribute after it, and any earlier sells must have left the account flat.
    buys = [r for r in history if r.get("sll_buy_dvsn_cd", r.get("sll_buy_dvsn")) == "02"
            and gateway._quantity(r, asset.market) > 0]
    entry = [r for r in buys if str(r["odno"]) == entry_id]
    if len(entry) != 1 or len(buys) != 1:
        raise ValueError("Handoff requires exactly one identified filled buy in the history window")
    entry = entry[0]
    filled = gateway._quantity(entry, asset.market)
    if entry.get("cncl_yn") == "Y" or filled != decimal(entry["ord_qty"]):
        raise ValueError("Identified buy is not fully filled")
    open_rows = gateway.client.account_pages("domestic_orders", exchange="NASD")["output"]
    if any(r["pdno"] == asset.symbol for r in open_rows):
        raise ValueError("Open orders for the instrument block handoff")
    rows = gateway._rows(asset)
    pos = next((r for r in rows if r["pdno"] == asset.symbol), None)
    size = decimal(pos["hldg_qty"]) if pos else Decimal(0)
    average = decimal(pos["pchs_avg_pric"]) if pos and size else Decimal(0)
    if (pos is None or size != filled or size != decimal(p["quantity"])
            or average != decimal(p["limit_price"]) or decimal(pos["ord_psbl_qty"]) != size):
        raise ValueError("Adoption plan does not match the current holding")
    atr, atr_source = gateway._atr(asset, now)
    if abs(decimal(atr) - decimal(p["atr"])) > decimal(p["atr"]) * Decimal("0.000001"):
        raise ValueError("Adoption ATR differs from current execution history")
    trail = Trail.create(entry=average, atr=decimal(p["atr"]),
                         multiple=decimal(p.get("local_atr_multiple", p["atr_multiple"])), opened_ms=now)
    # Owned history baseline: the entry counts from zero; nothing else may appear later.
    baseline = {str(r["odno"]): str(gateway._quantity(r, asset.market))
                for r in history if str(r["odno"]) != entry_id}
    updates = {"state": "PROTECTING", "reason": "KIS holding admitted; awaiting local protection supervision",
               "adopted_ms": now, "baseline": baseline, "baseline_start_ms": since,
               "first_fill_ms": since, "entry_filled": str(size), "observed_size": str(size),
               "covered_size": "0", "trailing_covered_size": "0", "trail": trail.to_dict(),
               "atr_source": atr_source,
               "providers": {"stop_loss": "local", "trailing": "local", "local_trailing_backup": False}}
    attempts = [{"id": "0x" + uuid4().hex, "position_id": row["id"], "kind": "entry",
                 "order_id": entry_id, "status": "FILLED", "created_ms": now,
                 "quantity": str(size), "price": str(average), "imported": True}]
    return updates, attempts
