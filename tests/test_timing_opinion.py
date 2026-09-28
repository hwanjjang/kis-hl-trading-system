import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.timing_opinion import OPTIONS, build_request, request_opinion

KEY = "test-key-never-printed"


def review(**overrides):
    return {
        "instrument": "hl:BTC",
        "snapshot_id": "fixture-snapshot",
        "asof_ms": 1790006400000,
        "horizon": "daily swing",
        "facts": {"breakout_predicate": True, "price_vs_30w_ema": "above, EMA rising",
                  "atr_10d_pct_of_price": "3.1"},
        "notes": ["Funding neutral"],
        **overrides,
    }


def answer(choice="long", probabilities=None, confidence=0.81, **extra):
    probabilities = probabilities or {"long": 0.88, "short": 0.02, "wait": 0.10}
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 300, "output_tokens": 20},
            "answers": {"timing": {"type": "choice", "choice": choice,
                                   "probabilities": probabilities, "confidence": confidence, **extra}}}


def opener_for(body, captured=None):
    def opener(req, timeout):
        if captured is not None:
            captured.update(url=req.full_url, headers=dict(req.header_items()),
                            body=json.loads(req.data), timeout=timeout)
        return io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
    return opener


def ask(body, **kwargs):
    return request_opinion(review(**kwargs), api_key=KEY, opener=opener_for(body))


