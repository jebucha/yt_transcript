"""E2E auto-summarize tests (T-TRANSCRIPT-SUMMARIZATION-043 .. 055).

Same harness as test_summarization.py: an in-process uvicorn with the fetch
chain stubbed and the summarize HTTP dispatch replaced by a recording stub.
The autoSummarize setting is a settings.json file in the module transcript
dir, read per request — tests toggle it on disk (or via the checkbox) and
reload the page. Every test starts from a cleaned directory (no settings, no
leftover transcripts/summaries) so skip-and-show state never leaks between
tests.

Run:  python -m pytest tests/e2e/test_auto_summarize.py -q
(One-time:  python -m playwright install chromium)
"""

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from app import chain as chain_mod
from app import summarize as summarize_mod
from tests.e2e.test_summarization import (
    PROVIDER_CONFIG,
    SUMMARY_TEXT,
    SummarizeStub,
    write_provider_config,
)
from tests.e2e.test_ui import (
    DEFAULT_PAYLOAD,
    StubChain,
    _fetch,
    _free_port,
    _wait_error,
    _wait_ready,
    _wait_result,
)

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DERIVED_NAME = "test_video_title.txt"  # from DEFAULT_PAYLOAD's title

# Files the flows create or seed; wiped before every test.
_TRANSIENT_FILES = (
    "settings.json",
    DERIVED_NAME,
    DERIVED_NAME + ".summary",
    "saved_video.txt",
    "saved_video.txt.summary",
)


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

    config_file = write_provider_config(
        Path(tmp_path_factory.mktemp("provider-config")) / "providers.json"
    )
    transcript_dir = Path(tmp_path_factory.mktemp("transcripts"))
    original_config_env = os.environ.get("PROVIDERS_CONFIG")
    original_transcript_env = os.environ.get("TRANSCRIPT_DIR")
    os.environ["PROVIDERS_CONFIG"] = str(config_file)
    os.environ["TRANSCRIPT_DIR"] = str(transcript_dir)

    port = _free_port()
    config = uvicorn.Config(app_main.app, host="0.0.0.0", port=port,
                            log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    _wait_ready(port)

    yield {
        "port": port,
        "stub": stub,
        "summarize_stub": summarize_stub,
        "config_file": config_file,
        "transcript_dir": transcript_dir,
        "localhost_base": f"http://localhost:{port}",
    }

    uvicorn_server.should_exit = True
    thread.join(timeout=10)
    chain_mod.default_chain = original_chain
    summarize_mod._call_chat_completions = original_dispatch
    if original_config_env is None:
        os.environ.pop("PROVIDERS_CONFIG", None)
    else:
        os.environ["PROVIDERS_CONFIG"] = original_config_env
    if original_transcript_env is None:
        os.environ.pop("TRANSCRIPT_DIR", None)
    else:
        os.environ["TRANSCRIPT_DIR"] = original_transcript_env


@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(autouse=True)
def _reset(server):
    """Fresh stub state and a clean transcript dir for every test."""
    server["stub"].calls = []
    server["stub"].set_success()
    server["summarize_stub"].reset()
    for name in _TRANSIENT_FILES:
        (server["transcript_dir"] / name).unlink(missing_ok=True)
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
    pg.goto(server["localhost_base"] + "/")
    yield pg
    context.close()


# --- helpers -------------------------------------------------------------------


def _enable_auto(server, value=True):
    """Persist the autoSummarize setting on disk (the app reads it per
    request, so a page reload picks it up without a restart). Written via
    temp file + os.replace so the write can never be caught mid-truncate
    by the page's initial settings read."""
    directory = server["transcript_dir"]
    tmp = directory / "settings.json.tmp"
    tmp.write_text(json.dumps({"autoSummarize": value}), encoding="utf-8")
    os.replace(tmp, directory / "settings.json")


def _wait_picker(page):
    # The picker lives in #result, hidden before a transcript is displayed —
    # wait for the options to exist, not to be visible.
    page.wait_for_function(
        "() => document.querySelectorAll('#provider-picker option').length > 0",
        timeout=10_000,
    )


def _wait_auto_checked(page, checked=True):
    page.wait_for_function(
        "() => document.getElementById('auto-summarize').checked === "
        + ("true" if checked else "false"),
        timeout=10_000,
    )


def _wait_summary_panel(page):
    page.wait_for_selector("#summary-panel:not([hidden])", timeout=10_000)


def _wait_auto_note(page):
    page.wait_for_selector("#auto-summarize-note:not([hidden])", timeout=10_000)


def _summarize_bodies(page):
    """Attach a /api/summarize request-body listener; returns the list."""
    bodies = []

    def on_request(request):
        if (
            request.method == "POST"
            and urlparse(request.url).path == "/api/summarize"
        ):
            bodies.append(request.post_data_json)

    page.on("request", on_request)
    return bodies


def _settings_json(server):
    return json.loads(
        (server["transcript_dir"] / "settings.json").read_text(encoding="utf-8")
    )


# --- T-TRANSCRIPT-SUMMARIZATION-043 .. 045, 055: the toggle control -------------


def test_checkbox_reflects_saved_setting_on_load(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-043"""
    _enable_auto(server)
    page.reload()
    _wait_picker(page)
    _wait_auto_checked(page, True)

    assert page.locator("#auto-summarize").is_checked()
    # markup check for task 2.1: the subdued note element exists and is
    # hidden while nothing has failed
    assert page.locator("#auto-summarize-note").count() == 1
    assert page.locator("#auto-summarize-note").is_hidden()


def test_toggle_persists_across_reload(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-044"""
    server["stub"].set_success()
    # The checkbox sits next to the summarize controls: display a transcript
    # (auto is off, so nothing fires), then toggle the checkbox.
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    assert not (server["transcript_dir"] / "settings.json").exists()

    page.click("#auto-summarize")
    page.wait_for_function(
        "() => fetch('/api/settings')"
        ".then(r => r.json()).then(d => d.autoSummarize === true)",
        timeout=10_000,
    )
    assert _settings_json(server) == {"autoSummarize": True}

    page.reload()
    _wait_picker(page)
    _wait_auto_checked(page, True)
    assert page.locator("#auto-summarize").is_checked()


def test_auto_checkbox_disabled_without_providers(page, server, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-045"""
    monkeypatch.setenv(
        "PROVIDERS_CONFIG", str(server["config_file"].parent / "missing.json")
    )
    with page.expect_response(
        lambda r: urlparse(r.url).path == "/api/providers", timeout=10_000
    ):
        page.reload()
    # give the load's DOM update a moment, then the checkbox (whose markup
    # starts disabled) stays disabled: no providers means no target
    page.wait_for_timeout(500)
    assert page.locator("#provider-picker option").count() == 0
    assert page.locator("#auto-summarize").is_disabled()


def test_toggle_reverts_on_failed_write(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-055"""
    server["stub"].set_success()
    # No settings file: the persisted value is off (the revert target).
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    assert not (server["transcript_dir"] / "settings.json").exists()

    # Break the settings write path: POSTs get a 500 (recorded), GETs pass
    # through untouched.
    posted = []

    def handler(route):
        if route.request.method == "POST":
            posted.append(route.request.post_data_json)
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"error": {"code": "INTERNAL"}}))
        else:
            route.fallback()

    page.route("**/api/settings", handler)
    page.click("#auto-summarize")
    # The optimistic check fires the write with the new value...
    deadline = time.monotonic() + 10
    while not posted and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert posted == [{"autoSummarize": True}]
    # ...and the checkbox reverts to the last persisted value when the write
    # fails (design D6: the UI never claims a state the server does not hold).
    # The recorded POST above proves the checkbox was checked at click time,
    # so this wait can only be satisfied by the revert.
    _wait_auto_checked(page, False)
    assert not page.locator("#auto-summarize").is_checked()
    assert not (server["transcript_dir"] / "settings.json").exists()


