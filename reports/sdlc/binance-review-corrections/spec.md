# Spec

Disable data-idle staleness only for Binance private streams. Keep transport disconnect detection. Deliver messages before renewal; retry transient renewal errors on bounded intervals, expire safely. Fail promptly on missing credentials/permanent auth errors. Hide credential repr and isolate CLI tests. PR18 pins supported live symbols to BTCUSDT and verifies current perpetual COIN/TRADING metadata. Normalize terminal acknowledgements, validate incompatible flags, and cover lock/allowlist guards. Preserve separate branch ownership.