class RequestTests(unittest.TestCase):
    def test_request_is_one_pinned_choice_over_long_short_wait(self):
        payload = build_request(review())
        self.assertEqual(payload["model"], "jev-1.13.0")
        self.assertEqual(list(payload["questions"]), ["timing"])
        question = payload["questions"]["timing"]
        self.assertEqual(question["type"], "choice")
        self.assertEqual(tuple(question["criteria"]), OPTIONS)
        self.assertEqual(set(payload["state"]), {"instrument", "horizon", "facts", "notes"})
        self.assertEqual(build_request(review()), payload)

    def test_state_limits_reject_empty_nested_oversized_or_non_finite_facts(self):
        for bad in [{}, {"nested": {"a": 1}}, {"text": "x" * 301}, {"nan": float("nan")},
                    {f"k{i}": i for i in range(41)}, {"": "blank key"}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_request(review(facts=bad))
        for key in ["instrument", "snapshot_id", "horizon"]:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                build_request(review(**{key: " "}))
        with self.assertRaises(ValueError):
            build_request(review(notes=["n"] * 11))
        with self.assertRaises(ValueError):
            build_request(review(min_confidence="1.5"))

    def test_http_call_uses_bearer_key_pinned_model_and_timeout(self):
        captured = {}
        result = request_opinion(review(), api_key=KEY, base_url="https://stub.invalid/",
                                 opener=opener_for(answer(), captured))
        self.assertEqual(captured["url"], "https://stub.invalid/v1/systemone")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer " + KEY)
        self.assertEqual(captured["body"], build_request(review()))
        self.assertEqual(captured["timeout"], 10)
        self.assertNotIn(KEY, json.dumps(result))


class ParseTests(unittest.TestCase):
    def test_valid_answer_is_advisory_with_probabilities_and_band(self):
        result = ask(answer())
        self.assertEqual(result["status"], "available")
        self.assertEqual((result["choice"], result["effective_opinion"], result["band"]), ("long", "long", "high"))
        self.assertEqual(result["probabilities"], {"long": "0.88", "short": "0.02", "wait": "0.1"})
        self.assertEqual(result["confidence"], "0.81")
        self.assertEqual(result["model"], "jev-1.13.0")
        self.assertIs(result["order_authorized"], False)
        self.assertEqual(result["input_sha256"], ask(answer())["input_sha256"])

    def test_confidence_below_minimum_becomes_wait(self):
        spread = {"long": 0.45, "short": 0.25, "wait": 0.30}
        result = ask(answer(probabilities=spread, confidence=0.18))
        self.assertEqual((result["choice"], result["effective_opinion"], result["band"]), ("long", "wait", "low"))
        medium = ask(answer(probabilities=spread, confidence=0.6))
        self.assertEqual((medium["effective_opinion"], medium["band"]), ("long", "medium"))
        strict = ask(answer(probabilities=spread, confidence=0.6), min_confidence="0.7")
        self.assertEqual(strict["effective_opinion"], "wait")

    def test_malformed_answers_are_unavailable_not_guessed(self):
        cases = {
            "missing option": answer(probabilities={"long": 0.9, "short": 0.1}),
            "extra option": answer(probabilities={"long": 0.8, "short": 0.1, "wait": 0.05, "hold": 0.05}),
            "non-finite": answer(probabilities={"long": float("inf"), "short": 0, "wait": 0}),
            "out of range": answer(probabilities={"long": 1.2, "short": -0.1, "wait": -0.1}),
            "bad sum": answer(probabilities={"long": 0.5, "short": 0.1, "wait": 0.1}),
            "not argmax": answer(choice="wait"),
            "unknown choice": answer(choice="buy"),
            "bad confidence": answer(confidence=1.5),
            "wrong type": answer(type="score"),
            "no answer": {"model": "jev-1.13.0", "answers": {}},
            "not json": b"<html>oops</html>",
        }
        for name, body in cases.items():
            with self.subTest(name):
                result = ask(body)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["effective_opinion"])
                self.assertIsNone(result["choice"])
                self.assertTrue(result["reason"])
                self.assertIs(result["order_authorized"], False)

    def test_raw_json_decimals_are_validated_without_float_rounding(self):
        def raw(confidence, probabilities):
            return ('{"model":"jev-1.13.0","answers":{"timing":{"type":"choice","choice":"long",'
                    '"probabilities":' + probabilities + ',"confidence":' + confidence + '}}}').encode()
        spread = '{"long":0.6,"short":0.1,"wait":0.3}'
        below = ask(raw("0.49999999999999999999", spread))
        self.assertEqual((below["status"], below["band"], below["effective_opinion"]), ("available", "low", "wait"))
        self.assertEqual(below["confidence"], "0.49999999999999999999")
        for probabilities in ['{"long":1.00000000000000001,"short":0,"wait":0}',
                              '{"long":1,"short":-1e-9999,"wait":0}',
                              '{"long":NaN,"short":0,"wait":0}']:
            with self.subTest(probabilities):
                self.assertEqual(ask(raw("0.9", probabilities))["status"], "unavailable")

    def test_http_and_transport_errors_are_unavailable(self):
        for error in [urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b"{}")) for code in [401, 422, 429, 529]] + [
                socket.timeout("timed out"), urllib.error.URLError("refused")]:
            def opener(req, timeout, error=error):
                raise error
            with self.subTest(error=repr(error)):
                result = request_opinion(review(), api_key=KEY, opener=opener)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["effective_opinion"])
                self.assertNotIn(KEY, json.dumps(result))

    def test_missing_key_is_a_configuration_error(self):
        with self.assertRaisesRegex(ValueError, "TYPESAFE_API_KEY"):
            request_opinion(review(), api_key="", opener=opener_for(answer()))

    def test_malformed_key_and_insecure_url_are_rejected_without_echoing_the_key(self):
        for key in [KEY + "\r", KEY + "\n", "a b"]:
            with self.subTest(key=repr(key)), self.assertRaises(ValueError) as ctx:
                request_opinion(review(), api_key=key, opener=opener_for(answer()))
            self.assertNotIn(key.strip(), str(ctx.exception))
        with self.assertRaisesRegex(ValueError, "https"):
            request_opinion(review(), api_key=KEY, base_url="http://api.example.com", opener=opener_for(answer()))

    def test_protocol_failures_and_oversized_values_are_unavailable(self):
        import http.client
        for error in [http.client.BadStatusLine("x"), http.client.IncompleteRead(b"")]:
            def opener(req, timeout, error=error):
                raise error
            with self.subTest(error=repr(error)):
                self.assertEqual(request_opinion(review(), api_key=KEY, opener=opener)["status"], "unavailable")
        deep = ("[" * 100000 + "]" * 100000).encode()
        self.assertEqual(ask(deep)["status"], "unavailable")
        self.assertEqual(ask({**answer(), "model": "m" * 65})["status"], "unavailable")
        usage = ask({**answer(), "usage": ["anything", {"nested": 1}]})
        self.assertEqual((usage["status"], usage["usage"]), ("available", None))

    def test_redirects_are_not_followed(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading
        hits = []

        class Stub(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/steal")
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_POST

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = request_opinion(review(), api_key=KEY, base_url=f"http://127.0.0.1:{server.server_port}")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "HTTP 302"))
        self.assertEqual(hits, ["/v1/systemone"])


class CliTests(unittest.TestCase):
    def test_dry_run_prints_request_without_key_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(review()))
            out = io.StringIO()
            env = {"TYPESAFE_API_KEY": "", "TYPESAFE_BASE_URL": "", "TYPESAFE_MODEL": ""}
            with patch.dict("os.environ", env), \
                    patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                    contextlib.redirect_stdout(out):
                code = main(["strategy", "opinion", "--dry-run", "--input", str(path)])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["payload"], build_request(review()))
            self.assertEqual(result["url"], "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(len(result["input_sha256"]), 64)
            path.write_text(json.dumps(review(facts={})))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["strategy", "opinion", "--dry-run", "--input", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
