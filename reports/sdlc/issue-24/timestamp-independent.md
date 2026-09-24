# Independent verification: canonical candle timestamp aliases

Verdict: PASS; no findings in the scoped three-file change. This is independent local verification, not an external PR review.

## Scope and inspection

Reviewed the complete current diff of `kis_hl/signals.py`, `tests/test_signals.py` and `docs/strategy-tools.md`. The helper now accepts `start_ms`/`end_ms` after every pre-existing timestamp alias. The existing normalizer sorts fully timestamped candles; preserving canonical timestamps therefore both fixes public result identity and makes latest/reference selection work for reversed canonical input. Legacy alias priority remains unchanged. Wrapper validation still runs before helper normalization and is not relaxed.

No repository edit, external API action, live execution, delegation or dependency installation was performed.

## Focused checks

- `python3 -m unittest tests.test_signals tests.test_strategy_tools`: 16 tests passed in 0.075 seconds, exit 0. Includes reverse canonical chronology/time retention and legacy precedence regressions, plus existing wrapper behavior.
- Separate public-helper probe used reversed canonical BTC fixture candles. It passed the expected breakout and preserved the latest candle start and reference candle end timestamps.
- The same fixture passed `evaluate_setup` in normal order, then returned `status=unavailable`, predicate false and an unordered-bar reason after reversing the input. This confirms the helper improvement does not cause the strategy wrapper to accept unordered snapshots.
- Documentation accurately distinguishes helper alias support/normalization from the strategy snapshot ordering requirement.

## Candidate identity

HEAD: `6d9cd131acf26f19bcdbce412ef2c1c9dc6bf17a`; reviewed uncommitted three-file diff.

- `kis_hl/signals.py`: `466dab9a6b3b0cf2484ac32aecb453eddb9aa15f0b4fdf06087ae0e3ca692b15`
- `tests/test_signals.py`: `cf3b72fd1fdfb89ce8f7902d50918448779f13aa589414ec4fe99862e67cebd1`
- `docs/strategy-tools.md`: `a4b3bc495a809d21cb23fc87d6eb291c93739731a74204b93166bbb88dbc9f9d`
