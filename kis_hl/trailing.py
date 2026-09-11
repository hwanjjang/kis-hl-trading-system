"""Deterministic long-only trailing policy; no exchange or storage side effects."""
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

NINE_MINUTES_MS = 540_000


def positive(value: Decimal, name: str) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return value


@dataclass
class Trail:
    entry: Decimal
    distance: Decimal
    high: Decimal
    threshold: Decimal
    opened_ms: int
    last_ms: int = -1
    bucket: int | None = None
    bucket_high: Decimal | None = None
    bucket_valid: bool = False
    last_bar: int | None = None

    @classmethod
    def create(cls, *, entry: Decimal, atr: Decimal, multiple: Decimal, opened_ms: int):
        for name, value in [('entry', entry), ('atr', atr), ('multiple', multiple)]:
            positive(value, name)
        distance = atr * multiple
        positive(entry - distance, 'initial stop')
        if opened_ms < 0:
            raise ValueError('opened_ms must be non-negative')
        return cls(entry, distance, entry, entry - distance, opened_ms)

    def disconnect(self) -> None:
        # Partial bars are never recovered from a period without proven coverage.
        self.bucket = None
        self.bucket_high = None
        self.bucket_valid = False

    def tick(self, time_ms: int, price: Decimal, *, max_gap_ms: int) -> bool:
        positive(price, 'price')
        if max_gap_ms <= 0:
            raise ValueError('max_gap_ms must be positive')
        if time_ms <= self.last_ms or time_ms < self.opened_ms:
            return False
        bucket = time_ms // NINE_MINUTES_MS * NINE_MINUTES_MS
        continuous = self.last_ms >= 0 and time_ms - self.last_ms <= max_gap_ms
        if self.bucket != bucket:
            if (self.bucket is not None and self.bucket_valid and continuous
                    and bucket == self.bucket + NINE_MINUTES_MS):
                self.high = max(self.high, self.bucket_high)
                self.threshold = max(self.threshold, self.high - self.distance)
                self.last_bar = self.bucket
            self.bucket_valid = (self.bucket is not None and continuous
                                 and bucket == self.bucket + NINE_MINUTES_MS)
            self.bucket = bucket
            self.bucket_high = price
        else:
            self.bucket_valid = self.bucket_valid and continuous
            self.bucket_high = max(self.bucket_high, price)
        self.last_ms = time_ms
        return price <= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        values = dict(data)
        for key in ['entry', 'distance', 'high', 'threshold', 'bucket_high']:
            if values.get(key) is not None:
                values[key] = Decimal(values[key])
        return cls(**values)
