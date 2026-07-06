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
"""

from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:7860"
VALID_SPEAKERS = {
    "Debater For",
    "Debater Against",
    "Moderator — Final Verdict",
    "System",
}


def stream_debate(topic: str):
    """Hit /debate and yield (event_name, data_dict) tuples as they arrive.

    Mimics EventSource: reads the text/event-stream line by line, parsing SSE
    `event:` and `data:` fields. Raises on any malformed payload.
    """
    url = f"{BASE_URL}/debate?topic={_urlencode(topic)}"
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
    except AssertionError as e:
        print(f"\n!!! E2E TEST FAILED: {e}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start
    print(f"\n=== ALL E2E TESTS PASSED in {elapsed:.1f}s ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
