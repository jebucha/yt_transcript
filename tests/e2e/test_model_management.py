"""E2E model-management tests (T-SUMMARIZATION-MODEL-MANAGEMENT-029 .. 041).

A real uvicorn instance of the app runs in-process (thread) with the upstream
fetch chain, the summarize HTTP dispatch seam, and the model-discovery HTTP
seam all stubbed, so no real YouTube, LLM, or /models traffic happens. The
provider config is a temporary file wired in via PROVIDERS_CONFIG; the app
reads it per request, so tests can swap it between requests. The overlay
file is deleted between tests so each test starts from file-only models.

Run:  python -m pytest tests/e2e/test_model_management.py -q
(One-time:  python -m playwright install chromium)
"""

import json
import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app import chain as chain_mod
from app import summarize as summarize_mod
from tests.e2e.test_summarization import SummarizeStub
from tests.e2e.test_ui import StubChain, _free_port, _wait_ready

# Two providers with differing effective model counts (2 and 1).
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

DISCOVERED = ["discovered-1", "model-a1", "discovered-2"]


def write_provider_config(path: Path, config=PROVIDER_CONFIG) -> Path:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


class DiscoveryStub:
    """Recording stand-in for model_discovery._get_provider_models.

    Sits *below* list_models (the e2e seam, design decision 6), so the real
    function's provider_models_refreshed / provider_models_refresh_failed log
    emission still runs while tests control the backend response.
    """

    def __init__(self):
        self.calls = []
        self.models = list(DISCOVERED)
        self.failure = None

    def reset(self):
        self.calls = []
        self.models = list(DISCOVERED)
        self.failure = None

    def set_failure(self, reason, detail):
        self.failure = (reason, detail)

    def __call__(self, base_url, api_key, timeout):
        from app import model_discovery as discovery_mod

        self.calls.append({
            "base_url": base_url,
            "api_key": api_key,
            "timeout": timeout,
        })
        if self.failure is not None:
            raise discovery_mod.ModelDiscoveryError(*self.failure)
        return {"data": [{"id": model_id} for model_id in self.models]}


# --- fixtures -----------------------------------------------------------------


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from app import main as app_main
    from app import model_discovery as discovery_mod
    import uvicorn

    stub = StubChain()
    summarize_stub = SummarizeStub()
    discovery_stub = DiscoveryStub()
    original_chain = chain_mod.default_chain
    chain_mod.default_chain = stub
    original_dispatch = summarize_mod._call_chat_completions
    summarize_mod._call_chat_completions = summarize_stub
    original_discovery = discovery_mod._get_provider_models
    discovery_mod._get_provider_models = discovery_stub

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
        "discovery_stub": discovery_stub,
        "config_file": config_file,
        "transcript_dir": transcript_dir,
        "ip_base": f"http://127.0.0.1:{port}",
        "localhost_base": f"http://localhost:{port}",
    }

    uvicorn_server.should_exit = True
    thread.join(timeout=10)
    chain_mod.default_chain = original_chain
    summarize_mod._call_chat_completions = original_dispatch
    discovery_mod._get_provider_models = original_discovery
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
    """Fresh stub state and a clean overlay file for every test."""
    server["stub"].calls = []
    server["stub"].set_success()
    server["summarize_stub"].reset()
    server["discovery_stub"].reset()
    overlay = server["transcript_dir"] / "provider_overrides.json"
    if overlay.exists():
        overlay.unlink()
    yield
    if overlay.exists():
        overlay.unlink()


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


def _item(page, provider_name):
    """The provider's <li> (row + panel) in the model-management list."""
    return page.locator("#model-management-list .model-provider").filter(
        has_text=provider_name
    )


def _wait_section(page):
    page.wait_for_selector(
        "#model-management-list .model-provider-row", timeout=10_000
    )


def _wait_count(page, count_text):
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('.model-provider-count')]"
        ".some(el => el.textContent.trim() === t)",
        arg=count_text,
        timeout=10_000,
    )


def _open_panel(page, provider_name):
    item = _item(page, provider_name)
    item.locator(".model-provider-row").click()
    page.wait_for_selector(".model-panel:not([hidden])", timeout=10_000)
    return item


def _overlay(transcript_dir):
    path = transcript_dir / "provider_overrides.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _picker_labels(page):
    options = page.locator("#provider-picker option")
    return [
        options.nth(i).text_content() for i in range(options.count())
    ]


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-029 .. 031: the section ------------------


