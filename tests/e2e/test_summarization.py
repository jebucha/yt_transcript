"""E2E summarization tests (T-TRANSCRIPT-SUMMARIZATION-025 .. 036, 040).

A real uvicorn instance of the app runs in-process (thread) with the upstream
fetch chain stubbed (as in test_ui.py) and the summarize HTTP dispatch seam
(app/summarize._call_chat_completions) replaced by a recording stub, so no
real LLM traffic happens. The provider config is a temporary file wired in
via PROVIDERS_CONFIG; the app reads it per request, so tests can edit or
remove it between requests.

Run:  python -m pytest tests/e2e/ -q
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
from tests.e2e.test_ui import (
    DEFAULT_PAYLOAD,
    LONG_PAYLOAD,
    StubChain,
    _fetch,
    _free_port,
    _lan_ip,
    _wait_ready,
    _wait_result,
)

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Two providers: the default one (alpha, keyless local backend) with two
# models, and a second one (beta) that carries an apiKey.
PROVIDER_CONFIG = {
    "provider": {
        "alpha": {
            "name": "Alpha Local",
            "options": {"baseURL": "http://127.0.0.1:41411/v1"},
            "models": {"model-a1": "Model A1", "model-a2": "Model A2"},
        },
        "beta": {
            "name": "Beta Remote",
            "options": {
                "baseURL": "http://127.0.0.1:41412/v1",
                "apiKey": "sekret-key-123",
            },
            "models": {"model-b1": "Model B1"},
        },
    },
    "default": "alpha",
}

SUMMARY_TEXT = "This is the summary of the transcript."


def write_provider_config(path: Path, config=PROVIDER_CONFIG) -> Path:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


class SummarizeStub:
    """Recording stand-in for summarize_mod._call_chat_completions.

    Sits *below* summarize_with_provider (the e2e seam, design decision 11),
    so the real function's summary_completed / summary_failed log emission
    still runs while tests control the backend response deterministically.
    """

    def __init__(self):
        self.calls = []
        self.summary = SUMMARY_TEXT
        self.failure = None
        self.delay = 0.0

    def reset(self):
        self.calls = []
        self.summary = SUMMARY_TEXT
        self.failure = None
        self.delay = 0.0

    def set_failure(self, reason, detail):
        self.failure = (reason, detail)

    def set_empty_summary(self):
        """2xx response whose body carries no summary text: the app's real
        summarize_with_provider treats an empty string as a success, so the
        endpoint answers 200 with an empty summary — the UI must defend."""
        self.summary = ""

    def __call__(self, base_url, model, messages, api_key, timeout):
        self.calls.append({
            "base_url": base_url,
            "model": model,
            "messages": messages,
            "api_key": api_key,
            "timeout": timeout,
        })
        if self.delay:
            time.sleep(self.delay)
        if self.failure is not None:
            raise summarize_mod.ProviderCallError(*self.failure)
        return self.summary


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
    lan_ip = _lan_ip()
    config = uvicorn.Config(app_main.app, host="0.0.0.0", port=port, log_level="warning")
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
        "ip_base": f"http://127.0.0.1:{port}",
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
def _reset_stub(server):
    """Fresh stub state (scenario + call logs) for every test."""
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
    """Page served over http://localhost (secure context; clipboard granted)."""
    context = browser.new_context(viewport={"width": 1024, "height": 640})
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = context.new_page()
    pg.goto(server["localhost_base"] + "/")
    yield pg
    context.close()


def _wait_summary_panel(page):
    page.wait_for_selector("#summary-panel:not([hidden])", timeout=10_000)


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


def _click_saved_row(page, name):
    page.click(f"#saved-list .saved-row[data-name='{name}']")
    _wait_result(page)


def _seed_transcript(directory, name, content):
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


# --- T-TRANSCRIPT-SUMMARIZATION-025 .. 029: picker and button ------------------


