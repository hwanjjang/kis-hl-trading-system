from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from kis_hl.assets import ResolvedAsset, resolve_hyperliquid_symbol
from kis_hl.trade_xyz_assets import TradeXyzAsset, get_trade_xyz_asset, normalize_trade_symbol

SESSION_CRYPTO_SPOT = "crypto_spot"
SESSION_CRYPTO_PERP = "crypto_perp"
SESSION_US_CASH = "us_cash_equities"
SESSION_KRX_CASH = "krx_cash_equities"
SESSION_TSE_CASH = "tse_cash_equities"
SESSION_COMMODITY_REFERENCE = "commodity_futures_reference"
SESSION_FX_REFERENCE = "fx_reference"
SESSION_UNKNOWN = "unknown"

NY_TZ = ZoneInfo("America/New_York")
KRX_TZ = ZoneInfo("Asia/Seoul")
TSE_TZ = ZoneInfo("Asia/Tokyo")
UTC_TZ = timezone.utc

# Shared by instantaneous eligibility and unobserved regular-session accounting.
CASH_SESSION_WINDOWS = {
    SESSION_KRX_CASH: (KRX_TZ, time(9, 0), time(15, 30)),
    SESSION_US_CASH: (NY_TZ, time(9, 30), time(16, 0)),
}


@dataclass(frozen=True, slots=True)
class TradingSessionDecision:
    allowed: bool
    reason: str
    session_group: str
    timezone: str
    market_timestamp: str
    holiday_calendar_applied: bool = False


def trading_session_decision_for_symbol(
    symbol: str,
    *,
    dex: str | None = None,
    now: datetime | None = None,
) -> TradingSessionDecision:
    return trading_session_decision_for_resolved_asset(
        resolve_hyperliquid_symbol(symbol, dex=dex),
        now=now,
    )


def trading_session_decision_for_resolved_asset(
    resolved: ResolvedAsset,
    *,
    now: datetime | None = None,
) -> TradingSessionDecision:
    current = _aware_utc_now(now)
    if resolved.kind == "spot" and resolved.coin == "UBTC/USDC":
        return _decision(
            True,
            "crypto_spot_is_24_7",
            SESSION_CRYPTO_SPOT,
            current.astimezone(UTC_TZ),
        )
    if resolved.kind == "perp" and resolved.coin in {"BTC", "ETH"} and resolved.dex is None:
        return _decision(
            True,
            "crypto_perp_is_24_7",
            SESSION_CRYPTO_PERP,
            current.astimezone(UTC_TZ),
        )

    if resolved.dex != "xyz":
        return _decision(
            False,
            "no_underlying_market_session_mapping",
            SESSION_UNKNOWN,
            current.astimezone(UTC_TZ),
        )

    asset = get_trade_xyz_asset(normalize_trade_symbol(resolved.coin))
    if asset is None:
        return _decision(
            False,
            "trade_xyz_asset_not_mapped",
            SESSION_UNKNOWN,
            current.astimezone(UTC_TZ),
        )
    return trading_session_decision_for_trade_xyz_asset(asset, now=current)


def trading_session_decision_for_trade_xyz_asset(
    asset: TradeXyzAsset,
    *,
    now: datetime | None = None,
) -> TradingSessionDecision:
    current = _aware_utc_now(now)
    session_group = session_group_for_trade_xyz_asset(asset)
    if session_group == SESSION_US_CASH:
        return _us_cash_decision(current)
    if session_group == SESSION_KRX_CASH:
        return _cash_decision(current, SESSION_KRX_CASH)
    if session_group == SESSION_TSE_CASH:
        return _tse_decision(current)
    if session_group == SESSION_COMMODITY_REFERENCE:
        return _commodity_reference_decision(current)
    if session_group == SESSION_FX_REFERENCE:
        return _fx_reference_decision(current)
    return _decision(
        False,
        "no_underlying_market_session_mapping",
        SESSION_UNKNOWN,
        current.astimezone(UTC_TZ),
    )


def session_group_for_trade_xyz_asset(asset: TradeXyzAsset) -> str:
    if asset.asset_class == "commodity":
        return SESSION_COMMODITY_REFERENCE
    if asset.asset_class == "fx":
        return SESSION_FX_REFERENCE
    if asset.trade_symbol == "JP225":
        return SESSION_TSE_CASH
    if asset.trade_symbol == "KR200" or asset.underlying_exchange == "KRX":
        return SESSION_KRX_CASH
    if asset.asset_class in {"stock", "etf", "equity_index"}:
        return SESSION_US_CASH
    return SESSION_UNKNOWN


def _us_cash_decision(current: datetime) -> TradingSessionDecision:
    return _cash_decision(current, SESSION_US_CASH)