def test_section_visible_before_transcript(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-029"""
    _wait_section(page)
    # the section is visible without any transcript displayed
    assert page.locator("#result").is_hidden()
    assert page.locator("#model-management").is_visible()
    assert page.locator("#model-management-title").is_visible()
    rows = page.locator("#model-management-list .model-provider-row")
    assert rows.count() == 2
    names = [rows.nth(i).text_content() for i in range(rows.count())]
    assert "Alpha Local" in names[0]
    assert "Beta Remote" in names[1]


def test_section_lists_providers_and_counts(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-030"""
    _wait_section(page)
    alpha = _item(page, "Alpha Local")
    beta = _item(page, "Beta Remote")
    # each provider's display name and effective model count are shown
    assert "Alpha Local" in alpha.locator(".model-provider-name").text_content()
    assert "Beta Remote" in beta.locator(".model-provider-name").text_content()
    assert alpha.locator(".model-provider-count").text_content().strip() == "2 models"
    assert beta.locator(".model-provider-count").text_content().strip() == "1 model"


def test_section_empty_without_providers(page, server, monkeypatch):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-031"""
    # The config is read per request: an empty provider map makes the app
    # "not configured" without a restart (the original file is untouched).
    empty_config = server["config_file"].parent / "empty_providers.json"
    empty_config.write_text(json.dumps({"provider": {}, "default": "alpha"}),
                            encoding="utf-8")
    monkeypatch.setenv("PROVIDERS_CONFIG", str(empty_config))
    page.reload()

    page.wait_for_selector("#model-management-empty:not([hidden])", timeout=10_000)
    # the empty state is shown and no manage actions are offered
    assert page.locator("#model-management").is_visible()
    assert page.locator("#model-management-empty").is_visible()
    assert page.locator("#model-management-list").is_hidden()
    assert page.locator("#model-management-list .model-provider-row").count() == 0


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-032 .. 036: the manage panel -------------


def test_manual_add_from_panel(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-032"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-add-input").fill("new-model-1")
    item.locator(".model-add-form button[type=submit]").click()

    # the provider's count increases...
    _wait_count(page, "3 models")
    item = _item(page, "Alpha Local")
    assert item.locator(".model-provider-count").text_content().strip() == "3 models"
    # ...and the model appears in the provider's added list
    added = item.locator(".model-added-list .model-list-id")
    assert added.count() == 1
    assert added.nth(0).text_content() == "new-model-1"
    # the addition is persisted to the overlay file
    assert _overlay(server["transcript_dir"]) == {"alpha": ["new-model-1"]}


def test_discovered_model_can_be_added(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-033"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-discover-btn").click()

    # the discovered ids are rendered, one row each
    page.wait_for_selector(".model-discovered-list:not([hidden])", timeout=10_000)
    item = _item(page, "Alpha Local")
    discovered = item.locator(".model-discovered-list .model-list-item")
    assert discovered.count() == 3
    ids = [
        discovered.nth(i).locator(".model-list-id").text_content()
        for i in range(discovered.count())
    ]
    assert ids == DISCOVERED
    # an already-effective id offers no add action
    effective_row = discovered.filter(has_text="model-a1")
    assert effective_row.locator("button").is_disabled()
    assert effective_row.locator("button").text_content() == "Added"

    # clicking Add beside a discovered model adds it
    discovered.nth(0).locator("button").click()
    _wait_count(page, "3 models")
    item = _item(page, "Alpha Local")
    added = item.locator(".model-added-list .model-list-id")
    assert added.count() == 1
    assert added.nth(0).text_content() == "discovered-1"
    # the discovered row now reads as added
    row = item.locator(".model-discovered-list .model-list-item").filter(
        has_text="discovered-1"
    )
    assert row.locator("button").is_disabled()
    assert row.locator("button").text_content() == "Added"
    assert _overlay(server["transcript_dir"]) == {"alpha": ["discovered-1"]}


def test_added_model_can_be_removed(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-034"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-add-input").fill("temp-model")
    item.locator(".model-add-form button[type=submit]").click()
    _wait_count(page, "3 models")

    # clicking Remove beside the added model removes it
    item = _item(page, "Alpha Local")
    item.locator(".model-added-list button").click()
    _wait_count(page, "2 models")
    item = _item(page, "Alpha Local")
    assert item.locator(".model-provider-count").text_content().strip() == "2 models"
    assert item.locator(".model-added-list .model-list-item").count() == 0
    # the overlay no longer holds it
    assert _overlay(server["transcript_dir"]) == {}


def test_file_models_not_removable(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-035"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")

    # the config-file models are listed in the panel...
    file_rows = item.locator(".model-file-list .model-list-item")
    assert file_rows.count() == 2
    ids = [
        file_rows.nth(i).locator(".model-list-id").text_content()
        for i in range(file_rows.count())
    ]
    assert ids == ["model-a1", "model-a2"]
    # ...without a Remove action
    assert item.locator(".model-file-list button").count() == 0


def test_markup_model_ids_shown_as_text(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-036"""
    markup = '<img src=x onerror="window.__mm_pwned = true">'
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-add-input").fill(markup)
    item.locator(".model-add-form button[type=submit]").click()
    _wait_count(page, "3 models")

    item = _item(page, "Alpha Local")
    added = item.locator(".model-added-list .model-list-id")
    assert added.count() == 1
    # the markup-like id is displayed as plain text...
    assert added.nth(0).text_content() == markup
    # ...not rendered or executed
    assert item.locator(".model-added-list img").count() == 0
    assert page.evaluate("() => window.__mm_pwned") is None


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-037 .. 038: picker refresh ---------------


def test_added_model_selected_in_picker(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-037"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-add-input").fill("picked-model")
    item.locator(".model-add-form button[type=submit]").click()
    _wait_count(page, "3 models")

    # the picker offers the added model...
    assert "Alpha Local — picked-model" in _picker_labels(page)
    # ...and selects it for the current page session
    selected = page.locator("#provider-picker option:checked").text_content()
    assert selected == "Alpha Local — picked-model"


def test_removed_model_leaves_picker(page):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-038"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-add-input").fill("doomed-model")
    item.locator(".model-add-form button[type=submit]").click()
    _wait_count(page, "3 models")
    assert (
        page.locator("#provider-picker option:checked").text_content()
        == "Alpha Local — doomed-model"
    )

    # removing it drops it from the picker...
    item = _item(page, "Alpha Local")
    item.locator(".model-added-list button").click()
    _wait_count(page, "2 models")
    assert "Alpha Local — doomed-model" not in _picker_labels(page)
    # ...and the selection falls back to the default option
    selected = page.locator("#provider-picker option:checked").text_content()
    assert selected == "Alpha Local — model-a1"


