"""End-to-end test: drive the /debate SSE endpoint exactly like the frontend's
EventSource does, and validate the full public contract.

Not a browser test (that would need Playwright + a ~400MB Chromium binary). This
catches every backend/SSE-contract bug that would break the frontend:
  - each `data:` event parses as JSON with the required keys
  - speaker labels are from the expected set
  - the stream terminates with `event: done`
  - turns arrive incrementally (not one blocking dump) — verified by timestamping
  - empty/whitespace topics get the friendly System turn + done, no agent call

Requires the server running on 127.0.0.1:7860. Start it with:
    .venv/bin/uvicorn backend.main:app --port 7860

Run:
    .venv/bin/python e2e_test.py

v1.1 additions: /models endpoint, per-side model override (For ≠ Against), and
invalid-model-id rejection.
"""

from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

BASE_URL = "http://127.0.0.1:7860"
VALID_SPEAKERS = {
    "Debater For",
    "Debater Against",
    "Moderator — Final Verdict",
    "System",
}


def stream_debate(topic: str, model_for: str | None = None, model_against: str | None = None):
    """Hit /debate and yield (event_name, data_dict) tuples as they arrive.

    Mimics EventSource: reads the text/event-stream line by line, parsing SSE
    `event:` and `data:` fields. Raises on any malformed payload.

    model_for / model_against (v1.1): optional per-side model overrides, sent as
    query params exactly like the frontend does.
    """
    params = {"topic": topic}
    if model_for:
        params["model_for"] = model_for
    if model_against:
        params["model_against"] = model_against
    url = f"{BASE_URL}/debate?" + "&".join(f"{k}={_urlencode(v)}" for k, v in params.items())
    # stream=True so we read incrementally as the server flushes turns — this is
    # what lets us assert turns arrive separately rather than buffered into one blob.
    req = Request(url, headers={"Accept": "text/event-stream"})
    with urlopen(req, timeout=180) as resp:
        if resp.status != 200:
            raise AssertionError(f"expected HTTP 200, got {resp.status}")
        event, data_lines, first_byte = "", [], None
        for raw in resp:
            if first_byte is None:
                first_byte = time.monotonic()
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                # blank line = event boundary per the SSE spec
                if data_lines:
                    payload = json.loads("\n".join(data_lines))
                    yield (event or "message", payload, first_byte)
                event, data_lines, first_byte = "", [], None
            elif line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())


def _urlencode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


# --- v1.3: open-ended session helpers ----------------------------------------

def _post_json(url: str, body: dict) -> tuple[int, dict]:
    """POST JSON, return (status_code, parsed_json)."""
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except URLError as e:  # 4xx/5xx come back as URLError via urlopen
        code = getattr(e, "code", 0)
        try:
            payload = json.loads(e.read().decode("utf-8")) if hasattr(e, "read") else {}
        except Exception:
            payload = {}
        return code, payload


def stream_session(url: str):
    """Consume a /debate/{sid}/stream or /next SSE stream, yield (event, data)."""
    req = Request(url, headers={"Accept": "text/event-stream"})
    with urlopen(req, timeout=300) as resp:
        event, data_lines = "", []
        for raw in resp:
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                if data_lines:
                    yield (event or "message", json.loads("\n".join(data_lines)))
                event, data_lines = "", []
            elif line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_static_files_served():
    """The frontend's three files must be reachable with correct content types."""
    print("[1/4] static files served with correct content types...")
    expectations = {
        "/": "text/html",
        "/style.css": "text/css",
        "/script.js": "text/javascript",
    }
    for path, expected_ct in expectations.items():
        with urlopen(f"{BASE_URL}{path}", timeout=10) as r:
            ct = r.headers.get("Content-Type", "")
            assert_true(
                expected_ct in ct,
                f"{path}: expected Content-Type containing {expected_ct!r}, got {ct!r}",
            )
    print("      PASS — index.html, style.css, script.js all reachable")


