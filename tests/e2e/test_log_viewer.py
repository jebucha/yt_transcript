"""E2E log viewer tests (T-LOG-VIEWER-008 .. 017).

Reuses the in-process uvicorn + stub-chain harness pattern from
test_ui.py. Synthetic log entries are emitted in-process through the app's
own logger, which shares the in-memory log bus with the running server.

Run:  python -m pytest tests/e2e/ -q
(One-time:  python -m playwright install chromium)
"""

import threading

import pytest
from playwright.sync_api import sync_playwright

from app import chain as chain_mod
from app import log as applog
from app.chain import FetchChain
from app.errors import UpstreamFailureError
from tests.e2e.test_ui import StubChain, _free_port, _wait_ready


class FailingFetcher:
    """A fetcher that always raises the given error (like the real fetchers,
    it raises with a safe, app-constructed message)."""

    def __init__(self, error):
        self._error = error

    def __call__(self, video_id, requested_language):
        raise self._error


def _log_synthetic(event, **fields):
    """Log an entry in-process; it flows through the shared bus to the SSE
    stream of the running server (and to the browser's panel)."""
    applog.get_logger().info(event, **fields)


def _wait_panel_text(page, text, timeout=10_000):
    page.wait_for_function(
        "(t) => document.getElementById('log-panel').textContent.includes(t)",
        arg=text,
        timeout=timeout,
    )


def _panel_line(page, marker):
    text = page.locator("#log-panel").inner_text()
    lines = [ln for ln in text.splitlines() if marker in ln]
    if not lines:
        pytest.fail(f"no log panel line containing {marker!r}")
    return lines[0]


# --- fixtures -----------------------------------------------------------------