# --- T-SUMMARIZATION-MODEL-MANAGEMENT-039 .. 041: error handling ---------------


def test_discovery_failure_shown(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-039"""
    server["discovery_stub"].set_failure("unreachable", "ConnectionError")
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    item.locator(".model-discover-btn").click()

    page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)
    message = page.locator("#error-banner").inner_text().lower()
    # a discovery-specific message, not a failed-summary message
    assert "model list" in message
    assert "manually" in message
    assert "summarization backend" not in message

    # the effective model list is unchanged and no discovered list appeared
    item = _item(page, "Alpha Local")
    assert item.locator(".model-provider-count").text_content().strip() == "2 models"
    assert item.locator(".model-discovered-list").is_hidden()

    # the section remains usable: a manual add still works and clears the error
    item.locator(".model-add-input").fill("after-failure")
    item.locator(".model-add-form button[type=submit]").click()
    _wait_count(page, "3 models")
    assert page.locator("#error-banner").is_hidden()


def test_invalid_model_error_shown(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-040"""
    _wait_section(page)
    item = _open_panel(page, "Alpha Local")
    # 201 characters: over the 200-character bound (set directly so the
    # input's maxlength hint cannot clamp it before the request goes out)
    item.locator(".model-add-input").evaluate("el => { el.value = 'x'.repeat(201); }")
    item.locator(".model-add-form button[type=submit]").click()

    page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)
    assert "model id" in page.locator("#error-banner").inner_text().lower()
    # no model was added and nothing was written
    item = _item(page, "Alpha Local")
    assert item.locator(".model-provider-count").text_content().strip() == "2 models"
    assert item.locator(".model-added-list .model-list-item").count() == 0
    assert _overlay(server["transcript_dir"]) is None


def test_write_failure_error_shown(page, server):
    """T-SUMMARIZATION-MODEL-MANAGEMENT-041"""
    transcript_dir = server["transcript_dir"]
    original_mode = transcript_dir.stat().st_mode
    try:
        # reads still work, but the overlay (and its temp file) cannot be
        # written: a real WRITE_FAILED for the manual add
        os.chmod(transcript_dir, 0o555)
        _wait_section(page)
        item = _open_panel(page, "Alpha Local")
        item.locator(".model-add-input").fill("unsaveable-model")
        item.locator(".model-add-form button[type=submit]").click()

        page.wait_for_selector("#error-banner:not([hidden])", timeout=10_000)
        message = page.locator("#error-banner").inner_text().lower()
        assert "save" in message
        assert "writable" in message

        # no partial state: the model was not added...
        item = _item(page, "Alpha Local")
        assert item.locator(".model-provider-count").text_content().strip() == "2 models"
        assert item.locator(".model-added-list .model-list-item").count() == 0
        # ...and the section remains usable
        assert page.locator("#model-management").is_visible()
        assert item.locator(".model-discover-btn").count() == 1
    finally:
        os.chmod(transcript_dir, original_mode)