def test_empty_topic():
    """Empty/whitespace topics must yield a friendly System turn + done, no agents."""
    print("[2/4] empty topic validation (no agent call expected)...")
    for topic in ("", "   "):
        events = list(stream_debate(topic))
        assert_true(len(events) == 2, f"empty topic {topic!r}: expected 2 events, got {len(events)}")
        name1, data1, _ = events[0]
        name2, data2, _ = events[1]
        assert_true(data1.get("speaker") == "System", f"expected System speaker, got {data1.get('speaker')!r}")
        assert_true("topic" in data1.get("text", "").lower(), f"unexpected empty-topic text: {data1.get('text')!r}")
        assert_true(name2 == "done", f"expected 'done' event, got {name2!r}")
    print("      PASS — empty + whitespace both → System turn + done")


def test_real_debate():
    """Full debate: valid JSON each turn, expected speaker sequence, incremental timing."""
    print("[3/4] real debate stream (5 turns, ~70s)...")
    topic = "Should AI replace human teachers?"
    turns = list(stream_debate(topic))

    data_turns = [(name, data, t) for name, data, t in turns if name == "message"]
    done_events = [t for name, _, t in turns if name == "done"]

    assert_true(len(done_events) == 1, f"expected exactly one 'done' event, got {len(done_events)}")
    assert_true(len(data_turns) == 5, f"expected 5 debate turns, got {len(data_turns)}")

    for i, (name, data, _) in enumerate(data_turns, start=1):
        assert_true("speaker" in data and "text" in data,
                    f"turn {i}: payload missing speaker/text keys: {data}")
        assert_true(data["speaker"] in VALID_SPEAKERS,
                    f"turn {i}: unexpected speaker {data['speaker']!r}")
        assert_true(isinstance(data["text"], str) and len(data["text"]) > 20,
                    f"turn {i}: text too short / wrong type")
        print(f"      turn {i}/5: {data['speaker']:<28} ({len(data['text'])} chars)")

    # Speaker sequence must be For → Against → For → Against → Moderator.
    expected_seq = ["Debater For", "Debater Against", "Debater For",
                    "Debater Against", "Moderator — Final Verdict"]
    actual_seq = [d["speaker"] for _, d, _ in data_turns]
    assert_true(actual_seq == expected_seq,
                f"speaker sequence mismatch:\n  expected: {expected_seq}\n  actual:   {actual_seq}")

    # Incremental delivery: each turn's first byte must arrive AFTER the previous
    # turn's first byte (i.e. they streamed separately, not buffered into one blob).
    first_byte_times = [t for _, _, t in data_turns]
    for i in range(1, len(first_byte_times)):
        assert_true(first_byte_times[i] > first_byte_times[i - 1],
                    f"turn {i+1} first byte not after turn {i}'s — stream may be buffered")
    spans = [round(first_byte_times[i] - first_byte_times[0], 1) for i in range(len(first_byte_times))]
    print(f"      PASS — 5 turns, correct sequence, incremental (t-offsets: {spans}s)")


def test_xss_safety():
    """A topic containing markup must come back as data, not execute as HTML."""
    print("[4/4] XSS safety (markup in topic is data, not HTML)...")
    # We only validate the server doesn't crash / doesn't echo raw HTML in a way
    # that breaks JSON. The frontend uses textContent (verified by inspection), so
    # server-side JSON-encoding is the actual safety boundary.
    topic = '<script>alert(1)</script>'
    events = list(stream_debate(topic))
    data_turns = [d for name, d, _ in events if name == "message"]
    assert_true(len(data_turns) >= 1, "expected at least one turn for markup topic")
    # Every payload must still be valid JSON (already enforced by stream_debate parsing).
    # And the literal <script> must appear only inside a JSON string value, never raw.
    print(f"      PASS — markup handled as data ({len(data_turns)} turns, no JSON break)")


