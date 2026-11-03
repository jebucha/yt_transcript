"""Log viewer: in-memory log bus, tee stream, and the /api/logs SSE endpoint.

Test Requirement IDs:
  T-LOG-VIEWER-001 .. 007 (endpoint, replay, stdout behavior)
"""

import json
import threading
import time

import pytest
from starlette.testclient import TestClient

from app import chain as chain_mod
from app import log as applog
from app import logbus
from app.chain import FetchResult
from app.main import create_app


# --- 1. LogBus ----------------------------------------------------------------


def test_multi_thread_publish_preserves_entry_order():
    """Publishes from two threads, forced into a strict global alternation
    outside the bus, must come back in that exact order."""
    bus = logbus.LogBus()
    steps = 20
    lock = threading.Lock()
    state = {"turn": 0}

    def worker(tag):
        for i in range(steps):
            while True:
                with lock:
                    if state["turn"] % 2 == (0 if tag == "a" else 1):
                        state["turn"] += 1
                        break
                time.sleep(0.001)
            bus.publish({"event": f"{tag}{i}"})

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in "ab"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = [f"{tag}{i}" for i in range(steps) for tag in "ab"]
    assert [e["event"] for e in bus.snapshot()] == expected


def test_multi_thread_publish_no_loss_within_cap():
    """Four threads publish concurrently: every entry visible in the capped
    window is present exactly once, in per-thread order."""
    bus = logbus.LogBus()
    per_thread = 300

    def worker(thread_id):
        for i in range(per_thread):
            bus.publish({"event": "multi", "thread": thread_id, "seq": i})

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = bus.snapshot()
    assert len(snap) == logbus.BUFFER_SIZE
    for tid in range(4):
        seqs = [e["seq"] for e in snap if e["thread"] == tid]
        assert seqs == sorted(seqs), f"thread {tid} out of order"
        assert len(seqs) == len(set(seqs)), f"thread {tid} has duplicates"


def test_snapshot_capped_at_buffer_size():
    bus = logbus.LogBus()
    for i in range(300):
        bus.publish({"event": "filler", "seq": i})

    snap = bus.snapshot()
    assert len(snap) == logbus.BUFFER_SIZE
    assert [e["seq"] for e in snap] == list(
        range(300 - logbus.BUFFER_SIZE, 300)
    )


def test_slow_subscriber_drops_without_blocking_publisher():
    bus = logbus.LogBus()
    q = bus.subscribe()
    # Fill the subscriber's queue so it is full and (by definition) not being
    # drained.
    for _ in range(logbus.SUBSCRIBER_QUEUE_SIZE):
        try:
            q.put_nowait({"event": "filler"})
        except Exception:
            break

    done = threading.Event()

    def publish():
        bus.publish({"event": "dropped_ok"})
        done.set()

    t = threading.Thread(target=publish)
    t.start()
    assert done.wait(timeout=2.0), "publish blocked on a full subscriber queue"
    t.join()
    # The entry still reached the ring buffer; only the fan-out was dropped.
    assert any(e["event"] == "dropped_ok" for e in bus.snapshot())


# --- 2. TeeStream --------------------------------------------------------------


def test_tee_reaches_stdout_and_bus(capsys):
    bus = logbus.LogBus()
    applog.setup_logging(stream=logbus.TeeStream(bus))

    applog.get_logger().info("tee_probe", n=1)

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "tee_probe"
    assert entry["n"] == 1
    # The same entry reached the bus.
    assert [e["event"] for e in bus.snapshot()] == ["tee_probe"]
    assert bus.snapshot()[0]["n"] == 1


def test_tee_forwards_non_json_lines_to_stdout_only(capsys):
    bus = logbus.LogBus()
    tee = logbus.TeeStream(bus)

    tee.write("not a log entry\n")

    assert "not a log entry" in capsys.readouterr().out
    assert bus.snapshot() == []


def test_default_logging_uses_tee_to_default_bus(monkeypatch):
    """setup_logging() with no explicit stream must route entries to
    logbus.DEFAULT_BUS (resolved at setup time)."""
    fresh = logbus.LogBus()
    monkeypatch.setattr(logbus, "DEFAULT_BUS", fresh)
    applog.setup_logging()

    applog.get_logger().info("default_tee_probe")

    assert [e["event"] for e in fresh.snapshot()] == ["default_tee_probe"]


# --- 3. Logging unaffected by the log viewer ----------------------------------


def test_stdout_without_subscribers(capsys):
    """T-LOG-VIEWER-006"""
    applog.setup_logging()

    applog.get_logger().info("stdout_probe", tag="none")

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "stdout_probe"
    assert entry["tag"] == "none"
    assert entry["level"] == "info"
    assert "timestamp" in entry


def test_stdout_with_subscribers(capsys):
    """T-LOG-VIEWER-007"""
    applog.setup_logging()
    q = logbus.DEFAULT_BUS.subscribe()
    try:
        applog.get_logger().info("stdout_probe", tag="some")

        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # exactly once on stdout, in the established single-JSON-line format
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "stdout_probe"
        assert entry["tag"] == "some"
        # and exactly one copy to the subscriber
        delivered = []
        while not q.empty():
            delivered.append(q.get_nowait())
        assert len(delivered) == 1
        assert delivered[0]["event"] == "stdout_probe"
    finally:
        logbus.DEFAULT_BUS.unsubscribe(q)


