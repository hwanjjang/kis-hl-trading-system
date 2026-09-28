"""Advisory long/short/wait timing opinion from TypeSafe's Jev model; never order authority."""

from decimal import Decimal, InvalidOperation
import hashlib
import http.client
import json
import math
import urllib.error
import urllib.parse
import urllib.request

OPTIONS = ("long", "short", "wait")
DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MIN_CONFIDENCE = Decimal("0.5")
HIGH_CONFIDENCE = Decimal("0.8")
TIMEOUT_SECONDS = 10
MAX_FACTS, MAX_NOTES, MAX_TEXT, MAX_KEY = 40, 10, 300, 64
SUM_TOLERANCE = Decimal("0.01")
MAX_RESPONSE_BYTES = 1_000_000
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

QUESTION = {
    "type": "choice",
    "instructions": "Using only `facts` and `notes`, which stance on `instrument` over the `horizon` is best supported right now?",
    "criteria": {
        "long": "The evidence supports taking or keeping long exposure now: trend and momentum point up and the setup is confirmed.",
        "short": "The evidence points down: trend or momentum is falling or support has failed, so new long exposure should be avoided.",
        "wait": "The evidence is mixed, missing, stale or unconfirmed: take no new position and wait for confirmation.",
    },
}


def _text(value, name, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be non-empty text of at most {limit} characters")
    return value


def _fact(value, name):
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Fact {name} must be finite")
        return value
    if isinstance(value, str) and len(value) <= MAX_TEXT:
        return value
    raise ValueError(f"Fact {name} must be text, boolean or a finite number")


def min_confidence(review):
    try:
        value = Decimal(str(review.get("min_confidence", DEFAULT_MIN_CONFIDENCE)))
    except InvalidOperation:
        raise ValueError("min_confidence must be a decimal") from None
    if not value.is_finite() or not 0 < value <= 1:
        raise ValueError("min_confidence must be in (0, 1]")
    return value


def build_request(review, *, model=DEFAULT_MODEL):
    """Validate a compact review snapshot and return the exact Jev request body."""
    _text(review.get("instrument"), "instrument")
    _text(review.get("snapshot_id"), "snapshot_id")
    asof = review.get("asof_ms")
    if isinstance(asof, bool) or not isinstance(asof, int) or asof <= 0:
        raise ValueError("asof_ms must be a positive integer")
    facts = review.get("facts")
    if not isinstance(facts, dict) or not 0 < len(facts) <= MAX_FACTS:
        raise ValueError(f"facts must hold 1 to {MAX_FACTS} named values")
    notes = review.get("notes", [])
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise ValueError(f"notes must be a list of at most {MAX_NOTES} items")
    min_confidence(review)
    return {
        "model": _text(model, "model", MAX_KEY),
        "state": {
            "instrument": review["instrument"],
            "horizon": _text(review.get("horizon"), "horizon"),
            "facts": {_text(k, "fact name", MAX_KEY): _fact(v, k) for k, v in facts.items()},
            "notes": [_text(n, "note") for n in notes],
        },
        "questions": {"timing": QUESTION},
    }


def encode_request(payload):
    """Return the canonical request bytes and their SHA-256."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return body, hashlib.sha256(body).hexdigest()


def endpoint(base_url):
    """HTTPS only, except plain HTTP to loopback for offline stubs."""
    parts = urllib.parse.urlsplit(base_url)
    if not (parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOOPBACK)):
        raise ValueError("TYPESAFE_BASE_URL must use https (http only for loopback)")
    return base_url.rstrip("/") + "/v1/systemone"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def gate(choice, confidence, minimum):
    """Return (band, effective opinion); low confidence always becomes wait."""
    if confidence < minimum:
        return "low", "wait"
    return ("high" if confidence >= HIGH_CONFIDENCE else "medium"), choice


def _unit(value, *, text=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str) if text else (int, float)):
        raise ValueError("non-numeric value")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("non-numeric value") from None
    if not number.is_finite() or not 0 <= number <= 1:
        raise ValueError("value outside [0, 1]")
    return number


def _answer(choice, raw, confidence, *, text=False):
    if not isinstance(raw, dict) or set(raw) != set(OPTIONS):
        raise ValueError("option set differs from long/short/wait")
    probabilities = {k: _unit(raw[k], text=text) for k in OPTIONS}
    if abs(sum(probabilities.values()) - 1) > SUM_TOLERANCE:
        raise ValueError("probabilities do not sum to 1")
    if choice not in OPTIONS or probabilities[choice] != max(probabilities.values()):
        raise ValueError("choice is not a highest-probability option")
    return probabilities, _unit(confidence, text=text)


def _usage(value):
    if isinstance(value, dict) and all(
            isinstance(value.get(k), int) and not isinstance(value.get(k), bool)
            for k in ("input_tokens", "output_tokens")):
        return {k: value[k] for k in ("input_tokens", "output_tokens")}
    return None


def _parse(body):
    data = json.loads(body)
    item = data["answers"]["timing"]
    if item.get("type") != "choice":
        raise ValueError("answer is not a choice")
    choice = item.get("choice")
    probabilities, confidence = _answer(choice, item["probabilities"], item["confidence"])
    model = data.get("model")
    if not isinstance(model, str) or not model or len(model) > MAX_KEY:
        raise ValueError("answering model missing or invalid")
    return model, choice, probabilities, confidence, _usage(data.get("usage"))


def request_opinion(review, *, api_key, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL, opener=_open):
    """Ask Jev once; any transport or contract failure is an explicit unavailable result."""
    if not api_key:
        raise ValueError("TYPESAFE_API_KEY is required unless --dry-run is used")
    if not api_key.isprintable() or any(c.isspace() for c in api_key):
        raise ValueError("TYPESAFE_API_KEY contains whitespace or control characters")
    url = endpoint(base_url)
    payload = build_request(review, model=model)
    minimum = min_confidence(review)
    body, digest = encode_request(payload)
    result = {
        "tool": "timing_opinion", "provider": "typesafe", "status": "unavailable",
        "instrument": review["instrument"], "snapshot_id": review["snapshot_id"],
        "asof_ms": review["asof_ms"], "requested_model": model, "model": None,
        "input_sha256": digest, "min_confidence": str(minimum),
        "choice": None, "probabilities": None, "confidence": None, "band": None,
        "effective_opinion": None, "advisory": True, "order_authorized": False,
    }
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": "kis-hl-trading-system"})
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return {**result, "reason": f"HTTP {exc.code}"}
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
        # Report only the exception type; messages can quote request headers.
        return {**result, "reason": f"transport error: {type(exc).__name__}"}
    if len(raw) > MAX_RESPONSE_BYTES:
        return {**result, "reason": "invalid response: body too large"}
    try:
        answered, choice, probabilities, confidence, usage = _parse(raw)
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation, RecursionError) as exc:
        return {**result, "reason": f"invalid response: {exc}"}
    band, effective = gate(choice, confidence, minimum)
    return {**result, "status": "available", "model": answered, "choice": choice,
            "probabilities": {k: str(v) for k, v in probabilities.items()},
            "confidence": str(confidence), "band": band, "effective_opinion": effective,
            "usage": usage}


def check_attached(opinion, *, instrument, snapshot_id):
    """Validate an opinion attached to a strategy decision; it stays advisory."""
    if not isinstance(opinion, dict) or opinion.get("tool") != "timing_opinion":
        raise ValueError("Timing opinion must be a strategy opinion result")
    if opinion.get("order_authorized") is not False:
        raise ValueError("Timing opinion cannot carry order authority")
    if opinion.get("instrument") != instrument or opinion.get("snapshot_id") != snapshot_id:
        raise ValueError("Timing opinion is bound to a different instrument or snapshot")
    status = opinion.get("status")
    if status == "unavailable":
        if opinion.get("effective_opinion") is not None:
            raise ValueError("Timing opinion is unavailable but reports an opinion")
        return None
    if status != "available" or opinion.get("provider") != "typesafe" or opinion.get("advisory") is not True:
        raise ValueError("Timing opinion status, provider or advisory flag is invalid")
    try:
        _, confidence = _answer(opinion.get("choice"), opinion.get("probabilities"),
                                opinion.get("confidence"), text=True)
        minimum = min_confidence(opinion)
    except (ValueError, KeyError, TypeError):
        raise ValueError("Timing opinion probabilities or confidence are invalid") from None
    if gate(opinion["choice"], confidence, minimum) != (opinion.get("band"), opinion.get("effective_opinion")):
        raise ValueError("Timing opinion band or effective opinion is inconsistent with its confidence gate")
    return opinion["effective_opinion"]