def _cash_decision(current: datetime, session_group: str) -> TradingSessionDecision:
    zone, opens, closes = CASH_SESSION_WINDOWS[session_group]
    return _single_window_decision(
        current, timezone=zone, session_group=session_group,
        open_time=opens, close_time=closes,
    )


def regular_cash_session_elapsed_ms(
    start_ms: int, end_ms: int, *, session_group: str
) -> int:
    """Count weekday cash-session time in a gap, excluding nights/weekends.

    Uses the same windows as session eligibility. Holidays and early closes are
    not verified, so scheduled open time is conservatively counted during outages.
    """
    zone, opens, closes = CASH_SESSION_WINDOWS[session_group]
    if end_ms <= start_ms:
        return 0
    day = datetime.fromtimestamp(start_ms / 1000, zone).date()
    last_day = datetime.fromtimestamp(end_ms / 1000, zone).date()
    elapsed = 0
    while day <= last_day:
        if day.weekday() < 5:
            opened = int(datetime.combine(day, opens, tzinfo=zone).timestamp() * 1000)
            closed = int(datetime.combine(day, closes, tzinfo=zone).timestamp() * 1000)
            elapsed += max(0, min(end_ms, closed) - max(start_ms, opened))
        day += timedelta(days=1)
    return elapsed


def _single_window_decision(
    current: datetime,
    *,
    timezone: ZoneInfo,
    session_group: str,
    open_time: time,
    close_time: time,
) -> TradingSessionDecision:
    local = current.astimezone(timezone)
    if local.weekday() >= 5:
        return _decision(False, "weekend", session_group, local)
    if open_time <= local.time() < close_time:
        return _decision(True, "open_regular_session", session_group, local)
    return _decision(False, "outside_regular_session", session_group, local)


def _tse_decision(current: datetime) -> TradingSessionDecision:
    local = current.astimezone(TSE_TZ)
    if local.weekday() >= 5:
        return _decision(False, "weekend", SESSION_TSE_CASH, local)
    local_time = local.time()
    if time(9, 0) <= local_time < time(11, 30):
        return _decision(True, "open_morning_session", SESSION_TSE_CASH, local)
    if time(12, 30) <= local_time < time(15, 30):
        return _decision(True, "open_afternoon_session", SESSION_TSE_CASH, local)
    return _decision(False, "outside_regular_session", SESSION_TSE_CASH, local)


def _commodity_reference_decision(current: datetime) -> TradingSessionDecision:
    local = current.astimezone(NY_TZ)
    weekday = local.weekday()
    local_time = local.time()
    if weekday == 5:
        return _decision(False, "weekend", SESSION_COMMODITY_REFERENCE, local)
    if weekday == 6:
        return _decision(
            local_time >= time(18, 0),
            "open_electronic_session" if local_time >= time(18, 0) else "before_sunday_open",
            SESSION_COMMODITY_REFERENCE,
            local,
        )
    if weekday == 4:
        return _decision(
            local_time < time(17, 0),
            "open_electronic_session" if local_time < time(17, 0) else "after_friday_close",
            SESSION_COMMODITY_REFERENCE,
            local,
        )
    if time(17, 0) <= local_time < time(18, 0):
        return _decision(False, "daily_maintenance_break", SESSION_COMMODITY_REFERENCE, local)
    return _decision(True, "open_electronic_session", SESSION_COMMODITY_REFERENCE, local)


def _fx_reference_decision(current: datetime) -> TradingSessionDecision:
    local = current.astimezone(NY_TZ)
    weekday = local.weekday()
    local_time = local.time()
    if weekday == 5:
        return _decision(False, "weekend", SESSION_FX_REFERENCE, local)
    if weekday == 6:
        return _decision(
            local_time >= time(17, 0),
            "open_weekday_session" if local_time >= time(17, 0) else "before_sunday_open",
            SESSION_FX_REFERENCE,
            local,
        )
    if weekday == 4:
        return _decision(
            local_time < time(17, 0),
            "open_weekday_session" if local_time < time(17, 0) else "after_friday_close",
            SESSION_FX_REFERENCE,
            local,
        )
    return _decision(True, "open_weekday_session", SESSION_FX_REFERENCE, local)


def _decision(
    allowed: bool,
    reason: str,
    session_group: str,
    market_time: datetime,
) -> TradingSessionDecision:
    return TradingSessionDecision(
        allowed=allowed,
        reason=reason,
        session_group=session_group,
        timezone=str(market_time.tzinfo),
        market_timestamp=market_time.isoformat(),
    )


def _aware_utc_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC_TZ)
    return current.astimezone(UTC_TZ)