@pytest.fixture(scope="module")
def server():
    from app import main as app_main
    import uvicorn

    stub = StubChain()
    original_chain = chain_mod.default_chain
    chain_mod.default_chain = stub

    port = _free_port()
    config = uvicorn.Config(app_main.app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    _wait_ready(port)

    yield {"port": port, "stub": stub, "base": f"http://127.0.0.1:{port}"}

    uvicorn_server.should_exit = True
    thread.join(timeout=10)
    chain_mod.default_chain = original_chain


@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(autouse=True)
def _reset_stub(server):
    """Fresh stub state (scenario + call log) for every test."""
    server["stub"].calls = []
    server["stub"].set_success()
    yield


@pytest.fixture()
def browser(playwright):
    b = playwright.chromium.launch()
    yield b
    b.close()


@pytest.fixture()
def page(browser, server):
    context = browser.new_context(viewport={"width": 1024, "height": 640})
    pg = context.new_page()
    pg.goto(server["base"] + "/")
    yield pg
    context.close()


def _fetch(page, url):
    page.fill("#url-input", url)
    page.click("#fetch-btn")


# --- T-LOG-VIEWER-008 .. 010: panel and toggle --------------------------------


def test_panel_hidden_by_default(page):
    assert page.locator("#log-panel").is_hidden()
    assert page.locator("#logs-toggle").inner_text() == "Show logs"


def test_show_logs_reveals_panel(page):
    page.click("#logs-toggle")

    assert not page.locator("#log-panel").is_hidden()
    assert page.locator("#logs-toggle").inner_text() == "Hide logs"


def test_hide_logs_hides_panel(page):
    page.click("#logs-toggle")
    page.click("#logs-toggle")

    assert page.locator("#log-panel").is_hidden()
    assert page.locator("#logs-toggle").inner_text() == "Show logs"


# --- T-LOG-VIEWER-011: entries while hidden -----------------------------------


def test_entries_while_hidden_still_available(page):
    assert page.locator("#log-panel").is_hidden()

    # Logged while the panel is hidden (unknown event -> key=value fallback).
    _log_synthetic("hidden_entry_probe", tag="while_hidden")
    _wait_panel_text(page, "hidden_entry_probe")

    page.click("#logs-toggle")

    assert not page.locator("#log-panel").is_hidden()
    text = page.locator("#log-panel").inner_text()
    assert "hidden_entry_probe" in text
    assert "tag=while_hidden" in text


# --- T-LOG-VIEWER-012: fetch failure with cause --------------------------------


def test_fetch_failure_shown_with_cause(page, server, monkeypatch):
    fetcher = FailingFetcher(UpstreamFailureError("connection to upstream timed out"))
    monkeypatch.setattr(
        chain_mod, "default_chain",
        FetchChain(primary=fetcher, fallback=fetcher),
    )

    page.click("#logs-toggle")
    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    _wait_panel_text(page, "connection to upstream timed out")
    line = _panel_line(page, "connection to upstream timed out")
    # identifies the failed attempt: video ID, fetcher source, error code
    # — together with the failure's cause detail
    assert "dQw4w9WgXcQ" in line
    assert "via primary" in line
    assert "UPSTREAM_FAILURE" in line


# --- T-LOG-VIEWER-013: save failure with path ----------------------------------


def test_save_failure_shown_with_path(page, server, tmp_path, monkeypatch):
    # Point TRANSCRIPT_DIR at a path under an existing file so the write
    # deterministically fails (the directory cannot exist).
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a directory")
    target_dir = blocker / "sub"
    monkeypatch.setenv("TRANSCRIPT_DIR", str(target_dir))

    server["stub"].set_success()
    page.click("#logs-toggle")
    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    page.wait_for_selector("#result:not([hidden])", timeout=10_000)

    _wait_panel_text(page, "transcript save failed")
    line = _panel_line(page, "transcript save failed")
    expected_path = str(target_dir / "test_video_title.txt")
    assert expected_path in line
    assert "Not a directory" in line


# --- T-LOG-VIEWER-014: unknown event fallback ----------------------------------


def test_unknown_event_fallback(page):
    page.click("#logs-toggle")

    _log_synthetic("synthetic_unknown_event", alpha="one", beta=2)
    _wait_panel_text(page, "synthetic_unknown_event")

    line = _panel_line(page, "synthetic_unknown_event")
    assert "alpha=one" in line
    assert "beta=2" in line


# --- T-LOG-VIEWER-015: panel grows in chronological order ----------------------


def test_panel_grows_with_entries(page):
    page.click("#logs-toggle")

    _log_synthetic("order_event", seq=1)
    _log_synthetic("order_event", seq=2)
    _log_synthetic("order_event", seq=3)
    _wait_panel_text(page, "seq=3")

    text = page.locator("#log-panel").inner_text()
    assert text.find("seq=1") < text.find("seq=2") < text.find("seq=3")
    # remains scrollable within a bounded area (page layout intact)
    box = page.locator("#log-panel")
    assert box.evaluate("el => getComputedStyle(el).overflowY") in ("auto", "scroll")
    assert box.evaluate("el => getComputedStyle(el).maxHeight") != "none"


# --- T-LOG-VIEWER-016: display cap ----------------------------------------------


def test_panel_display_cap(page):
    page.click("#logs-toggle")

    for i in range(210):
        _log_synthetic("cap_event", seq=f"e{i:03d}")
    _wait_panel_text(page, "e209", timeout=20_000)

    panel = page.locator("#log-panel")
    assert panel.evaluate("el => el.childNodes.length") == 200
    text = panel.inner_text()
    assert "e209" in text
    # the oldest lines have been dropped
    assert "e000" not in text
    assert "e009" not in text


# --- T-LOG-VIEWER-017: markup-like text is plain text ----------------------------


def test_markup_rendered_as_plain_text(page):
    page.click("#logs-toggle")

    markup = "<script>window.__log_viewer_pwned = true;</script>probe-marker"
    _log_synthetic("markup_probe", message=markup)
    _wait_panel_text(page, "window.__log_viewer_pwned")

    # displayed verbatim as plain text...
    assert "<script>" in page.locator("#log-panel").inner_text()
    # ...not rendered or executed
    assert page.locator("#log-panel script").count() == 0
    assert page.evaluate("() => window.__log_viewer_pwned") is None