def test_picker_lists_providers_with_default(page):
    """T-TRANSCRIPT-SUMMARIZATION-025"""
    provider_requests = []

    def on_request(request):
        if urlparse(request.url).path == "/api/providers":
            provider_requests.append(request.url)

    page.on("request", on_request)
    page.reload()
    # The picker lives in #result, which is hidden before a transcript is
    # displayed — wait for the options to exist, not to be visible.
    page.wait_for_function(
        "() => document.querySelectorAll('#provider-picker option').length > 0",
        timeout=10_000,
    )

    options = page.locator("#provider-picker option")
    # text_content (not inner_text): the picker is hidden until a transcript
    # is displayed
    labels = [options.nth(i).text_content() for i in range(options.count())]
    # one option per provider/model pair, labeled by display name
    assert labels == [
        "Alpha Local — model-a1",
        "Alpha Local — model-a2",
        "Beta Remote — model-b1",
    ]
    # the default provider's first model is pre-selected
    checked = page.locator("#provider-picker option:checked").text_content()
    assert checked == "Alpha Local — model-a1"
    # one request on load, no polling
    assert len(provider_requests) == 1
    page.wait_for_timeout(1500)
    assert len(provider_requests) == 1


def test_summarize_disabled_before_transcript(page):
    """T-TRANSCRIPT-SUMMARIZATION-026"""
    # providers configured, but no transcript has been displayed yet
    page.wait_for_function(
        "() => document.querySelectorAll('#provider-picker option').length > 0",
        timeout=10_000,
    )
    assert page.locator("#result").is_hidden()
    assert page.locator("#summarize-btn").is_disabled()


def test_summarize_disabled_without_providers(page, server, monkeypatch):
    """T-TRANSCRIPT-SUMMARIZATION-027"""
    # The config is read per request: pointing the variable at a missing
    # file makes the app "not configured" without a restart.
    monkeypatch.setenv(
        "PROVIDERS_CONFIG", str(server["config_file"].parent / "missing.json")
    )
    page.reload()
    server["stub"].set_success()
    _fetch(page, VIDEO_URL)
    _wait_result(page)

    assert page.locator("#provider-picker option").count() == 0
    assert page.locator("#summarize-btn").is_disabled()


def test_summarize_sends_displayed_transcript(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-028"""
    server["stub"].set_success()
    server["summarize_stub"].delay = 1.0  # an observable in-flight window
    bodies = _summarize_bodies(page)
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    page.click("#summarize-btn")

    # in flight: button and picker disabled, spinner shown
    assert page.locator("#summarize-btn").is_disabled()
    assert page.locator("#provider-picker").is_disabled()
    assert not page.locator("#summarize-spinner").is_hidden()

    _wait_summary_panel(page)
    # the button is re-enabled afterwards
    assert not page.locator("#summarize-btn").is_disabled()
    assert page.locator("#summarize-spinner").is_hidden()

    # the request carries the displayed text, its file name, and the
    # selected provider and model
    assert len(bodies) == 1
    body = bodies[0]
    assert body["text"] == DEFAULT_PAYLOAD["text"]
    assert body["name"] == "test_video_title.txt"
    assert body["provider"] == "alpha"
    assert body["model"] == "model-a1"
    # and the backend call used the selected model
    assert server["summarize_stub"].calls[0]["model"] == "model-a1"


def test_summarize_selected_saved_transcript(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-029"""
    content = "Saved transcript body.\n"
    _seed_transcript(server["transcript_dir"], "saved_video.txt", content)
    page.reload()
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='saved_video.txt']", timeout=10_000
    )

    bodies = _summarize_bodies(page)
    _click_saved_row(page, "saved_video.txt")
    page.click("#summarize-btn")
    _wait_summary_panel(page)

    assert len(bodies) == 1
    body = bodies[0]
    assert body["text"] == content
    assert body["name"] == "saved_video.txt"


# --- T-TRANSCRIPT-SUMMARIZATION-030 .. 036: summary panel and copy --------------


