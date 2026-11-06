"""E2E log viewer tests (T-LOG-VIEWER-008 .. 020).

Reuses the in-process uvicorn + stub-chain harness pattern from
test_ui.py. Synthetic log entries are emitted in-process through the app's
own logger, which shares the in-memory log bus with the running server.

Run:  python -m pytest tests/e2e/ -q
(One-time:  python -m playwright install chromium)
"""

import os
import threading

import pytest
from playwright.sync_api import sync_playwright

from app import chain as chain_mod
from app import log as applog
from app import summarize as summarize_mod
from app.chain import FetchChain
from app.errors import UpstreamFailureError
from tests.e2e.test_summarization import PROVIDER_CONFIG, SummarizeStub, write_provider_config
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
def server(tmp_path_factory):
    from app import main as app_main
    import uvicorn

    stub = StubChain()
    summarize_stub = SummarizeStub()
    original_chain = chain_mod.default_chain
    chain_mod.default_chain = stub
    original_dispatch = summarize_mod._call_chat_completions
    summarize_mod._call_chat_completions = summarize_stub

    # The same provider-config harness as test_summarization.py: the app
    # reads the config per request, so the summarization tests below can
    # drive real summarize requests without LLM traffic.
    config_file = write_provider_config(
        tmp_path_factory.mktemp("provider-config") / "providers.json",
        PROVIDER_CONFIG,
    )
    original_config_env = os.environ.get("PROVIDERS_CONFIG")
    os.environ["PROVIDERS_CONFIG"] = str(config_file)

    port = _free_port()
    config = uvicorn.Config(app_main.app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    _wait_ready(port)

    yield {
        "port": port,
        "stub": stub,
        "summarize_stub": summarize_stub,
        "base": f"http://127.0.0.1:{port}",
    }

    uvicorn_server.should_exit = True
    thread.join(timeout=10)
    chain_mod.default_chain = original_chain
    summarize_mod._call_chat_completions = original_dispatch
    if original_config_env is None:
        os.environ.pop("PROVIDERS_CONFIG", None)
    else:
        os.environ["PROVIDERS_CONFIG"] = original_config_env


@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(autouse=True)
def _reset_stub(server):
    """Fresh stub state (scenarios + call logs) for every test."""
    server["stub"].calls = []
    server["stub"].set_success()
    server["summarize_stub"].reset()
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


# --- T-LOG-VIEWER-018 .. 019: summary events ----------------------------------


def _fetch_and_summarize(page, server):
    server["stub"].set_success()
    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    page.wait_for_selector("#result:not([hidden])", timeout=10_000)
    page.click("#summarize-btn")


def test_summary_failure_shown_with_cause(page, server):
    server["summarize_stub"].set_failure("http_error", "backend returned HTTP 500")
    page.click("#logs-toggle")
    _fetch_and_summarize(page, server)

    _wait_panel_text(page, "summary failed")
    line = _panel_line(page, "summary failed")
    # identifies the failed summarization (provider, model) together with
    # the failure's cause detail
    assert "alpha" in line
    assert "model-a1" in line
    assert "http_error" in line
    assert "backend returned HTTP 500" in line


def test_summary_success_shown(page, server):
    page.click("#logs-toggle")
    _fetch_and_summarize(page, server)

    _wait_panel_text(page, "summary completed")
    line = _panel_line(page, "summary completed")
    # identifies the completed summarization (provider, model) with its
    # duration
    assert "alpha" in line
    assert "model-a1" in line
    assert "ms" in line


# --- T-LOG-VIEWER-020: panel placement beneath the toggle ------------------------


def test_panel_shown_beneath_toggle(page):
    page.click("#logs-toggle")

    assert not page.locator("#log-panel").is_hidden()

    toggle = page.locator("#logs-toggle")
    panel = page.locator("#log-panel")
    toggle_box = toggle.bounding_box()
    panel_box = panel.bounding_box()
    assert toggle_box is not None, "toggle should be visible when the panel is shown"
    assert panel_box is not None, "panel should have a box once visible"
    # Push-down placement: the panel renders as a row directly beneath the
    # toggle (normal document flow, second header row) — never above or
    # overlapping the toggle.
    assert panel_box["y"] >= toggle_box["y"] + toggle_box["height"]
    # The panel appears without requiring the user to scroll the page.
    assert panel_box["y"] + panel_box["height"] <= page.viewport_size["height"]
