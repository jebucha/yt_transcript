"""E2E UI tests (T-WEB-INTERFACE-001 .. 014).

A real uvicorn instance of the app runs in-process (thread) with the upstream
fetch chain stubbed for determinism — no real YouTube traffic.

Run:  python -m pytest tests/e2e/ -q
(One-time:  python -m playwright install chromium)
"""

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from app import chain as chain_mod
from app.chain import FetchResult
from app.errors import (
    BusyError,
    InvalidUrlError,
    NoCaptionsError,
    UpstreamFailureError,
    VideoUnavailableError,
)

DEFAULT_PAYLOAD = {
    "video_id": "dQw4w9WgXcQ",
    "title": "Test Video Title",
    "text": "This is the transcript of the test video.\nSecond line of the transcript.",
    "language": "en",
    "source": "primary",
}

LONG_PAYLOAD = dict(
    DEFAULT_PAYLOAD,
    text="\n".join(f"Transcript line number {i:03d}" for i in range(1, 401)),
)

ERROR_CLASSES = {
    "INVALID_URL": InvalidUrlError,
    "VIDEO_UNAVAILABLE": VideoUnavailableError,
    "NO_CAPTIONS": NoCaptionsError,
    "UPSTREAM_FAILURE": UpstreamFailureError,
    "BUSY": BusyError,
}


class StubChain:
    """Drop-in replacement for chain_mod.default_chain.

    Mirrors the real chain's single-flight semantics (asyncio.Semaphore(1) +
    immediate BusyError) so the BUSY path is exercised realistically.
    """

    def __init__(self):
        self.scenario = {"type": "success", "payload": DEFAULT_PAYLOAD, "delay": 0.0}
        self.calls = []
        self._semaphore = asyncio.Semaphore(1)

    def set_success(self, payload=None, delay=0.0):
        self.scenario = {
            "type": "success",
            "payload": payload or DEFAULT_PAYLOAD,
            "delay": delay,
        }

    def set_error(self, code, message=None):
        self.scenario = {"type": "error", "code": code, "message": message}

    async def run(self, url):
        from app.urls import parse_video_ref

        self.calls.append(url)
        video_id = parse_video_ref(url)  # real parsing: invalid -> 400
        if self._semaphore.locked():
            raise BusyError()
        await self._semaphore.acquire()
        try:
            scenario = self.scenario
            if scenario.get("delay"):
                await asyncio.sleep(scenario["delay"])
            if scenario["type"] == "error":
                raise ERROR_CLASSES[scenario["code"]](scenario.get("message"))
            payload = scenario.get("payload") or DEFAULT_PAYLOAD
            return FetchResult(
                text=payload["text"],
                video_id=payload.get("video_id", video_id),
                title=payload["title"],
                language=payload["language"],
                source=payload.get("source", "primary"),
            )
        finally:
            self._semaphore.release()


# --- fixtures -----------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _lan_ip() -> str:
    """Best-effort LAN IP (non-loopback, non-secure in the browser)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # UDP connect: no packets sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _wait_ready(port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    pytest.fail(f"local server did not become ready on port {port}")


@pytest.fixture(scope="module")
def server():
    from app import main as app_main
    import uvicorn

    stub = StubChain()
    original_chain = chain_mod.default_chain
    chain_mod.default_chain = stub

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
        "lan_ip": lan_ip,
        "ip_base": f"http://127.0.0.1:{port}",
        "localhost_base": f"http://localhost:{port}",
        # non-loopback plain HTTP: a true non-secure context (127.0.0.1 and
        # localhost both count as secure in current Chromium)
        "plain_http_base": f"http://{lan_ip}:{port}" if lan_ip != "127.0.0.1" else None,
    }

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
    """Page served over http://localhost (secure context; clipboard granted)."""
    context = browser.new_context(viewport={"width": 1024, "height": 640})
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = context.new_page()
    pg.goto(server["localhost_base"] + "/")
    yield pg
    context.close()


@pytest.fixture()
def http_page(browser, server):
    """Headless page served over plain HTTP at a non-loopback IP — a true
    non-secure context (127.0.0.1 and localhost are both secure in current
    Chromium), where the async Clipboard API is unavailable."""
    base = server["plain_http_base"]
    if not base:
        pytest.skip("no non-loopback address available for a non-secure context")
    context = browser.new_context(viewport={"width": 1024, "height": 640})
    pg = context.new_page()
    pg.goto(base + "/")
    yield pg
    context.close()


def _fetch(page, url):
    page.fill("#url-input", url)
    page.click("#fetch-btn")