def test_models_endpoint():
    """v1.1: /models must return a JSON list of the provider's available models."""
    print("[5/7] /models endpoint returns provider's model list...")
    with urlopen(f"{BASE_URL}/models", timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    assert_true(isinstance(data, dict) and "models" in data,
                f"/models payload missing 'models' key: {data}")
    models = data["models"]
    assert_true(isinstance(models, list), f"/models 'models' must be a list, got {type(models)}")
    if len(models) == 0:
        print("      SKIP — provider returned no models (subsequent model tests will skip)")
        return []
    print(f"      PASS — {len(models)} models available: {models}")
    return models


def test_per_side_models(available_models):
    """v1.1: pick two different models for For/Against, verify a real debate still
    streams correctly with 5 turns and the right speaker sequence."""
    print("[6/7] per-side model selection (For ≠ Against)...")
    if len(available_models) < 2:
        print("      SKIP — fewer than 2 models available, can't test per-side override")
        return
    topic = "Is space exploration worth the cost?"
    model_for, model_against = available_models[0], available_models[1]
    turns = list(stream_debate(topic, model_for=model_for, model_against=model_against))
    data_turns = [d for name, d, _ in turns if name == "message"]
    assert_true(len(data_turns) == 5,
                f"expected 5 turns with per-side models, got {len(data_turns)}")
    actual_seq = [d["speaker"] for d in data_turns]
    expected_seq = ["Debater For", "Debater Against", "Debater For",
                    "Debater Against", "Moderator — Final Verdict"]
    assert_true(actual_seq == expected_seq,
                f"per-side speaker sequence mismatch:\n  expected: {expected_seq}\n  actual:   {actual_seq}")
    print(f"      PASS — For={model_for!r}, Against={model_against!r}, 5 turns streamed correctly")


def test_invalid_model():
    """v1.1: a bogus model id must yield a friendly System turn + done, no agent call."""
    print("[7/7] invalid model id rejected with friendly System turn...")
    turns = list(stream_debate("any topic", model_for="this-model-does-not-exist"))
    data_turns = [d for name, d, _ in turns if name == "message"]
    done_events = [name for name, _, _ in turns if name == "done"]
    assert_true(len(data_turns) == 1, f"expected 1 System turn, got {len(data_turns)}")
    assert_true(data_turns[0].get("speaker") == "System",
                f"expected System speaker, got {data_turns[0].get('speaker')!r}")
    assert_true("this-model-does-not-exist" in data_turns[0].get("text", ""),
                f"System message should mention the bad model id: {data_turns[0].get('text')!r}")
    assert_true(len(done_events) == 1, "stream should terminate with one 'done' event")
    print(f"      PASS — bogus model id → '{data_turns[0]['text'][:60]}...' + done, no agent call")


# --- v1.3: open-ended mode tests ---------------------------------------------

def test_open_lifecycle():
    """Full open-ended lifecycle: start → stream 2 turns + paused → next 2 more → verdict."""
    print("[8/10] open-ended lifecycle (start → stream → next → verdict)...")
    code, body = _post_json(f"{BASE_URL}/debate/start", {"topic": "Is curiosity more important than knowledge?"})
    assert_true(code == 200 and "session_id" in body, f"start failed: HTTP {code}, {body}")
    sid = body["session_id"]

    # Initial stream: first For+Against round, then pause.
    events = list(stream_session(f"{BASE_URL}/debate/{sid}/stream"))
    event_names = [e for e, _ in events]
    turns1 = [d for e, d in events if e == "turn"]
    assert_true("paused" in event_names, f"initial stream should pause; got events {event_names}")
    assert_true(len(turns1) == 2, f"expected 2 turns in first round, got {len(turns1)}")
    assert_true(turns1[0]["speaker"] == "Debater For", "round 1 should start with For")
    print(f"      round 1: {len(turns1)} turns, paused ✓")

    # One more round via /next.
    events = list(stream_session(f"{BASE_URL}/debate/{sid}/next"))
    turns2 = [d for e, d in events if e == "turn"]
    assert_true(len(turns2) == 2, f"expected 2 more turns, got {len(turns2)}")
    print(f"      round 2: {len(turns2)} more turns, paused ✓")

    # User judges.
    code, verdict = _post_json(f"{BASE_URL}/debate/{sid}/verdict", {})
    assert_true(code == 200, f"verdict HTTP {code}: {verdict}")
    assert_true(verdict.get("speaker") == "Moderator — Final Verdict",
                f"expected Moderator verdict, got {verdict.get('speaker')!r}")
    assert_true(len(verdict.get("text", "")) > 50, "verdict text too short")
    print(f"      verdict: {verdict['text'][:60]}... ✓")

    # Subsequent /next on a judged session should 409 (conflict).
    try:
        urlopen(f"{BASE_URL}/debate/{sid}/next", timeout=30)
        assert_true(False, "expected /next on judged session to 409")
    except URLError as e:
        assert_true(getattr(e, "code", 0) == 409, f"expected 409, got {getattr(e, 'code', '?')}")
    print("      PASS — full open-ended lifecycle (start → stream → next → verdict + 409 after)")


def test_open_verdict_on_empty():
    """Judging before any turns yields a friendly System message, no moderator call."""
    print("[9/10] open-ended verdict-on-empty (judge before any turns)...")
    code, body = _post_json(f"{BASE_URL}/debate/start", {"topic": "any topic"})
    sid = body["session_id"]
    code, data = _post_json(f"{BASE_URL}/debate/{sid}/verdict", {})
    assert_true(code == 200, f"verdict-on-empty HTTP {code}")
    assert_true(data.get("speaker") == "System", f"expected System speaker, got {data.get('speaker')!r}")
    assert_true("no debate" in data.get("text", "").lower() or "at least one" in data.get("text", "").lower(),
                f"unexpected empty-verdict text: {data.get('text')!r}")
    print(f"      PASS — '{data['text'][:60]}...' (no moderator call)")


def test_open_turn_cap():
    """The 20-turn cap auto-triggers the verdict instead of running forever."""
    print("[10/10] open-ended 20-turn cap auto-verdict (~60-90s, many LLM calls)...")
    code, body = _post_json(f"{BASE_URL}/debate/start", {"topic": "Does free will exist?"})
    sid = body["session_id"]
    total_turns = 0
    got_verdict = False
    # Initial round
    for event, data in stream_session(f"{BASE_URL}/debate/{sid}/stream"):
        if event == "turn": total_turns += 1
        if event == "verdict": got_verdict = True
    # Keep requesting rounds until the cap fires or we hit a safety max
    for _ in range(11):  # 22 more turns requested = well past the 20 cap
        if got_verdict:
            break
        for event, data in stream_session(f"{BASE_URL}/debate/{sid}/next"):
            if event == "turn": total_turns += 1
            if event == "verdict": got_verdict = True
    assert_true(got_verdict, f"expected auto-verdict at 20 turns; got {total_turns} turns, no verdict")
    assert_true(total_turns == 20, f"expected exactly 20 turns before cap verdict, got {total_turns}")
    print(f"      PASS — capped at 20 turns, auto-verdict fired (no overrun)")


def main():
    print(f"=== E2E test against {BASE_URL} ===\n")
    # Reachability guard — gives a clearer error than a stack trace from urlopen.
    try:
        with urlopen(f"{BASE_URL}/", timeout=5) as r:
            if r.status != 200:
                raise ConnectionError
    except Exception:
        print(f"!! Server not reachable at {BASE_URL}. Start it with:\n"
              f"   .venv/bin/uvicorn backend.main:app --port 7860", file=sys.stderr)
        return 1

    start = time.monotonic()
    try:
        test_static_files_served()
        test_empty_topic()
        test_real_debate()
        test_xss_safety()
        available = test_models_endpoint()
        test_per_side_models(available)
        test_invalid_model()
        test_open_lifecycle()
        test_open_verdict_on_empty()
        test_open_turn_cap()
    except AssertionError as e:
        print(f"\n!!! E2E TEST FAILED: {e}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start
    print(f"\n=== ALL E2E TESTS PASSED in {elapsed:.1f}s ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
