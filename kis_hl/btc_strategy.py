from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import (
    HyperliquidInfoClient,
    HyperliquidTradingClient,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.hyperliquid.ws import (
    HyperliquidWebSocketClient,
    all_mids_subscription,
    parse_all_mids_ticks_payload,
)
from kis_hl.logging_utils import get_logger
from kis_hl.risk import calculate_atr_10d
from kis_hl.signals import (
    BTCUSDC_FUTURES_INTERVAL,
    BTCUSDC_FUTURES_SYMBOL,
    BreakoutSignal,
    evaluate_btcusdc_futures_3h_breakout,
)
from kis_hl.streaming import PriceTick, TransportFactory, WebSocketStatus

logger = get_logger(__name__)

BTCUSDC_SPOT_SYMBOL = "BTCUSDC"
BTCUSDC_SPOT_COIN = "UBTC/USDC"
THREE_HOURS_MS = 3 * 60 * 60 * 1000
DEFAULT_BTC_ENTRY_NOTIONAL_USDC = Decimal("80")
DEFAULT_BTC_STOP_ATR_MULTIPLE = Decimal("2")
DAY_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True, slots=True)
class SpotCandle:
    start_ms: int
    end_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def as_signal_candle(self) -> dict[str, Any]:
        return {
            "t": self.start_ms,
            "T": self.end_ms,
            "o": str(self.open),
            "h": str(self.high),
            "l": str(self.low),
            "c": str(self.close),
        }


@dataclass(frozen=True, slots=True)
class BtcPerpEntryPlan:
    strategy: str
    spot_symbol: str
    perp_symbol: str
    perp_coin: str
    side: str
    order_type: str
    entry_notional_usdc: Decimal
    entry_price: Decimal
    entry_size: Decimal
    atr_10d: Decimal
    stop_atr_multiple: Decimal
    stop_distance: Decimal
    stop_loss_price: Decimal
    signal: BreakoutSignal


class ThreeHourSpotCandleBuilder:
    def __init__(self, *, interval_ms: int = THREE_HOURS_MS) -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        self.interval_ms = interval_ms
        self.current: SpotCandle | None = None

    def on_tick(self, tick: PriceTick) -> list[SpotCandle]:
        bucket_start = tick.received_at_ms - (tick.received_at_ms % self.interval_ms)
        bucket_end = bucket_start + self.interval_ms
        if self.current is None:
            self.current = SpotCandle(
                start_ms=bucket_start,
                end_ms=bucket_end,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
            )
            return []

        if bucket_start == self.current.start_ms:
            self.current = SpotCandle(
                start_ms=self.current.start_ms,
                end_ms=self.current.end_ms,
                open=self.current.open,
                high=max(self.current.high, tick.price),
                low=min(self.current.low, tick.price),
                close=tick.price,
            )
            return []

        closed = [self.current]
        self.current = SpotCandle(
            start_ms=bucket_start,
            end_ms=bucket_end,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
        )
        return closed


class BtcSpotBreakoutPerpStrategy:
    def __init__(
        self,
        *,
        atr_10d: Decimal,
        entry_notional_usdc: Decimal = DEFAULT_BTC_ENTRY_NOTIONAL_USDC,
        stop_atr_multiple: Decimal = DEFAULT_BTC_STOP_ATR_MULTIPLE,
        lookback_candles: int = 1,
        spot_symbols: Iterable[str] = (BTCUSDC_SPOT_COIN,),
    ) -> None:
        if atr_10d <= 0:
            raise ValueError("atr_10d must be positive")
        if entry_notional_usdc <= 0:
            raise ValueError("entry_notional_usdc must be positive")
        if stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple must be positive")
        if lookback_candles <= 0:
            raise ValueError("lookback_candles must be positive")
        self.atr_10d = atr_10d
        self.entry_notional_usdc = entry_notional_usdc
        self.stop_atr_multiple = stop_atr_multiple
        self.lookback_candles = lookback_candles
        self.spot_symbols = {symbol.upper() for symbol in spot_symbols}
        self.builder = ThreeHourSpotCandleBuilder()
        self.closed_candles: list[SpotCandle] = []
        self.entry_planned = False

    def on_tick(self, tick: PriceTick) -> BtcPerpEntryPlan | None:
        if tick.symbol.upper() not in self.spot_symbols:
            return None
        for candle in self.builder.on_tick(tick):
            self.closed_candles.append(candle)
        required = self.lookback_candles + 1
        if self.entry_planned or len(self.closed_candles) < required:
            return None

        signal = evaluate_btcusdc_futures_3h_breakout(
            [candle.as_signal_candle() for candle in self.closed_candles],
            lookback_candles=self.lookback_candles,
        )
        if not signal.should_enter:
            return None
        plan = create_btc_perp_entry_plan(
            signal,
            atr_10d=self.atr_10d,
            entry_notional_usdc=self.entry_notional_usdc,
            stop_atr_multiple=self.stop_atr_multiple,
        )
        self.entry_planned = True
        return plan