def _wait_result(page):
    page.wait_for_selector("#result:not([hidden])", timeout=10_000)


def _wait_error(page):
    page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)


# --- T-WEB-INTERFACE-001 .. 004 ------------------------------------------------


def test_root_serves_ui(page, server):
    """URL input, fetch button, transcript area and copy button render, and
    the page references no external network resources."""
    external = []

    def on_request(request):
        url = request.url
        if url.startswith("https://"):
            external.append(url)
        elif "http://" in url:
            host_port = url.split("http://", 1)[1].split("/", 1)[0]
            if not host_port.endswith(f":{server['port']}"):
                external.append(url)

    page.on("request", on_request)
    page.reload()

    assert page.locator("#url-input").count() == 1
    assert page.locator("#fetch-btn").count() == 1
    assert page.locator("#transcript-panel").count() == 1
    assert page.locator("#copy-btn").count() == 1
    assert page.title() == "YouTube Transcript"
    assert external == [], f"external network resources referenced: {external}"


def test_fetch_button_shows_loading(page, server):
    server["stub"].set_success(delay=1.2)

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # in flight: button disabled + visible spinner
    assert page.locator("#fetch-btn").is_disabled()
    assert not page.locator("#fetch-spinner").is_hidden()

    _wait_result(page)
    assert not page.locator("#fetch-btn").is_disabled()
    assert page.locator("#fetch-spinner").is_hidden()


def test_fetch_with_enter_key(page, server):
    server["stub"].set_success()

    page.fill("#url-input", "https://youtu.be/dQw4w9WgXcQ")
    page.press("#url-input", "Enter")

    _wait_result(page)
    assert "Test Video Title" in page.locator("#video-title").inner_text()
    assert server["stub"].calls[-1] == "https://youtu.be/dQw4w9WgXcQ"


def test_empty_input_sends_no_request(page, server):
    server["stub"].set_success()

    page.fill("#url-input", "   ")
    page.click("#fetch-btn")
    page.wait_for_timeout(300)

    assert server["stub"].calls == []
    assert page.locator("#error-banner").is_hidden()
    assert not page.locator("#fetch-btn").is_disabled()
    assert page.locator("#result").is_hidden()


# --- T-WEB-INTERFACE-005 .. 009 ------------------------------------------------


def test_result_shown_and_copy_enabled(page, server):
    server["stub"].set_success()

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(page)

    assert "This is the transcript of the test video." in page.locator("#transcript-panel").inner_text()
    assert page.locator("#video-title").inner_text() == "Test Video Title"
    assert "en" in page.locator("#video-language").inner_text()
    assert not page.locator("#copy-btn").is_disabled()


def test_long_transcript_scrolls(page, server):
    server["stub"].set_success(payload=LONG_PAYLOAD)

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(page)

    box = page.locator("#transcript-panel")
    scroll_height = box.evaluate("el => el.scrollHeight")
    client_height = box.evaluate("el => el.clientHeight")
    assert scroll_height > client_height, "panel should be taller than its viewport"
    box.evaluate("el => { el.scrollTop = 500; }")
    assert box.evaluate("el => el.scrollTop") > 0


def test_copy_over_localhost(page, server):
    server["stub"].set_success()

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(page)
    page.click("#copy-btn")

    page.wait_for_function(
        "document.getElementById('copy-btn').textContent === 'Copied!'",
        timeout=5_000,
    )
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert clipboard == DEFAULT_PAYLOAD["text"]


def test_copy_over_plain_http(http_page, server):
    # Non-secure context: the async Clipboard API must be unavailable, which
    # forces the hidden-textarea + execCommand("copy") fallback. (With
    # navigator.clipboard undefined, "Copied!" can only come from the legacy
    # path.)
    assert http_page.evaluate("window.isSecureContext") is False
    assert http_page.evaluate("typeof navigator.clipboard") == "undefined"
    server["stub"].set_success()

    _fetch(http_page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(http_page)
    http_page.click("#copy-btn")

    http_page.wait_for_function(
        "document.getElementById('copy-btn').textContent === 'Copied!'",
        timeout=5_000,
    )


def test_copy_over_plain_http_reaches_system_clipboard(playwright, server):
    # Stronger check: the full transcript actually lands in the OS clipboard.
    # Headed Chromium is required because headless Chromium does not write to
    # the OS system clipboard at all.
    base = server["plain_http_base"]
    if not base:
        pytest.skip("no non-loopback address available for a non-secure context")
    if not shutil.which("pbpaste"):
        pytest.skip("pbpaste not available (macOS only)")
    try:
        browser = playwright.chromium.launch(headless=False)
    except Exception as exc:
        pytest.skip(f"headed Chromium unavailable: {exc}")
    context = None
    try:
        context = browser.new_context(viewport={"width": 1024, "height": 640})
        page = context.new_page()
        page.goto(base + "/")

        assert page.evaluate("typeof navigator.clipboard") == "undefined"
        server["stub"].set_success()

        _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        _wait_result(page)
        page.click("#copy-btn")

        page.wait_for_function(
            "document.getElementById('copy-btn').textContent === 'Copied!'",
            timeout=5_000,
        )
        clipboard = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, check=True
        ).stdout
        assert clipboard == DEFAULT_PAYLOAD["text"]
    finally:
        if context is not None:
            context.close()
        browser.close()


