# Scope clarification

AK previously explicitly requested Binance CLI live-by-default with `--dry-run`, but the inherited implementation incorrectly retained `--live` opt-in. This correction applies the requested CLI behavior, preserves Python direct-call dry-run defaults, and tests mode dispatch using fake transports. No exchange orders or signed vendor calls were executed.

The accepted C01 recommendation requires a protective stop to match the current one-way position direction and full quantity. This checks a snapshot inside the existing API-key lock, not account-wide exclusion against external clients.
