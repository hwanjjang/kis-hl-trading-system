# Required Trade-Journal Statistics

## Population and notation

Use completed journal records in the selected symbol/strategy population.

- `r_i`: `realized_pnl_pct` for record `i`, after fees when PnL is calculated locally.
- `h_i`: elapsed `holding_days` for record `i`.
- `W`: records where net `realized_pnl > 0`.
- `L`: records where net `realized_pnl < 0`.
- `B`: records where net `realized_pnl == 0`.
- `p_w = |W| / (|W| + |L|)` and `p_l = |L| / (|W| + |L|)`.

Breakevens remain in total `trade_count` but are excluded from `p_w` and `p_l`.

## The nine statistics

| Output | Formula | Contract |
| --- | --- | --- |
| `average_profit` | `sum(r_i for W) / |W|` | Positive percentage; `None` without wins. |
| `average_loss` | `sum(r_i for L) / |L|` | Negative percentage; `None` without losses. |
| `success_failure_ratio` | `average_profit / abs(average_loss)` | Display as `x:1`; `None` unless both sides exist. |
| `win_rate_pct` | `100 * p_w` | Breakevens excluded; `None` without a decisive trade. |
| `adjusted_success_failure_ratio` | `(average_profit * p_w) / (abs(average_loss) * p_l)` | Display as `x:1`; `None` unless both sides exist. |
| `max_profit` | `max(r_i for W)` | Positive percentage; `None` without wins. |
| `max_loss` | `min(r_i for L)` | Negative percentage; `None` without losses. |
| `average_profit_holding_days` | `sum(h_i for W) / |W|` | Elapsed days; `None` without wins. |
| `average_loss_holding_days` | `sum(h_i for L) / |L|` | Elapsed days; `None` without losses. |

The adjusted ratio is equivalent to:

```text
(average_profit * success_count)
/
(abs(average_loss) * failure_count)
```

because the common decisive-trade denominator cancels.

## Example

For completed returns `+10%`, `+20%`, and `-5%`:

```text
average_profit = 15%
average_loss = -5%
success_failure_ratio = 3:1
win_rate_pct = 66.666...%
adjusted_success_failure_ratio = 6:1
```

If the `-5%` trade has ten times the position size of a winner, these percentage
statistics do not change. Currency PnL and portfolio return are separate reports.

## Interpretation and edge cases

- A single-sided sample cannot establish a win/loss relationship. Return `None`
  instead of inventing `1:0`, infinity, or zero.
- Keep the stored sign on `average_loss` and `max_loss`; take an absolute value only
  when they are ratio denominators.
- Compare average winning and losing holding days over a useful sample. Winners held
  for less time than losers can reveal premature profit-taking and delayed loss exits,
  but it is a diagnostic rather than an automatic sell rule.
- Segment by strategy before changing risk rules. Aggregate figures can hide a weak
  setup behind a stronger, unrelated setup.
- One month can be noisy. Use monthly snapshots for monitoring and longer windows for
  conclusions, while preserving the exact population and filters used.