# --- 4. GET /api/logs (SSE) -----------------------------------------------------


@pytest.fixture()
def bus(monkeypatch):
    """A fresh default bus: the default tee (reconfigured here) and the
    /api/logs endpoint both resolve logbus.DEFAULT_BUS at call time."""
    fresh = logbus.LogBus()
    monkeypatch.setattr(logbus, "DEFAULT_BUS", fresh)
    applog.setup_logging()
    return fresh


def _sse_events(response):
    """One persistent iterator yielding parsed JSON payloads of SSE data
    lines (a response's stream may only be iterated from one iterator)."""
    for raw in response.iter_lines():
        line = raw.strip()
        if line.startswith("data: "):
            yield json.loads(line[len("data: "):])


def _read_until(events, event_name, max_events=40):
    """Blocking-read SSE events until event_name arrives (bounded)."""
    for _ in range(max_events):
        entry = next(events)
        if entry["event"] == event_name:
            return entry
    pytest.fail(f"event {event_name!r} not received within {max_events} SSE events")


def test_live_event_delivered(bus):
    """T-LOG-VIEWER-001"""
    client = TestClient(create_app())
    with client:
        with client.stream("GET", "/api/logs") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = _sse_events(response)
            # The replay delivers the lifespan startup event first.
            startup = next(events)
            assert startup["event"] == "server_started"

            applog.get_logger().info("live_probe_event", marker="lv001")

            entry = _read_until(events, "live_probe_event")
            assert entry["marker"] == "lv001"
            assert entry["level"] == "info"
            assert "timestamp" in entry


def test_history_replayed_on_connect(bus):
    """T-LOG-VIEWER-004"""
    for i in range(3):
        applog.get_logger().info("replay_event", seq=i)

    client = TestClient(create_app())
    with client:
        with client.stream("GET", "/api/logs") as response:
            events = _sse_events(response)
            applog.get_logger().info("replay_live_event")

            entries = []
            for _ in range(40):
                entries.append(next(events))
                if entries[-1]["event"] == "replay_live_event":
                    break
            live_idx = next(
                i for i, e in enumerate(entries) if e["event"] == "replay_live_event"
            )
            history_idx = [
                i for i, e in enumerate(entries) if e["event"] == "replay_event"
            ]
            # Recent history, chronological, before any newer live event.
            assert [e["seq"] for e in entries if e["event"] == "replay_event"] == [0, 1, 2]
            assert history_idx and all(i < live_idx for i in history_idx)


def test_buffer_cap(bus):
    """T-LOG-VIEWER-005"""
    total = logbus.BUFFER_SIZE + 50
    for i in range(total):
        applog.get_logger().info("cap_event", seq=i)
    # The ring buffer itself is capped.
    assert len(bus.snapshot()) == logbus.BUFFER_SIZE

    client = TestClient(create_app())
    with client:
        with client.stream("GET", "/api/logs") as response:
            events_iter = _sse_events(response)
            # Exactly one full buffer of replayed data lines.
            events = [next(events_iter) for _ in range(logbus.BUFFER_SIZE)]
            received = {e["seq"] for e in events if e.get("event") == "cap_event"}
            # The oldest 50 have been pushed out of the capped buffer.
            assert not received & set(range(50))
            # Every newer cap event was delivered (a couple of lifecycle and
            # request entries may occupy the rest of the buffer).
            assert set(range(55, total)) <= received
            cap_seq = [e["seq"] for e in events if e.get("event") == "cap_event"]
            assert cap_seq == sorted(cap_seq)


def test_multiple_clients_receive_event(bus):
    """T-LOG-VIEWER-002"""
    client = TestClient(create_app())
    with client:
        with client.stream("GET", "/api/logs") as r1, client.stream(
            "GET", "/api/logs"
        ) as r2:
            events1 = _sse_events(r1)
            events2 = _sse_events(r2)
            applog.get_logger().info("multi_client_probe")
            e1 = _read_until(events1, "multi_client_probe")
            e2 = _read_until(events2, "multi_client_probe")
            assert e1["event"] == e2["event"] == "multi_client_probe"


class _FakeChain:
    """Stands in for chain_mod.default_chain (tests/test_api.py pattern)."""

    def __init__(self):
        self.calls = []

    async def run(self, url):
        self.calls.append(url)
        return FetchResult(
            text="hello world",
            video_id="dQw4w9WgXcQ",
            title="A Title",
            language="en",
            source="primary",
        )


def test_log_stream_does_not_affect_fetch(bus, monkeypatch):
    """T-LOG-VIEWER-003"""
    fake = _FakeChain()
    monkeypatch.setattr(chain_mod, "default_chain", fake)
    client = TestClient(create_app())
    with client:
        with client.stream("GET", "/api/logs") as response:
            events = _sse_events(response)
            transcript = client.post(
                "/api/transcript",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
            assert transcript.status_code == 200
            assert transcript.json()["text"] == "hello world"
            assert fake.calls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
            # The stream is still alive after the fetch.
            applog.get_logger().info("post_fetch_probe")
            entry = _read_until(events, "post_fetch_probe")
            assert entry["event"] == "post_fetch_probe"
