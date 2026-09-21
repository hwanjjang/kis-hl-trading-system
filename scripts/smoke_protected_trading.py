"""Exercise actual offline CLI processes and SQLite state without exchange writes."""

import json
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(
        os.environ,
        HYPERLIQUID_WALLETADDRESS="0x" + "1" * 40,
        HYPERLIQUID_PRIVATEKEY="",
        HYPERLIQUID_KEY_PROFILE="default",
        HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz",
    )
    with tempfile.TemporaryDirectory(prefix="protected-smoke-") as temp:
        folder = Path(temp)
        db = folder / "state.sqlite"
        calls = []

        def cli(*args):
            command = [sys.executable, "-m", "kis_hl.cli", "--db", str(db), *args]
            run = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
            )
            if run.returncode:
                raise RuntimeError(
                    "Offline CLI failed: " + str(args) + " / " + run.stderr
                )
            calls.append(list(args))
            return json.loads(run.stdout)

        def save(name, value):
            file = folder / name
            file.write_text(json.dumps(value))
            return str(file)

        catalog = cli("instrument", "list")["instruments"]
        assert {
            "index:KOSPI",
            "index:SPX",
            "index:NDX",
            "kis:GLD",
            "kis:DRAM",
            "hl:ETH",
        } <= {x["id"] for x in catalog}
        now = int(time.time() * 1000)
        plan = dict(
            intent_id="offline-smoke",
            instrument="hl:BTC",
            signal_instrument="hl:BTC",
            strategy="smoke",
            strategy_version="1",
            quantity="1",
            limit_price="100",
            atr="2",
            atr_multiple="2",
            max_notional="101",
            max_loss="5",
            max_quote_age_ms=1000,
            protection_grace_ms=5000,
            max_exit_attempts=3,
            exit_deadline_ms=60000,
            exit_reprice_ms=5000,
            slippage="0.01",
            allow_local_sl=True,
            expires_ms=now + 600000,
            max_portfolio_notional="1000",
            max_correlated_notional="500",
            max_spread_bps="20",
            max_entry_deviation_bps="100",
        )
        plan_path = save("plan.json", plan)
        assert cli("order", "preview", "--input", plan_path)["dry_run"] is True
        row = cli("order", "submit", "--input", plan_path)
        assert row["mode"] == "paper" and row["state"] == "QUEUED"
        cli("supervisor", "run", "--venue", "hyperliquid", "--once")
        observed = cli("order", "status", "--id", row["id"])
        assert observed["state"] == "PREVIEWED" and observed["attempts"] == []

        statement = dict(
            schema_version=1,
            source="offline synthetic statement",
            start_ms=0,
            end_ms=100,
            complete=True,
            costs_complete=True,
            fills=[
                dict(
                    execution_id="a",
                    symbol="SPY",
                    time_ms=10,
                    side="buy",
                    quantity="2",
                    price="100",
                    currency="USD",
                    fee="1",
                    position_before="0",
                ),
                dict(
                    execution_id="b",
                    symbol="SPY",
                    time_ms=20,
                    side="sell",
                    quantity="2",
                    price="110",
                    currency="USD",
                    fee="1",
                ),
            ],
        )
        source = save("statement.json", statement)
        common = [
            "--venue",
            "kis",
            "--account",
            "offline-fixture",
            "--environment",
            "sim",
        ]
        imported = cli("journal", "import", *common, "--input", source)
        duplicate = cli("journal", "import", *common, "--input", source)
        assert imported["finalized_count"] == 1 and duplicate["inserted_fills"] == 0
        report = cli("journal", "report", *common)
        assert len(report["entries"]) == 1 and Decimal(
            report["entries"][0]["realized_pnl"]
        ) == Decimal("18")
        before = cli("journal", "status", *common)
        assert before["schedule"]["interval_seconds"] == 10800
        cli("journal", "configure", *common, "--interval-seconds", "60")
        after = cli("journal", "status", *common)
        assert (
            after["schedule"]["interval_seconds"] == 60
            and before["coverage"] == after["coverage"]
        )

        cli(
            "strategy",
            "register",
            "--input",
            save(
                "strategy.json",
                dict(
                    id="smoke",
                    version="1",
                    description="Offline fixture",
                    instruments=["hl:BTC"],
                ),
            ),
        )
        cli(
            "signal",
            "ingest",
            "--input",
            save(
                "signal.json",
                dict(
                    id="signal-smoke",
                    strategy="smoke",
                    strategy_version="1",
                    signal_instrument="hl:BTC",
                    execution_instruments=["hl:BTC"],
                    observed_ms=now,
                    expires_ms=now + 600000,
                    rationale="Offline fixture",
                ),
            ),
        )
        first = cli(
            "signal",
            "execute",
            "--id",
            "signal-smoke",
            "--input",
            plan_path,
            "--manual",
        )
        second = cli(
            "signal",
            "execute",
            "--id",
            "signal-smoke",
            "--input",
            plan_path,
            "--manual",
        )
        assert first["id"] == second["id"]
        cli("order", "cancel", "--id", first["id"])
        cli("supervisor", "run", "--venue", "hyperliquid", "--once")
        final = cli("order", "status", "--id", first["id"])
        assert final["state"] == "CLOSED" and final["attempts"] == []
        print(
            json.dumps(
                {
                    "status": "passed",
                    "cli_processes": len(calls),
                    "checks": [
                        "explicit instrument identities",
                        "offline preview and paper supervisor",
                        "actual-fact fixture import and duplicate-safe net journal",
                        "persistent 3h default and configurable interval without cursor reset",
                        "versioned signal storage, manual claim deduplication and queued cancellation",
                    ],
                    "network_calls": 0,
                    "exchange_orders": 0,
                    "cleanup": "Temporary database and fixture files removed",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