def test_copy_disabled_before_fetch(page):
    assert page.locator("#copy-btn").is_disabled()


# --- T-WEB-INTERFACE-010 .. 014 ------------------------------------------------


def test_invalid_url_error_shown(page, server):
    server["stub"].set_success()

    _fetch(page, "https://vimeo.com/123456789")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "valid YouTube" in message
    # input stays editable and the fetch button re-enabled
    assert not page.locator("#url-input").is_disabled()
    assert not page.locator("#fetch-btn").is_disabled()
    assert page.locator("#url-input").evaluate("el => el.value") == "https://vimeo.com/123456789"


def test_video_unavailable_error_shown(page, server):
    server["stub"].set_error("VIDEO_UNAVAILABLE")

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "unavailable" in message.lower()
    assert "private" in message.lower()
    assert not page.locator("#fetch-btn").is_disabled()


def test_no_captions_error_shown(page, server):
    server["stub"].set_error("NO_CAPTIONS")

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "no captions" in message.lower()


def test_upstream_failure_error_shown(page, server):
    server["stub"].set_error("UPSTREAM_FAILURE")

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "rate-limit" in message or "blocking" in message
    assert "try again later" in message.lower()


def test_busy_error_shown(page, server):
    # The first request is slow (holds the single-flight semaphore); a second
    # request issued while it is in flight must come back BUSY.
    server["stub"].set_success(delay=1.5)

    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert page.locator("#fetch-btn").is_disabled()
    page.wait_for_timeout(400)

    page.fill("#url-input", "https://youtu.be/aBcDeF12345")
    page.press("#url-input", "Enter")
    _wait_error(page)

    message = page.locator("#error-banner").inner_text()
    assert "busy" in message.lower()
    assert "try again" in message.lower()
    assert not page.locator("#fetch-btn").is_disabled()

    # Drain the still-in-flight first fetch so the single-flight semaphore is
    # released before any later test issues a fetch (no cross-test BUSY).
    _wait_result(page)


# --- T-TRANSCRIPT-LIBRARY-016 .. 027 ------------------------------------------
# The saved-transcript list UI. The running server reads TRANSCRIPT_DIR at call
# time, so a fresh per-test directory wired via the env var is enough; seeding
# files and reloading the page makes them visible to the list.

SAVED_MTIME_OLD = 1_760_000_000
SAVED_MTIME_NEW = SAVED_MTIME_OLD + 3600


@pytest.fixture()
def saved_env():
    """A fresh per-test transcript directory wired to the running server via
    TRANSCRIPT_DIR (the app reads the variable at call time)."""
    tmp = tempfile.TemporaryDirectory()
    os.environ["TRANSCRIPT_DIR"] = tmp.name
    yield Path(tmp.name)
    os.environ.pop("TRANSCRIPT_DIR", None)
    tmp.cleanup()


def _seed(directory, name, content, mtime):
    """Write a saved transcript and pin its mtime (no clock-granularity flakes)."""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _wait_saved_rows(page, count):
    page.wait_for_function(
        "n => document.querySelectorAll('#saved-list .saved-row').length === n",
        arg=count,
        timeout=10_000,
    )


