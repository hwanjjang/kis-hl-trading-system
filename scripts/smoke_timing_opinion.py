"""Offline smoke: real CLI processes against a local Jev stub and a temporary SQLite DB."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_strategy_tools import DAY, bar

KEY = "smoke-secret-key-must-not-leak"
ANSWER = {"model": "jev-1.13.0", "usage": {"input_tokens": 310, "output_tokens": 20},
          "answers": {"timing": {"type": "choice", "choice": "wait", "confidence": 0.7,
                                 "probabilities": {"long": 0.1, "short": 0.05, "wait": 0.85}}}}
seen = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append({"path": self.path, "bearer": self.headers["Authorization"] == "Bearer " + KEY,
                     "model": body["model"], "options": sorted(body["questions"]["timing"]["criteria"])})
        data = json.dumps(ANSWER).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def snapshot(now):
    return dict(id="smoke-snapshot", instrument="hl:BTC", source="fixture", currency="USDC",
                asof_ms=now, max_age_ms=600000, timeframe_ms=10800000,
                candles=[bar(now-21600000, 10800000, 100), bar(now-10800000, 10800000, 103)],
                daily_bars=[bar(now-DAY*(11-i), DAY, 100+i) for i in range(11)],
                weekly_bars=[bar(now-DAY*7*(31-i), DAY*7, 80+i) for i in range(31)],
                history_max_age_ms={"daily": 4*DAY, "weekly": 10*DAY})


def run():
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    outputs, steps = [], []
    with tempfile.TemporaryDirectory(prefix="timing-opinion-smoke-") as directory:
        root = Path(directory)
        env = {**os.environ, "PYTHONPATH": str(ROOT), "TYPESAFE_API_KEY": KEY, "TYPESAFE_MODEL": "",
               "TYPESAFE_BASE_URL": f"http://127.0.0.1:{server.server_port}"}

        def cli(*argv, expect=0, key=True):
            proc = subprocess.run([sys.executable, "-m", "kis_hl.cli", "--db", str(root/"s.sqlite"), *argv],
                                  cwd=root, env=env if key else {**env, "TYPESAFE_API_KEY": ""},
                                  capture_output=True, text=True, timeout=60)
            outputs.append(proc.stdout + proc.stderr)
            steps.append({"argv": list(argv[:2]), "exit": proc.returncode})
            assert proc.returncode == expect, (argv, proc.returncode, proc.stderr)
            return json.loads(proc.stdout) if expect == 0 else proc.stderr

        now = int(time.time() * 1000) // 1000 * 1000
        review = {"instrument": "hl:BTC", "snapshot_id": "smoke-snapshot", "asof_ms": now,
                  "horizon": "3-hour swing", "facts": {"breakout_predicate": True, "weekly_trend": "up"}}
        (root/"review.json").write_text(json.dumps(review))
        dry = cli("strategy", "opinion", "--dry-run", "--input", str(root/"review.json"), key=False)
        assert dry["payload"]["model"] == "jev-1.13.0" and not seen
        opinion = cli("strategy", "opinion", "--input", str(root/"review.json"))
        assert opinion["status"] == "available" and opinion["effective_opinion"] == "wait"
        assert opinion["order_authorized"] is False
        (root/"strategy.json").write_text(json.dumps(
            {"id": "trend", "version": "1", "description": "Smoke", "instruments": ["hl:BTC"]}))
        cli("strategy", "register", "--input", str(root/"strategy.json"))
        decision = dict(id="smoke-d1", strategy="trend", strategy_version="1", signal_instrument="hl:BTC",
                        execution_instruments=["hl:BTC"], observed_ms=now, expires_ms=now + 600000,
                        rationale="Breakout", action="enter",
                        setup_input=dict(setup="breakout", snapshot=snapshot(now), lookback=1),
                        confluence=["Weekly uptrend", "Prior high resistance"], management="Fixed SL",
                        timing_opinion=opinion)
        (root/"decision.json").write_text(json.dumps(decision))
        rejected = cli("strategy", "decide", "--input", str(root/"decision.json"), expect=1)
        assert "opinion_note" in rejected
        decision["opinion_note"] = "Confirmed breakout outweighs a medium-confidence wait"
        (root/"decision.json").write_text(json.dumps(decision))
        stored = cli("strategy", "decide", "--input", str(root/"decision.json"))
        listed = cli("signal", "list")
        match = [s for s in listed if s["id"] == "smoke-d1"]
        assert match and match[0]["timing_opinion"]["input_sha256"] == opinion["input_sha256"]
        assert stored["timing_opinion"]["effective_opinion"] == "wait"
    server.shutdown()
    assert len(seen) == 1 and seen[0] == {"path": "/v1/systemone", "bearer": True, "model": "jev-1.13.0",
                                          "options": ["long", "short", "wait"]}
    assert all(KEY not in text for text in outputs), "API key leaked into CLI output"
    return {"steps": steps, "stub_requests": seen, "opinion": {k: opinion[k] for k in
            ["status", "model", "choice", "probabilities", "confidence", "band", "effective_opinion",
             "order_authorized"]}, "key_leaked": False}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
