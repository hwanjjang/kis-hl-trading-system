# PR #14 inventory correction: renewed independent verification

Verdict: **PASS**. No remaining Must Fix or recommended finding in this bounded
correction. Reviewer `/root/verify_inventory_correction` independently verified
builder `/root`'s revised candidate based on
`76d22d4a1aa0ee2ce804bae1aa2d074af5793a51`. The previous BLOCKED report is retained
unchanged. This report is the renewed preflight during build attempt 4; the parent
owns the formal independent-verification stage and its receipts.

## Executed evidence

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.test_canonical_inventory tests.test_unified_data -q` | PASS: 61 tests, 8.140 s |
| `python3 -m unittest discover -s tests -t . -q` | PASS: 321 tests, 28.624 s |
| `python3 scripts/smoke_canonical_inventory.py` | PASS: 7 real CLI processes, 7 raw facts, 1 valid finalized cycle; invalid returns excluded, fees retained, immutable export, cleanup confirmed |
| `PYTHONPATH=. python3 /tmp/verify_inventory_correction.py` | Three independent real-SQLite probes pass the intended outcomes below |
| `PYTHONPATH=.:/tmp python3 /tmp/verify_inventory_additional.py` | Three additional independent edge probes pass |

The CLI smoke was inspected and executed. It uses a temporary working directory
and restricted environment, synthetic manifest preview/apply/replay, a real journal,
new immutable export and repeated generation. It does not load repository credentials
or call vendors. Temporary fixture directories were removed. The JSON companion
contains exact probe results, retained or referenced reproducible scripts, and file
hashes verified unchanged before/after execution.

## Findings resolved and independently challenged

- **F-1:** KIS oversell is rejected before the tracked long closes; no fabricated
  short or confirmed return enters metrics. All source fees remain in the observed
  account summary and unreliable account net remains unavailable.
- **F-2:** Complete trade coverage cannot anchor opening inventory. Unanchored
  cycles remain ineligible until explicit flat evidence establishes a later cycle.
  DAY ending holdings are checked after all same-day activity.
- **IV-1:** Day 1 buy 1 anchored at zero; day 2 sell 1 before=1/end=7 and then sell 2
  now yields PENDING with opening_inventory_gap and null return. The first closed
  candidate cannot escape validation through the later oversell branch.
- **IV-2:** A verified day-1/2 cycle remains FINALIZED when day-3 activity is
  ambiguous. A later day-end contradiction likewise preserves the earlier cycle.
- Additional probes force same-day position-before mismatch and ambiguous chronology
  after an apparent close. Both invalidate the overlapping candidate. A positive
  probe ingests evidenced same-day re-entry before the closing sell; chronology
  reconstruction still finalizes both valid cycles with no quality findings.
- Anchored partial exits/adds, subsequent continuous cycles, normal Hyperliquid
  long-to-short reversal, fee/funding conservation and immutable prior report IDs
  remain covered by the executed regression suite.

The shared interval-aware invalidation helper now applies consistently to all early
errors and day-end mismatch. Its half-open boundary preserves strictly earlier
verified exits while invalidating DAY cycles overlapping the unresolved period.

## Acceptance, documentation and limits

**AC3 PASS; AC6 PASS for this correction scope.** The operations guide and
trade-journal record contract agree with source-backed anchors, gap behavior,
ending-holdings checks, unavailable account net, preserved source facts, and the
new `kis-inventory-v1` metadata. The nine metric formulas are unchanged. Existing
report IDs stay frozen; a new report/export is needed to adopt the policy.

This verification is offline and synthetic. No broker calls, private-data migration,
orders, source edits, commits or publication were performed. Unchanged vendor
adapters were not revalidated against live services. Reconstruction intentionally
stops for inconsistent instrument inventory until the source is reconciled. This
local review does not substitute for the separately requested actual-provider
Fable PR re-review. No additional skill observation was identified.

## Reviewed file hashes

- `kis_hl/journal_exports.py`: `8f6169ef53ad7dd906f74cd85b85b34d445bdad7cd661cebfacc698fbcc1102d`
- `tests/test_canonical_inventory.py`: `8f8577c80c6434c71ae8adcf443c2350547409994116cdabb9b65417ba5f0b9e`
- `tests/test_unified_data.py`: `fcc71bf7c18fce237fa28f9c417defb1120b49d8bce994fe11ea1bb82d418078`
- `scripts/smoke_canonical_inventory.py`: `9e11106c20d63ecd370ab2dedb43777f89c9626451d9d7657f67c6bd5db56d9e`
- `docs/unified-data-operations.md`: `35440f872faf50c98a7c0ba6cb2ec76b68839cea266c41eccc40135a19f3c636`
- `.agents/skills/trade-journal/references/record-contract.md`: `e929757fb164fcc4e634bad1fa53e84709ef156358b11cb898400453a48a1264`
