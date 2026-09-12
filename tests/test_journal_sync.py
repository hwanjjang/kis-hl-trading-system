import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from kis_hl.journal_sync import Fill, JournalLedger, Scope, SyncSchedule


class JournalSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = JournalLedger(Path(self.tmp.name) / "state.sqlite")
        self.scope = Scope("hyperliquid", "mainnet", "test-account")

    def fill(self, key, side, qty, price, time, **kw):
        return Fill(key, "BTC", time, side, str(qty), str(price), "USDC", fee="1", **kw)

    def batch(self, fills, **kw):
        return self.store.ingest(
            self.scope,
            fills,
            start_ms=0,
            end_ms=100,
            source="test-statement",
            complete=True,
            costs_complete=True,
            **kw,
        )

    def test_external_cycle_dedupes_and_uses_net_return(self):
        fs = [
            self.fill("a", "buy", 2, 100, 10, position_before="0"),
            self.fill("b", "sell", 1, 110, 20),
            self.fill("c", "sell", 1, 120, 30),
        ]
        self.batch(fs)
        self.batch(fs)
        rows = self.store.entries(self.scope)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strategy"], "unassigned")
        self.assertEqual(Decimal(rows[0]["realized_pnl"]), Decimal("27"))
        self.assertEqual(Decimal(rows[0]["realized_pnl_pct"]), Decimal("13.5"))
        self.assertEqual(self.store.status(self.scope)["fill_count"], 3)

    def test_evidenced_attribution_enriches_without_changing_execution(self):
        from dataclasses import replace

        fill = self.fill("a", "buy", 1, 100, 10, position_before="0")
        self.batch([fill])
        enriched = replace(fill, strategy="alpha", strategy_version="1", origin="agent")
        self.batch([enriched], allow_attribution_enrichment=True)
        self.batch([fill], allow_attribution_enrichment=True)
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT payload FROM journal_source_fills ORDER BY revision"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIn('"strategy":"alpha"', rows[-1][0])
        with self.assertRaisesRegex(ValueError, "Conflicting execution"):
            self.batch(
                [replace(enriched, price="101")], allow_attribution_enrichment=True
            )
        with self.assertRaisesRegex(ValueError, "Conflicting execution"):
            self.batch(
                [replace(enriched, strategy="beta")], allow_attribution_enrichment=True
            )

    def test_missing_opening_history_or_costs_never_finalizes(self):
        self.batch([self.fill("a", "sell", 1, 100, 10)])
        self.assertEqual(self.store.entries(self.scope), [])
        self.assertTrue(self.store.status(self.scope)["pending"])
        other = Scope("kis", "live", "test-account")
        self.store.ingest(
            other,
            [
                self.fill("a", "buy", 1, 100, 10, position_before="0"),
                self.fill("b", "sell", 1, 110, 20),
            ],
            start_ms=0,
            end_ms=100,
            source="test",
            complete=True,
            costs_complete=False,
        )
        self.assertEqual(self.store.entries(other), [])

    def test_partial_exit_is_not_completed_and_external_add_marks_mixed(self):
        self.batch(
            [
                self.fill(
                    "a", "buy", 2, 100, 10, position_before="0", strategy="alpha"
                ),
                self.fill("b", "sell", 1, 110, 20),
            ]
        )
        self.assertEqual(self.store.entries(self.scope), [])
        self.batch([self.fill("c", "sell", 1, 120, 30)])
        self.assertEqual(self.store.entries(self.scope)[0]["strategy"], "mixed")

    def test_reversal_splits_quantity_and_fees_at_flat(self):
        self.batch(
            [
                self.fill("a", "buy", 1, 100, 10, position_before="0"),
                self.fill("b", "sell", 2, 110, 20),
                self.fill("c", "buy", 1, 100, 30),
            ]
        )
        rows = self.store.entries(self.scope)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(Decimal(r["realized_pnl"]) for r in rows), Decimal("17"))

    def test_failed_interval_cannot_advance_cursor_or_finalize(self):
        self.store.ingest(
            self.scope,
            [
                self.fill("a", "buy", 1, 100, 10, position_before="0"),
                self.fill("b", "sell", 1, 110, 20),
            ],
            start_ms=0,
            end_ms=100,
            source="incomplete",
            complete=False,
            costs_complete=True,
        )
        self.assertIsNone(self.store.status(self.scope)["covered_until_ms"])
        self.assertEqual(self.store.entries(self.scope), [])

    def test_conflicting_fill_requires_explicit_correction(self):
        self.batch([self.fill("a", "buy", 1, 100, 10, position_before="0")])
        with self.assertRaisesRegex(ValueError, "correction"):
            self.batch([self.fill("a", "buy", 1, 101, 10, position_before="0")])
        self.assertEqual(self.store.status(self.scope)["fill_count"], 1)

    def test_bad_decimal_rolls_back_entire_batch(self):
        with self.assertRaises(ValueError):
            self.batch([self.fill("a", "buy", 1, "NaN", 10, position_before="0")])
        self.assertEqual(self.store.status(self.scope)["fill_count"], 0)

    def test_scope_and_currency_are_separate(self):
        fs = [
            self.fill("a", "buy", 1, 100, 10, position_before="0"),
            self.fill("b", "sell", 1, 110, 20),
        ]
        self.batch(fs)
        self.assertEqual(
            self.store.entries(Scope("hyperliquid", "testnet", "test-account")), []
        )

    def test_schedule_default_change_and_overdue_coalescing(self):
        schedule = SyncSchedule(self.store, self.scope)
        self.assertEqual(schedule.settings()["interval_seconds"], 10800)
        schedule.success(1000)
        self.assertFalse(schedule.due(1001))
        schedule.configure(60, now_ms=2000)
        self.assertEqual(schedule.settings()["next_due_ms"], 61000)
        self.assertTrue(schedule.due(999999))
        schedule.success(999999)
        self.assertEqual(schedule.settings()["next_due_ms"], 1059999)
        for bad in [0, -1, True, 0.5]:
            with self.assertRaises(ValueError):
                schedule.configure(bad, now_ms=2000)
        self.assertEqual(schedule.settings()["interval_seconds"], 60)

    def test_equal_time_uses_position_continuity_not_id_sort(self):
        self.batch(
            [
                self.fill("2", "buy", 1, 100, 10, position_before="0"),
                self.fill("10", "sell", 1, 110, 10, position_before="1"),
            ]
        )
        self.assertEqual(len(self.store.entries(self.scope)), 1)

    def test_ambiguous_equal_time_is_pending(self):
        self.batch(
            [self.fill("2", "buy", 1, 100, 10), self.fill("10", "sell", 1, 110, 10)]
        )
        self.assertEqual(self.store.entries(self.scope), [])
        self.assertIn("Ambiguous", str(self.store.status(self.scope)["pending"]))

    def test_correction_stats_exclude_removed_cycles(self):
        self.batch(
            [
                self.fill("a", "buy", 1, 100, 10, position_before="0"),
                self.fill("b", "sell", 1, 110, 20),
                self.fill("c", "buy", 1, 100, 30),
                self.fill("d", "sell", 1, 110, 40),
            ]
        )
        self.batch(
            [
                self.fill("b", "sell", ".5", 110, 20),
                self.fill("c", "buy", ".5", 100, 30),
            ],
            allow_corrections=True,
        )
        rows = self.store.entries(self.scope)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stats_json"]["trade_count"], 1)

    def test_gap_fragment_remains_visible_when_later_flat_anchor_arrives(self):
        self.batch(
            [
                self.fill("a", "sell", 1, 100, 10),
                self.fill("b", "buy", 1, 100, 20, position_before="0"),
                self.fill("c", "sell", 1, 110, 30),
            ]
        )
        self.assertEqual(len(self.store.entries(self.scope)), 1)
        self.assertTrue(self.store.status(self.scope)["pending"])


if __name__ == "__main__":
    unittest.main()