def test_saved_list_shows_transcripts(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-016"""
    _seed(saved_env, "the_end_of_llms_ncm.txt", "Hello there.\n", SAVED_MTIME_NEW)
    _seed(saved_env, "another_video.txt", "Another transcript.\n", SAVED_MTIME_OLD)
    page.reload()

    _wait_saved_rows(page, 2)
    rows = page.locator("#saved-list .saved-row")
    # most recent first, each row carries the real file name
    assert rows.nth(0).get_attribute("data-name") == "the_end_of_llms_ncm.txt"
    assert rows.nth(1).get_attribute("data-name") == "another_video.txt"
    assert page.locator("#saved-count").inner_text() == "2"
    assert page.locator("#saved-empty").is_hidden()
    # inside a bounded, scrollable area
    list_box = page.locator("#saved-list")
    assert list_box.evaluate("el => getComputedStyle(el).overflowY") in ("auto", "scroll")
    assert list_box.evaluate("el => getComputedStyle(el).maxHeight") != "none"


def test_saved_list_empty_state(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-018"""
    page.reload()  # fresh empty directory

    page.wait_for_selector("#saved-empty:not([hidden])", timeout=10_000)
    assert page.locator("#saved-list").is_hidden()
    assert page.locator("#saved-list .saved-row").count() == 0
    assert page.locator("#saved-count").inner_text() == ""


def test_saved_list_scrolls(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-019"""
    for i in range(60):
        _seed(saved_env, f"transcript_{i:03d}.txt", f"line {i}\n", SAVED_MTIME_OLD + i)
    page.reload()

    _wait_saved_rows(page, 60)
    box = page.locator("#saved-list")
    scroll_height = box.evaluate("el => el.scrollHeight")
    client_height = box.evaluate("el => el.clientHeight")
    assert scroll_height > client_height, "list should be taller than its viewport"
    box.evaluate("el => { el.scrollTop = 500; }")
    assert box.evaluate("el => el.scrollTop") > 0
    # the section stays bounded, so the page layout does not break
    assert box.evaluate("el => getComputedStyle(el).maxHeight") != "none"
    assert page.evaluate("() => document.body.scrollHeight") < 3 * 640


def test_saved_list_prettified_display_name(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-017"""
    _seed(saved_env, "the_end_of_llms_ncm.txt", "Hello there.\n", SAVED_MTIME_NEW)
    page.reload()
    page.wait_for_selector("#saved-list .saved-row", timeout=10_000)

    row = page.locator("#saved-list .saved-row")
    # display: underscores replaced with spaces, .txt extension stripped,
    # words capitalized (CSS text-transform); the row itself carries the
    # real file name
    label = row.locator(".saved-name").inner_text()
    assert "_" not in label
    assert label.lower() == "the end of llms ncm"
    assert row.locator(".saved-name").evaluate(
        "el => getComputedStyle(el).textTransform"
    ) == "capitalize"
    assert row.get_attribute("data-name") == "the_end_of_llms_ncm.txt"

    # any request triggered by the row targets the real file name
    request_paths = []
    page.on(
        "request",
        lambda r: request_paths.append(urlparse(r.url).path),
    )
    row.click()
    page.wait_for_selector("#result:not([hidden])", timeout=10_000)
    assert "/api/transcripts/the_end_of_llms_ncm.txt" in request_paths


def test_saved_list_updates_after_fetch(page, server, saved_env):
    """T-TRANSCRIPT-LIBRARY-020"""
    server["stub"].set_success()
    page.reload()
    page.wait_for_function(
        "() => document.querySelectorAll('#saved-list .saved-row').length === 0"
    )

    # a successful fetch persists test_video_title.txt and reloads the list
    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(page)

    page.wait_for_selector(
        "#saved-list .saved-row[data-name='test_video_title.txt']", timeout=10_000
    )
    assert page.locator("#saved-list .saved-row").count() == 1


def test_saved_list_manual_refresh(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-026"""
    page.reload()
    page.wait_for_function(
        "() => document.querySelectorAll('#saved-list .saved-row').length === 0"
    )

    # a new file appears without a fetch; only the refresh affordance notices
    _seed(saved_env, "brand_new_video.txt", "Fresh text.\n", SAVED_MTIME_NEW)
    assert page.locator("#saved-list .saved-row").count() == 0

    page.click("#saved-refresh-btn")
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='brand_new_video.txt']", timeout=10_000
    )
    assert page.locator("#saved-list .saved-row").count() == 1


def test_saved_list_does_not_poll(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-027"""
    list_requests = []

    def on_request(request):
        if urlparse(request.url).path == "/api/transcripts":
            list_requests.append(request.url)

    page.on("request", on_request)
    page.reload()
    page.wait_for_function(
        "() => document.querySelectorAll('#saved-list .saved-row').length === 0"
    )

    # exactly one list request on load, and none after it
    assert len(list_requests) == 1
    page.wait_for_timeout(1500)
    assert len(list_requests) == 1


def test_click_saved_transcript_displays_it(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-021"""
    _seed(saved_env, "the_end_of_llms_ncm.txt", "Hello there.\n", SAVED_MTIME_NEW)
    page.reload()
    page.wait_for_selector("#saved-list .saved-row", timeout=10_000)

    page.click("#saved-list .saved-row")
    _wait_result(page)

    assert page.locator("#transcript-panel").inner_text() == "Hello there.\n"
    # the transcript's name is shown as the title
    assert page.locator("#video-title").inner_text() == "the_end_of_llms_ncm.txt"
    assert not page.locator("#copy-btn").is_disabled()
    # the language line is hidden for a saved transcript
    assert page.locator("#video-language").inner_text() == ""


def test_saved_transcript_html_shown_as_text(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-022"""
    markup = "<script>window.__transcript_pwned = true;</script>hello world"
    _seed(saved_env, "tricky_video.txt", markup + "\n", SAVED_MTIME_NEW)
    page.reload()
    page.wait_for_selector("#saved-list .saved-row", timeout=10_000)

    page.click("#saved-list .saved-row")
    _wait_result(page)

    # the markup is displayed as plain text...
    assert "<script>" in page.locator("#transcript-panel").inner_text()
    # ...not rendered or executed
    assert page.locator("#transcript-panel script").count() == 0
    assert page.evaluate("() => window.__transcript_pwned") is None


def test_click_deleted_saved_transcript_shows_error(page, saved_env):
    """T-TRANSCRIPT-LIBRARY-023"""
    path = _seed(saved_env, "gone_video.txt", "Gone.\n", SAVED_MTIME_NEW)
    page.reload()
    page.wait_for_selector(
        "#saved-list .saved-row[data-name='gone_video.txt']", timeout=10_000
    )

    # the file disappears after the list was loaded
    path.unlink()
    page.click("#saved-list .saved-row")
    _wait_error(page)

    assert page.locator("#error-banner").inner_text()
    # the page remains usable
    assert not page.locator("#url-input").is_disabled()
    assert not page.locator("#fetch-btn").is_disabled()


def test_download_saved_transcript_downloads_file(page, server, saved_env):
    """T-TRANSCRIPT-LIBRARY-024"""
    content = "Hello there.\n"
    _seed(saved_env, "the_end_of_llms_ncm.txt", content, SAVED_MTIME_NEW)
    page.reload()
    page.wait_for_selector("#saved-list .saved-row", timeout=10_000)

    # A freshly fetched transcript has no download name: button stays disabled
    server["stub"].set_success()
    _fetch(page, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _wait_result(page)
    assert page.locator("#download-btn").is_disabled()

    # A saved transcript does: clicking its row enables the download
    page.click("#saved-list .saved-row[data-name='the_end_of_llms_ncm.txt']")
    page.wait_for_function(
        "() => document.getElementById('video-title').textContent === 'the_end_of_llms_ncm.txt'",
        timeout=10_000,
    )
    assert not page.locator("#download-btn").is_disabled()

    with page.expect_download() as download_info:
        page.click("#download-btn")
    download = download_info.value
    assert download.suggested_filename == "the_end_of_llms_ncm.txt"

    target = Path(tempfile.mkstemp(suffix=".txt")[1])
    try:
        download.save_as(str(target))
        # the downloaded bytes equal the seeded file's content
        assert target.read_bytes() == content.encode("utf-8")
    finally:
        target.unlink()


def test_download_over_plain_http(http_page, saved_env):
    """T-TRANSCRIPT-LIBRARY-025"""
    # a true non-secure context: the Blob download must not depend on HTTPS
    assert http_page.evaluate("window.isSecureContext") is False
    content = "Hello there.\n"
    _seed(saved_env, "the_end_of_llms_ncm.txt", content, SAVED_MTIME_NEW)
    http_page.reload()
    http_page.wait_for_selector("#saved-list .saved-row", timeout=10_000)

    http_page.click("#saved-list .saved-row")
    http_page.wait_for_function(
        "() => document.getElementById('video-title').textContent === 'the_end_of_llms_ncm.txt'",
        timeout=10_000,
    )
    assert not http_page.locator("#download-btn").is_disabled()

    with http_page.expect_download() as download_info:
        http_page.click("#download-btn")
    download = download_info.value
    assert download.suggested_filename == "the_end_of_llms_ncm.txt"

    target = Path(tempfile.mkstemp(suffix=".txt")[1])
    try:
        download.save_as(str(target))
        assert target.read_bytes() == content.encode("utf-8")
    finally:
        target.unlink()