def test_summary_shown_on_success(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-030"""
    server["stub"].set_success()
    _fetch(page, VIDEO_URL)
    _wait_result(page)

    page.click("#summarize-btn")
    _wait_summary_panel(page)

    assert page.locator("#summary-text").inner_text() == SUMMARY_TEXT
    # the copy action is available
    assert not page.locator("#summary-copy-btn").is_disabled()


def test_copy_summary_to_clipboard(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-031"""
    server["stub"].set_success()
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    page.click("#summarize-btn")
    _wait_summary_panel(page)

    page.click("#summary-copy-btn")
    page.wait_for_function(
        "document.getElementById('summary-copy-btn').textContent === 'Copied!'",
        timeout=5_000,
    )
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert clipboard == SUMMARY_TEXT


def test_new_transcript_clears_summary(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-032"""
    server["stub"].set_success()
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    page.click("#summarize-btn")
    _wait_summary_panel(page)
    assert page.locator("#summary-text").inner_text() == SUMMARY_TEXT

    # fetch a different transcript: the previous summary must be cleared
    server["stub"].set_success(payload=LONG_PAYLOAD)
    page.fill("#url-input", "https://youtu.be/aBcDeF12345")
    page.click("#fetch-btn")
    page.wait_for_function(
        "() => document.getElementById('transcript-panel')"
        ".textContent.indexOf('Transcript line number 001') !== -1",
        timeout=10_000,
    )
    assert page.locator("#summary-panel").is_hidden()
    assert page.locator("#summary-text").inner_text() == ""


def test_saved_summary_loaded_with_transcript(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-033"""
    _seed_transcript(server["transcript_dir"], "saved_video.txt", "Saved body.\n")
    _seed_transcript(
        server["transcript_dir"], "saved_video.txt.summary", "The saved summary."
    )
    page.reload()
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='saved_video.txt']", timeout=10_000
    )

    _click_saved_row(page, "saved_video.txt")
    _wait_summary_panel(page)

    assert page.locator("#transcript-panel").inner_text() == "Saved body.\n"
    assert page.locator("#summary-text").inner_text() == "The saved summary."


def test_no_summary_panel_without_saved_summary(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-034"""
    _seed_transcript(server["transcript_dir"], "no_summary_video.txt", "Body.\n")
    page.reload()
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='no_summary_video.txt']", timeout=10_000
    )

    _click_saved_row(page, "no_summary_video.txt")

    # the transcript is displayed...
    assert page.locator("#transcript-panel").inner_text() == "Body.\n"
    # ...and the summary panel stays hidden (give a stray response a chance)
    page.wait_for_timeout(500)
    assert page.locator("#summary-panel").is_hidden()


def test_summarize_error_shown(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-035"""
    server["stub"].set_success()
    server["summarize_stub"].set_failure("unreachable", "ConnectionError")
    _fetch(page, VIDEO_URL)
    _wait_result(page)

    page.click("#summarize-btn")
    page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)

    message = page.locator("#error-banner").inner_text()
    assert "summarization backend" in message.lower()
    assert "try again" in message.lower()
    # no summary panel content is shown, and the page remains usable with
    # the Summarize button re-enabled
    assert page.locator("#summary-panel").is_hidden()
    assert page.locator("#summary-text").inner_text() == ""
    assert not page.locator("#summarize-btn").is_disabled()
    assert not page.locator("#fetch-btn").is_disabled()


def test_summary_markup_shown_as_text(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-036"""
    server["stub"].set_success()
    server["summarize_stub"].summary = (
        "<script>window.__summary_pwned = true;</script>Summary text"
    )
    _fetch(page, VIDEO_URL)
    _wait_result(page)
    page.click("#summarize-btn")
    _wait_summary_panel(page)

    # the markup is displayed as plain text...
    assert "<script>" in page.locator("#summary-text").inner_text()
    # ...not rendered or executed
    assert page.locator("#summary-panel script").count() == 0
    assert page.evaluate("() => window.__summary_pwned") is None


def test_empty_summary_response_shows_no_panel(page, server):
    """T-TRANSCRIPT-SUMMARIZATION-040"""
    server["stub"].set_success()
    server["summarize_stub"].set_empty_summary()
    _fetch(page, VIDEO_URL)
    _wait_result(page)

    page.click("#summarize-btn")
    page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)

    message = page.locator("#error-banner").inner_text()
    assert "no summary text" in message.lower()
    # the summary panel remains hidden...
    assert page.locator("#summary-panel").is_hidden()
    assert page.locator("#summary-text").inner_text() == ""
    # ...and the page remains usable with the Summarize button re-enabled
    assert not page.locator("#summarize-btn").is_disabled()
    assert not page.locator("#fetch-btn").is_disabled()