# --- T-TRANSCRIPT-SUMMARIZATION-046 .. 051: auto-fire and skip-and-show ----------


def test_auto_summarize_fires_after_fetch(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-046"""
    server["stub"].set_success()
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    bodies = _summarize_bodies(page)
    _fetch(page, VIDEO_URL)
    _wait_summary_panel(page)  # displayed without a single click

    assert len(bodies) == 1
    body = bodies[0]
    assert body["text"] == DEFAULT_PAYLOAD["text"]
    assert body["name"] == DERIVED_NAME
    assert body["provider"] == "alpha"  # the picker's default pre-selection
    assert body["model"] == "model-a1"
    assert page.locator("#summary-text").inner_text() == SUMMARY_TEXT


def test_auto_summarize_shows_busy_state(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-047"""
    server["stub"].set_success()
    server["summarize_stub"].delay = 1.0  # an observable in-flight window
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    _fetch(page, VIDEO_URL)
    # the auto request is in flight: button, picker and checkbox disabled,
    # spinner shown
    page.wait_for_selector("#summarize-spinner:not([hidden])", timeout=10_000)
    assert page.locator("#summarize-btn").is_disabled()
    assert page.locator("#provider-picker").is_disabled()
    assert page.locator("#auto-summarize").is_disabled()

    _wait_summary_panel(page)
    # restored when the response arrives
    page.wait_for_function(
        "() => !document.getElementById('summarize-btn').disabled"
        " && !document.getElementById('auto-summarize').disabled",
        timeout=10_000,
    )
    assert page.locator("#summarize-spinner").is_hidden()


def test_saved_click_does_not_auto_fire(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-048"""
    (server["transcript_dir"] / "saved_video.txt").write_text(
        "Saved body.\n", encoding="utf-8"
    )
    _enable_auto(server)
    page.reload()
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='saved_video.txt']", timeout=10_000
    )

    bodies = _summarize_bodies(page)
    page.click("#saved-list .saved-row[data-name='saved_video.txt']")
    _wait_result(page)

    # the existing saved-summary load runs (404 here: no summary file) and
    # the panel stays hidden; no summarize request is ever sent
    page.wait_for_timeout(500)
    assert bodies == []
    assert server["summarize_stub"].calls == []
    assert page.locator("#summary-panel").is_hidden()


def test_auto_off_fetch_does_not_summarize(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-049"""
    server["stub"].set_success()
    # no settings.json at all: the off-default
    bodies = _summarize_bodies(page)
    _fetch(page, VIDEO_URL)
    _wait_result(page)

    page.wait_for_timeout(500)
    assert bodies == []
    assert page.locator("#summary-panel").is_hidden()
    # the manual flow is unchanged: the click shows the panel
    page.click("#summarize-btn")
    _wait_summary_panel(page)


def test_refetch_with_existing_summary_shows_saved(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-050"""
    (server["transcript_dir"] / (DERIVED_NAME + ".summary")).write_text(
        "The saved summary.", encoding="utf-8"
    )
    server["stub"].set_success()
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    bodies = _summarize_bodies(page)
    _fetch(page, VIDEO_URL)
    _wait_summary_panel(page)

    # skip-and-show: the saved summary is displayed, no summarize call
    assert page.locator("#summary-text").inner_text() == "The saved summary."
    assert bodies == []
    assert server["summarize_stub"].calls == []


def test_refetch_without_summary_auto_fires(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-051"""
    # The transcript file exists from an earlier fetch, but no summary does.
    (server["transcript_dir"] / DERIVED_NAME).write_text(
        "Earlier body.\n", encoding="utf-8"
    )
    server["stub"].set_success()
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    bodies = _summarize_bodies(page)
    _fetch(page, VIDEO_URL)
    _wait_summary_panel(page)

    assert len(bodies) == 1
    assert page.locator("#summary-text").inner_text() == SUMMARY_TEXT


# --- T-TRANSCRIPT-SUMMARIZATION-052 .. 054: subdued failures ---------------------


def test_auto_failure_shows_note_not_banner(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-052"""
    server["stub"].set_success()
    server["summarize_stub"].set_failure("unreachable", "ConnectionError")
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    _fetch(page, VIDEO_URL)
    _wait_auto_note(page)

    # the red banner stays hidden and the note carries the subdued message
    assert page.locator("#error-banner").is_hidden()
    assert "auto-summarize" in page.locator("#auto-summarize-note").inner_text().lower()
    # the summary panel stays hidden, and the manual retry path is enabled
    assert page.locator("#summary-panel").is_hidden()
    assert not page.locator("#summarize-btn").is_disabled()
    # the manual click then succeeds through the banner-free retry path
    server["summarize_stub"].failure = None
    page.click("#summarize-btn")
    _wait_summary_panel(page)


def test_auto_empty_summary_shows_note(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-053"""
    server["stub"].set_success()
    server["summarize_stub"].set_empty_summary()
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    _fetch(page, VIDEO_URL)
    _wait_auto_note(page)

    # a 200 with no summary text is a failure for display: the note shows,
    # never an empty panel, and the banner stays hidden
    assert page.locator("#summary-panel").is_hidden()
    assert page.locator("#summary-text").inner_text() == ""
    assert page.locator("#error-banner").is_hidden()
    assert not page.locator("#summarize-btn").is_disabled()


def test_manual_failure_still_uses_banner(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-054"""
    server["stub"].set_success()
    _enable_auto(server)
    page.reload()
    _wait_picker(page)

    # the auto attempt succeeds first
    _fetch(page, VIDEO_URL)
    _wait_summary_panel(page)

    # with the backend now failing, a manual click keeps the banner path
    server["summarize_stub"].set_failure("unreachable", "ConnectionError")
    page.click("#summarize-btn")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "summarization backend" in message.lower()
    assert page.locator("#summary-text").inner_text() == SUMMARY_TEXT
    assert not page.locator("#summarize-btn").is_disabled()