def create_btc_perp_entry_plan(
    signal: BreakoutSignal,
    *,
    atr_10d: Decimal,
    entry_notional_usdc: Decimal = DEFAULT_BTC_ENTRY_NOTIONAL_USDC,
    stop_atr_multiple: Decimal = DEFAULT_BTC_STOP_ATR_MULTIPLE,
) -> BtcPerpEntryPlan:
    if not signal.should_enter or signal.entry_price is None:
        raise ValueError("entry plan requires an active breakout signal")
    if atr_10d <= 0:
        raise ValueError("atr_10d must be positive")
    if entry_notional_usdc <= 0:
        raise ValueError("entry_notional_usdc must be positive")
    if stop_atr_multiple <= 0:
        raise ValueError("stop_atr_multiple must be positive")
    stop_distance = atr_10d * stop_atr_multiple
    stop_loss_price = signal.entry_price - stop_distance
    if stop_loss_price <= 0:
        raise ValueError("stop_loss_price must be positive")
    entry_size = entry_notional_usdc / signal.entry_price
    return BtcPerpEntryPlan(
        strategy=signal.strategy,
        spot_symbol=BTCUSDC_SPOT_SYMBOL,
        perp_symbol=BTCUSDC_FUTURES_SYMBOL,
        perp_coin=signal.resolved_coin,
        side="buy",
        order_type="market",
        entry_notional_usdc=entry_notional_usdc,
        entry_price=signal.entry_price,
        entry_size=entry_size,
        atr_10d=atr_10d,
        stop_atr_multiple=stop_atr_multiple,
        stop_distance=stop_distance,
        stop_loss_price=stop_loss_price,
        signal=signal,
    )


def execute_btc_perp_entry_plan(
    client: HyperliquidTradingClient,
    plan: BtcPerpEntryPlan,
    *,
    dry_run: bool = True,
    slippage: Decimal = Decimal("0.05"),
) -> dict[str, Any]:
    entry = client.place_order(
        symbol=plan.perp_symbol,
        side="buy",
        order_type="market",
        size=plan.entry_size,
        slippage=slippage,
        dry_run=dry_run,
    )
    stop = client.place_stop_loss_order(
        symbol=plan.perp_symbol,
        side="sell",
        size=plan.entry_size,
        trigger_price=plan.stop_loss_price,
        dry_run=dry_run,
    )
    return {
        "plan": asdict(plan),
        "entry_order": submission_to_dict(entry),
        "stop_loss_order": submission_to_dict(stop),
    }


def fetch_btc_perp_atr_10d(
    client: HyperliquidInfoClient,
    *,
    end_time_ms: int | None = None,
    lookback_days: int = 20,
) -> Decimal:
    if lookback_days < 11:
        raise ValueError("lookback_days must be at least 11 for ATR(10D)")
    resolved_end = end_time_ms or _time_ms()
    candles = client.candle_snapshot(
        BTCUSDC_FUTURES_SYMBOL,
        interval="1d",
        start_time_ms=resolved_end - (lookback_days * DAY_MS),
        end_time_ms=resolved_end,
    )
    if not isinstance(candles, list):
        raise RuntimeError("Hyperliquid daily candle snapshot returned a non-list response")
    return calculate_atr_10d(candles)


def run_btc_spot_breakout_monitor(
    *,
    config: HyperliquidConfig,
    trading_client: HyperliquidTradingClient,
    atr_10d: Decimal,
    entry_notional_usdc: Decimal = DEFAULT_BTC_ENTRY_NOTIONAL_USDC,
    stop_atr_multiple: Decimal = DEFAULT_BTC_STOP_ATR_MULTIPLE,
    lookback_candles: int = 1,
    dry_run: bool = True,
    slippage: Decimal = Decimal("0.05"),
    transport_factory: TransportFactory | None = None,
    max_messages: int | None = None,
    max_reconnects: int | None = None,
    on_execution: Callable[[dict[str, Any]], None] | None = None,
) -> WebSocketStatus:
    info_client = HyperliquidInfoClient(config)
    spot_symbols = {BTCUSDC_SPOT_COIN}
    try:
        spot_symbols.add(resolve_spot_order_coin(info_client.spot_meta(), BTCUSDC_SPOT_COIN))
    except Exception as exc:
        logger.warning("btc_spot_key_resolution_failed", extra={"error": str(exc)})
    strategy = BtcSpotBreakoutPerpStrategy(
        atr_10d=atr_10d,
        entry_notional_usdc=entry_notional_usdc,
        stop_atr_multiple=stop_atr_multiple,
        lookback_candles=lookback_candles,
        spot_symbols=spot_symbols,
    )

    def handle_message(payload: dict[str, Any]) -> None:
        received_at_ms = _payload_time_ms(payload)
        ticks = parse_all_mids_ticks_payload(payload, received_at_ms=received_at_ms)
        for tick in ticks:
            plan = strategy.on_tick(tick)
            if plan is None:
                continue
            logger.info(
                "btc_spot_breakout_entry_signal",
                extra={
                    "entry_price": str(plan.entry_price),
                    "entry_size": str(plan.entry_size),
                    "stop_loss_price": str(plan.stop_loss_price),
                    "dry_run": dry_run,
                },
            )
            execution = execute_btc_perp_entry_plan(
                trading_client,
                plan,
                dry_run=dry_run,
                slippage=slippage,
            )
            if on_execution:
                on_execution(execution)

    ws_client = HyperliquidWebSocketClient(
        config,
        subscriptions=[all_mids_subscription()],
        on_message=handle_message,
        transport_factory=transport_factory,
    )
    return ws_client.run(max_messages=max_messages, max_reconnects=max_reconnects)


def _payload_time_ms(payload: Mapping[str, Any]) -> int:
    for key in ("time", "t", "timestamp", "received_at_ms"):
        value = payload.get(key)
        if value not in (None, ""):
            return int(value)
    return _time_ms()


def _time_ms() -> int:
    import time

    return int(time.time() * 1000)
