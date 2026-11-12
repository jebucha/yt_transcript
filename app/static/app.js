/* YouTube Transcript — request flow, result display, copy button, errors.
 * All fetched content is inserted via textContent only (never as HTML). */
(function () {
  "use strict";

  var input = document.getElementById("url-input");
  var form = document.getElementById("fetch-form");
  var fetchBtn = document.getElementById("fetch-btn");
  var spinner = document.getElementById("fetch-spinner");
  var errorBanner = document.getElementById("error-banner");
  var resultSection = document.getElementById("result");
  var titleEl = document.getElementById("video-title");
  var langEl = document.getElementById("video-language");
  var panel = document.getElementById("transcript-panel");
  var copyBtn = document.getElementById("copy-btn");
  var downloadBtn = document.getElementById("download-btn");
  var savedList = document.getElementById("saved-list");
  var savedEmpty = document.getElementById("saved-empty");
  var savedCount = document.getElementById("saved-count");
  var savedRefreshBtn = document.getElementById("saved-refresh-btn");
  var providerPicker = document.getElementById("provider-picker");
  var autoCheckbox = document.getElementById("auto-summarize");
  var autoNote = document.getElementById("auto-summarize-note");
  var summarizeBtn = document.getElementById("summarize-btn");
  var summarizeSpinner = document.getElementById("summarize-spinner");
  var summaryPanel = document.getElementById("summary-panel");
  var summaryTextEl = document.getElementById("summary-text");
  var summaryCopyBtn = document.getElementById("summary-copy-btn");
  var modelManagementList = document.getElementById("model-management-list");
  var modelManagementEmpty = document.getElementById("model-management-empty");

  var ERROR_MESSAGES = {
    INVALID_URL:
      "That doesn't look like a valid YouTube video URL. Check the link and try again.",
    VIDEO_UNAVAILABLE:
      "This video is unavailable — it may be private, deleted, or region-locked.",
    NO_CAPTIONS:
      "This video has no captions available, so there is no transcript to show.",
    UPSTREAM_FAILURE:
      "Couldn't fetch the transcript — YouTube may be rate-limiting or blocking the server. Please try again later.",
    BUSY:
      "The server is busy with another transcript right now. Please try again in a moment.",
    NOT_CONFIGURED:
      "Summarization is not set up — no providers are configured.",
    INVALID_PROVIDER:
      "That provider or model is no longer configured. Reload the page and try again.",
    PROVIDER_ERROR:
      "The summarization backend failed — it may be down or overloaded. Please try again.",
    INPUT_TOO_LONG:
      "This transcript is too long to summarize (over 100,000 characters).",
    INVALID_MODEL:
      "That model id can't be added — it must be 1–200 characters with no control characters, and each provider holds at most 50 added models.",
    MODEL_NOT_REMOVABLE:
      "That model comes from the provider config file, so it can't be removed from the UI.",
    NOT_FOUND:
      "That model isn't among this provider's added models, so it can't be removed.",
    WRITE_FAILED:
      "Couldn't save the model list — the server's transcript directory is " +
      "not writable. Please check the server's storage."
  };

  var currentTranscript = "";
  // Real file name of the displayed saved transcript ("" for a freshly
  // fetched transcript, which the UI has no trustworthy name to download).
  var currentSavedName = "";
  // Trustworthy file name of the displayed transcript: the derived name from
  // the fetch response, or the saved row's name (used by Summarize). Kept
  // separate from currentSavedName, which still drives Download's predicate.
  var currentTranscriptName = "";
  var currentSummary = "";
  // Monotonic display token: a late summary response for a previously
  // displayed transcript must not populate the panel.
  var displayToken = 0;
  var summarizing = false;
  var restoreCopyLabelTimer = null;
  var restoreSummaryCopyLabelTimer = null;
  // Loaded provider list (display side only — never keys or base URLs) and
  // the picker options, parallel to the <select>'s options.
  var providers = [];
  var defaultProviderId = null;
  var providerOptions = [];
  // The autoSummarize setting as last known to be persisted server-side:
  // the revert target when a POST /api/settings write fails (design D6).
  var persistedAutoSummarize = false;
  // Model-management UI state (design D7/D8): which manage panels the user
  // has open (a re-render must not collapse them), and the last successful
  // discovery result per provider (so a section re-render doesn't lose it).
  var openPanels = {};
  var discoveredModels = {};
  // A failed "Refresh from backend" must not read as a failed summary.
  var DISCOVERY_ERROR_MESSAGES = {
    PROVIDER_ERROR:
      "Couldn't fetch the model list from that backend — it may be down or " +
      "not expose a models endpoint. You can still add a model manually."
  };

  function setBusy(busy) {
    fetchBtn.disabled = busy;
    spinner.hidden = !busy;
  }

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }

  function clearError() {
    errorBanner.textContent = "";
    errorBanner.hidden = true;
  }

  // ``overrides`` (optional) maps error codes to call-site-specific messages
  // that take precedence over ERROR_MESSAGES — used by model discovery,
  // where a PROVIDER_ERROR is a failed refresh, not a failed summary.
  function messageFor(code, serverMessage, overrides) {
    if (code && overrides && overrides[code]) return overrides[code];
    if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
    if (serverMessage) return serverMessage;
    return "Something went wrong. Please try again.";
  }

  function renderResult(data) {
    currentTranscript = data.text;
    // A freshly fetched transcript has no trustworthy file name to download.
    currentSavedName = "";
    // ...but the fetch response carries its derived persistence name, which
    // Summarize uses for the alongside save.
    currentTranscriptName = data.name || "";
    downloadBtn.disabled = true;
    titleEl.textContent = data.title || "";
    titleEl.title = data.title || "";
    langEl.textContent = data.language ? "Language: " + data.language : "";
    panel.textContent = data.text;
    resultSection.hidden = false;
    copyBtn.disabled = false;
    panel.scrollTop = 0;
    displayToken++; // invalidate any in-flight saved-summary load
    clearSummary();
    updateSummarizeEnabled();
    // Auto-summarize hook: fresh fetches only (design D5) — the saved-
    // transcript click path (displaySavedTranscript) never fires it.
    maybeAutoSummarize(displayToken);
  }

  // With auto-summarize on, a fresh fetch first tries the saved-summary read
  // for the derived name (the same load saved clicks use): a found summary
  // is shown and the summarize call is skipped; otherwise the auto-fire
  // targets the picker's default (design D5).
  async function maybeAutoSummarize(token) {
    if (!autoCheckbox.checked) return;
    var shown = await loadSavedSummary(currentTranscriptName, token);
    if (shown) return;
    if (token !== displayToken) return; // transcript changed meanwhile
    if (!autoCheckbox.checked) return; // the user turned it off meanwhile
    doSummarize(true);
  }

  async function doFetch() {
    var url = input.value.trim();
    if (!url) return; // no request, no error

    clearError();
    setBusy(true);
    try {
      var res = await fetch("/api/transcript", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url })
      });
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!res.ok) {
        var code = data && data.error ? data.error.code : null;
        var serverMessage = data && data.error ? data.error.message : null;
        showError(messageFor(code, serverMessage));
        return;
      }
      renderResult(data);
      // The fetch just persisted a new file; pick it up in the saved list.
      loadSavedList();
    } catch (_) {
      showError("Network error — could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    doFetch();
  });

  // Explicit Enter handling: works identically to the fetch button even while
  // the button is disabled (a disabled default button would suppress the
  // browser's implicit form submission).
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      doFetch();
    }
  });

  // --- copy button ----------------------------------------------------------

  function legacyCopy(text) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_) {
      ok = false;
    }
    document.body.removeChild(textarea);
    return ok;
  }

  async function copyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        // fall through to the legacy path (e.g. permission denied)
      }
    }
    return legacyCopy(text);
  }

  function showCopied() {
    copyBtn.textContent = "Copied!";
    copyBtn.disabled = true;
    if (restoreCopyLabelTimer) clearTimeout(restoreCopyLabelTimer);
    restoreCopyLabelTimer = setTimeout(function () {
      copyBtn.textContent = "Copy transcript";
      copyBtn.disabled = false;
      restoreCopyLabelTimer = null;
    }, 1500);
  }

  copyBtn.addEventListener("click", async function () {
    if (copyBtn.disabled || !currentTranscript) return;
    var ok = await copyText(currentTranscript);
    if (ok) showCopied();
  });

  // --- saved transcripts list -------------------------------------------------

  // Cosmetic display only: drop the .txt extension and turn underscores into
  // spaces (words are capitalized by CSS text-transform). The real file name is
  // kept in the row's data-name and is what every request uses; the display
  // string is never sent to the server.
  function prettifyName(name) {
    return name.replace(/\.txt$/i, "").replace(/_/g, " ");
  }

  function formatSavedDate(iso) {
    var date = new Date(iso);
    return isNaN(date.getTime()) ? "" : date.toLocaleDateString();
  }

  function renderSavedList(transcripts) {
    // Rebuild the list; every fetched string enters the DOM via textContent.
    savedList.textContent = "";
    savedCount.textContent = transcripts.length ? String(transcripts.length) : "";
    if (!transcripts.length) {
      savedList.hidden = true;
      savedEmpty.hidden = false;
      return;
    }
    savedList.hidden = false;
    savedEmpty.hidden = true;
    for (var i = 0; i < transcripts.length; i++) {
      var entry = transcripts[i];
      var item = document.createElement("li");
      var row = document.createElement("button");
      row.type = "button";
      row.className = "saved-row";
      row.dataset.name = entry.name; // real file name; requests use this
      row.title = entry.name;
      var nameSpan = document.createElement("span");
      nameSpan.className = "saved-name";
      nameSpan.textContent = prettifyName(entry.name);
      var dateSpan = document.createElement("span");
      dateSpan.className = "saved-date";
      dateSpan.textContent = formatSavedDate(entry.modified);
      row.appendChild(nameSpan);
      row.appendChild(dateSpan);
      item.appendChild(row);
      savedList.appendChild(item);
    }
  }

  async function loadSavedList() {
    try {
      var res = await fetch("/api/transcripts");
      if (!res.ok) return; // best-effort: keep the current display
      var data = await res.json();
      renderSavedList(data.transcripts || []);
    } catch (_) {
      // network failure: the page stays usable, nothing new to show
    }
  }

  // Manual refresh affordance: reload the list on demand (design decision 6).
  savedRefreshBtn.addEventListener("click", function () {
    loadSavedList();
  });

  // Click a list row: load that transcript into the existing result panel.
  // The request uses the row's real file name (data-name), never the
  // prettified display string.
  savedList.addEventListener("click", function (event) {
    var row = event.target.closest(".saved-row");
    if (!row) return;
    displaySavedTranscript(row.dataset.name);
  });

  async function displaySavedTranscript(name) {
    clearError();
    try {
      var res = await fetch("/api/transcripts/" + encodeURIComponent(name));
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!res.ok || !data || typeof data.text !== "string") {
        var serverMessage = data && data.error ? data.error.message : null;
        showError(messageFor(null, serverMessage));
        return;
      }
      currentTranscript = data.text;
      currentSavedName = data.name;
      currentTranscriptName = data.name;
      titleEl.textContent = data.name;
      titleEl.title = data.name || "";
      langEl.textContent = ""; // no language to show for a saved transcript
      panel.textContent = data.text;
      resultSection.hidden = false;
      copyBtn.disabled = false;
      // Only a saved transcript has a trustworthy file name to download.
      downloadBtn.disabled = false;
      panel.scrollTop = 0;
      displayToken++; // invalidate any in-flight saved-summary load
      clearSummary();
      updateSummarizeEnabled();
      // Best-effort: if this transcript has a saved summary, show it.
      loadSavedSummary(data.name, displayToken);
    } catch (_) {
      showError("Network error — could not reach the server. Please try again.");
    }
  }

  // Download: client-side Blob + transient <a download>. Works over plain
  // HTTP (no HTTPS-only browser features, no server headers).
  function downloadTranscript() {
    if (downloadBtn.disabled || !currentSavedName || !currentTranscript) return;
    var blob = new Blob([currentTranscript], { type: "text/plain" });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = currentSavedName;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    // Defer the revocation: an immediate revoke can race with the download
    // starting in some browsers.
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  downloadBtn.addEventListener("click", function () {
    downloadTranscript();
  });

  // --- model management -----------------------------------------------------------
  // Always-visible section listing each configured provider with its
  // effective model count and a manage panel (design D7): a manual model-id
  // add, a backend discovery whose results carry Add buttons, and the
  // UI-added models with Remove buttons (config-file models never get a
  // Remove). After a successful add or remove the provider list is reloaded
  // and the picker re-rendered (design D8). Every fetched string enters the
  // DOM via textContent only; provider ids and model ids are opaque text.

  function modelCountLabel(count) {
    return count === 1 ? "1 model" : count + " models";
  }

  function renderModelManagement() {
    // Rebuild the section from the current provider list. Open panels
    // (openPanels) and cached discovery results (discoveredModels) survive
    // the re-render, so add/remove/discovery never collapse the UI.
    modelManagementList.textContent = "";
    if (!providers.length) {
      modelManagementList.hidden = true;
      modelManagementEmpty.hidden = false;
      return;
    }
    modelManagementList.hidden = false;
    modelManagementEmpty.hidden = true;
    for (var i = 0; i < providers.length; i++) {
      modelManagementList.appendChild(buildProviderItem(providers[i]));
    }
  }

  function buildProviderItem(provider) {
    var item = document.createElement("li");
    item.className = "model-provider";

    var row = document.createElement("button");
    row.type = "button";
    row.className = "model-provider-row";
    var nameSpan = document.createElement("span");
    nameSpan.className = "model-provider-name";
    nameSpan.textContent = provider.name;
    var countSpan = document.createElement("span");
    countSpan.className = "model-provider-count";
    countSpan.textContent = modelCountLabel(provider.models.length);
    var manageSpan = document.createElement("span");
    manageSpan.className = "model-provider-manage";
    manageSpan.textContent = "Manage";
    row.appendChild(nameSpan);
    row.appendChild(countSpan);
    row.appendChild(manageSpan);

    var panel = buildProviderPanel(provider);
    var open = !!openPanels[provider.id];
    panel.hidden = !open;
    row.setAttribute("aria-expanded", open ? "true" : "false");
    row.setAttribute("aria-controls", panel.id);
    row.addEventListener("click", function () {
      openPanels[provider.id] = !openPanels[provider.id];
      panel.hidden = !openPanels[provider.id];
      row.setAttribute("aria-expanded", openPanels[provider.id] ? "true" : "false");
    });

    item.appendChild(row);
    item.appendChild(panel);
    return item;
  }

  // One panel per provider: manual add, discovery, the UI-added models
  // (removable), and the config-file models (never removable from the UI).
  function buildProviderPanel(provider) {
    var panel = document.createElement("div");
    panel.className = "model-panel";
    panel.id = "model-panel-" + provider.id;
    panel.hidden = true;

    var added = provider.addedModels || [];
    var fileModels = [];
    for (var i = 0; i < provider.models.length; i++) {
      if (added.indexOf(provider.models[i]) === -1) {
        fileModels.push(provider.models[i]);
      }
    }

    // Manual add (form submit).
    var manualGroup = document.createElement("div");
    manualGroup.className = "model-panel-group";
    var manualLabel = document.createElement("span");
    manualLabel.className = "model-panel-label";
    manualLabel.textContent = "Add a model";
    var addForm = document.createElement("form");
    addForm.className = "model-add-form";
    var addInput = document.createElement("input");
    addInput.className = "model-add-input";
    addInput.type = "text";
    addInput.maxLength = 200;
    addInput.placeholder = "model id";
    addInput.autocomplete = "off";
    addInput.spellcheck = false;
    addInput.setAttribute("aria-label", "Model id to add for " + provider.name);
    var addBtn = document.createElement("button");
    addBtn.type = "submit";
    addBtn.className = "btn";
    addBtn.textContent = "Add";
    addForm.appendChild(addInput);
    addForm.appendChild(addBtn);
    manualGroup.appendChild(manualLabel);
    manualGroup.appendChild(addForm);
    panel.appendChild(manualGroup);

    addForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var modelId = addInput.value.trim();
      if (!modelId) return; // no request, no error (same rule as the URL input)
      doAddModel(provider.id, modelId, addInput);
    });

    // Discovery: a button plus the last successful result, each row with an
    // Add button (a disabled "Added" when the id is already effective).
    var discoverGroup = document.createElement("div");
    discoverGroup.className = "model-panel-group";
    var discoverLabel = document.createElement("span");
    discoverLabel.className = "model-panel-label";
    discoverLabel.textContent = "Backend models";
    var discoverBtn = document.createElement("button");
    discoverBtn.type = "button";
    discoverBtn.className = "btn btn-quiet model-item-btn model-discover-btn";
    discoverBtn.textContent = "Refresh from backend";
    var discoveredList = document.createElement("ul");
    discoveredList.className = "model-list model-discovered-list";
    discoveredList.hidden = true;
    discoverGroup.appendChild(discoverLabel);
    discoverGroup.appendChild(discoverBtn);
    discoverGroup.appendChild(discoveredList);
    panel.appendChild(discoverGroup);

    discoverBtn.addEventListener("click", function () {
      doDiscoverModels(provider, discoverBtn, discoveredList);
    });
    discoveredList.addEventListener("click", function (event) {
      var btn = event.target.closest("button");
      if (!btn || btn.disabled) return;
      var modelRow = btn.closest(".model-list-item");
      doAddModel(provider.id, modelRow.dataset.model);
    });
    renderDiscoveredList(discoveredList, provider);

    // UI-added models, each with a Remove button.
    var addedGroup = document.createElement("div");
    addedGroup.className = "model-panel-group";
    var addedLabel = document.createElement("span");
    addedLabel.className = "model-panel-label";
    addedLabel.textContent = "Added by you";
    var addedList = document.createElement("ul");
    addedList.className = "model-list model-added-list";
    var addedNote = document.createElement("p");
    addedNote.className = "model-panel-note";
    addedNote.textContent = "No models added yet.";
    addedNote.hidden = added.length > 0;
    addedGroup.appendChild(addedLabel);
    addedGroup.appendChild(addedList);
    addedGroup.appendChild(addedNote);
    panel.appendChild(addedGroup);

    addedList.addEventListener("click", function (event) {
      var btn = event.target.closest("button");
      if (!btn) return;
      var modelRow = btn.closest(".model-list-item");
      doRemoveModel(provider.id, modelRow.dataset.model);
    });
    for (var a = 0; a < added.length; a++) {
      addedList.appendChild(
        buildModelListRow(added[a], "Remove", "model-item-btn-remove")
      );
    }

    // Config-file models: shown without any Remove action.
    var fileGroup = document.createElement("div");
    fileGroup.className = "model-panel-group";
    var fileLabel = document.createElement("span");
    fileLabel.className = "model-panel-label";
    fileLabel.textContent = "From config file";
    var fileList = document.createElement("ul");
    fileList.className = "model-list model-file-list";
    fileGroup.appendChild(fileLabel);
    fileGroup.appendChild(fileList);
    panel.appendChild(fileGroup);

    for (var f = 0; f < fileModels.length; f++) {
      fileList.appendChild(buildModelListRow(fileModels[f], null, null));
    }

    return panel;
  }

  // A list row: the model id as plain text plus an optional action button.
  // The id rides in dataset.model, which the delegated list handlers read
  // from the clicked row — no closure captures a loop variable.
  function buildModelListRow(modelId, actionLabel, actionClass) {
    var row = document.createElement("li");
    row.className = "model-list-item";
    row.dataset.model = modelId;
    var idSpan = document.createElement("span");
    idSpan.className = "model-list-id";
    idSpan.textContent = modelId;
    row.appendChild(idSpan);
    if (actionLabel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn model-item-btn" + (actionClass ? " " + actionClass : "");
      btn.textContent = actionLabel;
      row.appendChild(btn);
    }
    return row;
  }

  function renderDiscoveredList(listEl, provider) {
    // Rebuild this provider's cached discovery result; ids already in the
    // effective list get a disabled "Added" button instead of Add.
    listEl.textContent = "";
    var ids = discoveredModels[provider.id];
    if (!ids || !ids.length) {
      listEl.hidden = true;
      return;
    }
    for (var i = 0; i < ids.length; i++) {
      var present = provider.models.indexOf(ids[i]) !== -1;
      var row = buildModelListRow(ids[i], present ? "Added" : "Add", null);
      if (present) row.querySelector("button").disabled = true;
      listEl.appendChild(row);
    }
    listEl.hidden = false;
  }

  async function doAddModel(providerId, modelId, inputEl) {
    clearError();
    var res;
    try {
      res = await fetch("/api/providers/" + encodeURIComponent(providerId) + "/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelId })
      });
    } catch (_) {
      showError("Network error — could not reach the server. Please try again.");
      return;
    }
    var data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok) {
      showError(
        messageFor(
          data && data.error ? data.error.code : null,
          data && data.error ? data.error.message : null
        )
      );
      return;
    }
    if (inputEl) inputEl.value = ""; // a persisted add clears the manual input
    // Success: reload the list and select the new pair (design D8).
    await loadProviders({ provider: providerId, model: modelId });
  }

  async function doRemoveModel(providerId, modelId) {
    clearError();
    var previous = providerOptions[providerPicker.selectedIndex] || null;
    var res;
    try {
      res = await fetch("/api/providers/" + encodeURIComponent(providerId) + "/models", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelId })
      });
    } catch (_) {
      showError("Network error — could not reach the server. Please try again.");
      return;
    }
    var data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok) {
      showError(
        messageFor(
          data && data.error ? data.error.code : null,
          data && data.error ? data.error.message : null
        )
      );
      return;
    }
    // Success: if the removal dropped the picker's current selection, fall
    // back to the default option; otherwise the selection is kept (design D8).
    var preferred = undefined;
    if (previous && previous.provider === providerId && previous.model === modelId) {
      preferred = null;
    }
    await loadProviders(preferred);
  }

  // Discovery never changes the effective model list; on failure it only
  // shows the discovery-specific message and leaves any previous result.
  async function doDiscoverModels(provider, discoverBtn, listEl) {
    discoverBtn.disabled = true;
    try {
      var res = await fetch(
        "/api/providers/" + encodeURIComponent(provider.id) + "/available-models"
      );
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!res.ok) {
        showError(
          messageFor(
            data && data.error ? data.error.code : null,
            data && data.error ? data.error.message : null,
            DISCOVERY_ERROR_MESSAGES
          )
        );
        return;
      }
      discoveredModels[provider.id] =
        data && Array.isArray(data.models) ? data.models : [];
      renderDiscoveredList(listEl, provider);
      clearError(); // a successful refresh clears any stale error
    } catch (_) {
      showError("Network error — could not reach the server. Please try again.");
    } finally {
      discoverBtn.disabled = false;
    }
  }

  // --- summarization --------------------------------------------------------------
  // The provider list is loaded once on page load (no polling, same
  // convention as the saved list). The picker offers one option per
  // provider/model pair; the server is the only holder of keys and base
  // URLs, so the picker never sees them. Every string enters the DOM via
  // textContent only.

  // The option index the picker pre-selects: the default provider's first
  // model, or the first option without a usable default. Shared with the
  // auto-summarize path so both always agree on the default target
  // (design D4).
  function defaultOptionIndex() {
    for (var k = 0; k < providerOptions.length; k++) {
      if (providerOptions[k].provider === defaultProviderId) return k;
    }
    return 0;
  }

  function defaultSelection() {
    return providerOptions.length ? providerOptions[defaultOptionIndex()] : null;
  }

  // Selection rule (design D8): ``preferred === undefined`` keeps the
  // picker's current selection when the same provider/model pair is still
  // offered; ``preferred === null`` selects the default option; a
  // ``preferred`` object selects that pair (falling back to the default
  // when it is no longer offered).
  function renderProviderPicker(preferred) {
    var previous = null;
    if (preferred === undefined) {
      previous = providerOptions[providerPicker.selectedIndex] || null;
    }
    providerPicker.textContent = "";
    providerOptions = [];
    for (var i = 0; i < providers.length; i++) {
      var provider = providers[i];
      for (var j = 0; j < provider.models.length; j++) {
        var option = document.createElement("option");
        option.textContent = provider.name + " — " + provider.models[j];
        providerOptions.push({ provider: provider.id, model: provider.models[j] });
        providerPicker.appendChild(option);
      }
    }
    var index = defaultOptionIndex();
    var wanted = preferred === undefined ? previous : preferred;
    if (wanted) {
      for (var k = 0; k < providerOptions.length; k++) {
        if (providerOptions[k].provider === wanted.provider &&
          providerOptions[k].model === wanted.model) {
          index = k;
          break;
        }
      }
    }
    providerPicker.selectedIndex = index;
  }

  // Loads the provider list, re-renders the picker (with the optional
  // preferred selection) and the model-management section. Called on page
  // load and after every successful model add/remove (design D8).
  async function loadProviders(preferred) {
    try {
      var res = await fetch("/api/providers");
      if (!res.ok) return; // keep the not-configured state
      var data = await res.json();
      providers = data.providers || [];
      defaultProviderId = data.default || null;
    } catch (_) {
      providers = [];
      defaultProviderId = null;
    }
    renderProviderPicker(preferred);
    renderModelManagement();
    updateSummarizeEnabled();
  }

  // --- auto-summarize setting ----------------------------------------------
  // The checkbox reflects the server-persisted autoSummarize flag (loaded on
  // page load, mirroring loadProviders: one read, no polling). Toggling posts
  // the new value; on a failed write the checkbox reverts to the last known
  // persisted value so the UI never claims a state the server does not hold
  // (design D6). All strings enter the DOM via textContent only.

  function updateAutoCheckbox() {
    autoCheckbox.checked = persistedAutoSummarize;
    // Interactive only when providers exist; disabled while summarizing (both
    // handled by updateSummarizeEnabled below).
    updateSummarizeEnabled();
  }

  async function loadSettings() {
    try {
      var res = await fetch("/api/settings");
      if (!res.ok) return; // keep the off-default
      var data = await res.json();
      persistedAutoSummarize = data && data.autoSummarize === true;
    } catch (_) {
      persistedAutoSummarize = false;
    }
    updateAutoCheckbox();
  }

  autoCheckbox.addEventListener("change", async function () {
    var next = autoCheckbox.checked;
    try {
      var res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ autoSummarize: next })
      });
      if (res.ok) {
        persistedAutoSummarize = next; // server confirms the write
      } else {
        autoCheckbox.checked = persistedAutoSummarize; // revert (design D6)
      }
    } catch (_) {
      autoCheckbox.checked = persistedAutoSummarize; // network failure: revert
    }
  });

  // Summarize is enabled only while a transcript is displayed and at least
  // one provider is configured; while a request is in flight the button and
  // the picker are both disabled. The auto-summarize checkbox needs
  // providers to have a target but not a displayed transcript (it acts on
  // the next fetch), and is disabled while any summarize is in flight.
  function updateSummarizeEnabled() {
    var enabled =
      !summarizing &&
      !resultSection.hidden &&
      providerOptions.length > 0;
    summarizeBtn.disabled = !enabled;
    providerPicker.disabled = !enabled;
    autoCheckbox.disabled = summarizing || providerOptions.length === 0;
  }

  function showSummaryPanel() {
    summaryTextEl.textContent = currentSummary;
    summaryPanel.hidden = false;
    summaryCopyBtn.disabled = false;
  }

  function clearSummary() {
    currentSummary = "";
    summaryTextEl.textContent = "";
    summaryPanel.hidden = true;
    summaryCopyBtn.disabled = true;
    // The auto note belongs to the previous transcript's summary surface:
    // any new transcript clears it (design D6).
    clearAutoNote();
  }

  // Best-effort load of a saved summary: a 404 or network error leaves the
  // panel hidden and the page unaffected (saved-transcript clicks) — the
  // auto path reads the return value to decide between skip-and-show and
  // auto-fire. Returns whether a summary was displayed.
  async function loadSavedSummary(name, token) {
    try {
      var res = await fetch("/api/transcripts/" + encodeURIComponent(name) + "/summary");
      if (!res.ok) return false;
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      // The transcript may have changed in the meantime: stale result.
      if (token !== displayToken) return false;
      if (data && typeof data.summary === "string" && data.summary) {
        currentSummary = data.summary;
        showSummaryPanel();
        return true;
      }
      return false;
    } catch (_) {
      // network failure: panel stays hidden, nothing else to do
      return false;
    }
  }

  function showSummaryCopied() {
    summaryCopyBtn.textContent = "Copied!";
    summaryCopyBtn.disabled = true;
    if (restoreSummaryCopyLabelTimer) clearTimeout(restoreSummaryCopyLabelTimer);
    restoreSummaryCopyLabelTimer = setTimeout(function () {
      summaryCopyBtn.textContent = "Copy summary";
      summaryCopyBtn.disabled = false;
      restoreSummaryCopyLabelTimer = null;
    }, 1500);
  }

  summaryCopyBtn.addEventListener("click", async function () {
    if (summaryCopyBtn.disabled || !currentSummary) return;
    var ok = await copyText(currentSummary);
    if (ok) showSummaryCopied();
  });

  // --- auto-summarize note ----------------------------------------------------
  // A subdued inline note for failed AUTOMATIC summarization (design D6):
  // unasked-for red banners on every over-long or provider-down fetch would
  // make the toggle unusable, so the auto path never calls showError and the
  // manual banner path stays untouched. The note shows only from auto calls
  // and clears with any new transcript (clearSummary), keeping the enabled
  // manual Summarize button as the explicit retry affordance.

  var AUTO_NOTE_MESSAGE =
    "Auto-summarize could not produce a summary — use Summarize to retry.";

  function showAutoNote() {
    autoNote.textContent = AUTO_NOTE_MESSAGE;
    autoNote.hidden = false;
  }

  function clearAutoNote() {
    autoNote.textContent = "";
    autoNote.hidden = true;
  }

  // One summarize path for both entry points. auto=false: the button click,
  // using the picker's current selection and the error banner for failures.
  // auto=true: the post-fetch auto-fire, using the default target (design D4)
  // and the subdued note for every failure shape (design D6). Same busy
  // state, same summarizing guard, same displayToken staleness rule.
  async function doSummarize(auto) {
    if (summarizing) {
      // Accepted consecutive-fetch behavior (design D7): if a new fetch
      // starts while an auto-summarize is in flight, this second auto-fire
      // is dropped here and the first response is discarded by the
      // displayToken rule, so the newest transcript gets no auto-summary.
      // Queueing/re-firing would add state for a rare self-inflicted race
      // in a single-user tool; manual Summarize is the retry path.
      return;
    }
    var selection;
    if (auto) {
      selection = defaultSelection();
    } else {
      if (summarizeBtn.disabled) return;
      selection = providerOptions[providerPicker.selectedIndex];
    }
    if (!selection || !currentTranscript) return;
    var token = displayToken;
    summarizing = true;
    summarizeSpinner.hidden = false;
    summarizeBtn.disabled = true;
    providerPicker.disabled = true;
    autoCheckbox.disabled = true;
    clearAutoNote();
    if (!auto) clearError();
    try {
      var res = await fetch("/api/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: currentTranscript,
          name: currentTranscriptName,
          provider: selection.provider,
          model: selection.model
        })
      });
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!res.ok || !data || typeof data.summary !== "string") {
        if (auto) {
          // Staleness rule applies to the note too: never paint an old
          // fetch's failure onto a newer transcript.
          if (token !== displayToken) return;
          showAutoNote();
          return;
        }
        var code = data && data.error ? data.error.code : null;
        var serverMessage = data && data.error ? data.error.message : null;
        showError(messageFor(code, serverMessage));
        return;
      }
      // A 2xx whose body carries no summary text is a failed summarization
      // for display (same truthiness check as loadSavedSummary): show the
      // error region, never an empty panel.
      if (!data.summary) {
        if (auto) {
          if (token !== displayToken) return;
          showAutoNote();
          return;
        }
        showError(
          "The summarization backend returned no summary text. Please try again."
        );
        return;
      }
      // Staleness rule: a late response must not paint over a transcript
      // displayed in the meantime.
      if (token !== displayToken) return;
      currentSummary = data.summary;
      showSummaryPanel();
    } catch (_) {
      if (auto) {
        if (token !== displayToken) return;
        showAutoNote();
      } else {
        showError("Network error — could not reach the server. Please try again.");
      }
    } finally {
      summarizing = false;
      summarizeSpinner.hidden = true;
      updateSummarizeEnabled();
    }
  }

  summarizeBtn.addEventListener("click", function () {
    doSummarize(false);
  });

  // --- log viewer -----------------------------------------------------------------
  // The server's structured log stream (SSE) is appended live as humanized
  // lines. Visibility is purely a display concern: entries keep accumulating
  // while the panel is hidden, so re-showing it includes what was logged in
  // the meantime. Every string enters the DOM via textContent only.

  var logPanel = document.getElementById("log-panel");
  var logsToggle = document.getElementById("logs-toggle");
  var LOG_DISPLAY_CAP = 200;

  // Known event types get a dedicated one-line format; anything else falls
  // back to "event  key=value ..." (see formatLogEntry).
  var LOG_FORMATTERS = {
    server_started: function (e) {
      return "server started on port " + e.port;
    },
    server_stopped: function (e) {
      return "server stopped";
    },
    http_request: function (e) {
      return e.method + " " + e.path + " -> " + e.status + " (" + e.duration_ms + " ms)";
    },
    fetch_attempt: function (e) {
      if (e.outcome === "success") {
        return (
          "fetched " + e.video_id + " via " + e.source +
          " in " + e.duration_ms + " ms (" + e.chars + " chars)"
        );
      }
      var line = "fetch failed: " + e.video_id + " via " + e.source +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    fetch_rejected: function (e) {
      return "fetch rejected: " + e.video_id + " [" + e.reason + "]";
    },
    transcript_saved: function (e) {
      return (
        "transcript saved: " + e.video_id + " -> " + e.path +
        " (" + e.bytes + " bytes)"
      );
    },
    transcript_save_failed: function (e) {
      var line = "transcript save failed: " + e.video_id + " at " + e.path +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    summary_completed: function (e) {
      return (
        "summary completed: " + e.provider + "/" + e.model +
        " in " + e.duration_ms + " ms (" + e.chars_in + " chars in, " +
        e.chars_out + " chars out)"
      );
    },
    summary_failed: function (e) {
      var line = "summary failed: " + e.provider + "/" + e.model +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    summary_save_failed: function (e) {
      var line = "summary save failed: " + e.name + " at " + e.path +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    config_load_failed: function (e) {
      var line = "provider config load failed: " + e.path +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    provider_model_added: function (e) {
      return "model added: " + e.provider + "/" + e.model;
    },
    provider_model_removed: function (e) {
      return "model removed: " + e.provider + "/" + e.model;
    },
    provider_models_refreshed: function (e) {
      return (
        "models refreshed: " + e.provider +
        " (" + e.count + " models, " + e.duration_ms + " ms)"
      );
    },
    provider_models_refresh_failed: function (e) {
      var line = "models refresh failed: " + e.provider +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    provider_overrides_load_failed: function (e) {
      var line = "provider overrides load failed: " + e.path +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    provider_overrides_save_failed: function (e) {
      var line = "provider overrides save failed: " + e.path +
                 " [" + e.reason + "]";
      if (e.detail) line += " " + e.detail;
      return line;
    },
    unhandled_exception: function (e) {
      var message = "";
      if (e.exc_info) {
        // Keep the entry on one line: use the exception's final line.
        var lines = String(e.exc_info).split("\n");
        message = lines[lines.length - 1].trim();
      }
      return "unhandled exception" + (message ? ": " + message : "");
    }
  };

  function logTime(timestamp) {
    var date = timestamp ? new Date(timestamp) : new Date();
    return isNaN(date.getTime()) ? "" : date.toISOString().slice(11, 19);
  }

  function formatLogEntry(entry) {
    var event = entry.event || "unknown";
    var level = String(entry.level || "info").toUpperCase();
    var formatter = LOG_FORMATTERS[event];
    var body;
    if (formatter) {
      body = formatter(entry);
    } else {
      var fields = [];
      for (var key in entry) {
        if (!Object.prototype.hasOwnProperty.call(entry, key)) continue;
        if (key === "event" || key === "level" || key === "timestamp") continue;
        fields.push(key + "=" + entry[key]);
      }
      body = event + (fields.length ? "  " + fields.join(" ") : "");
    }
    return logTime(entry.timestamp) + "  " + level + "  " + body;
  }

  function appendLogEntry(entry) {
    var line = document.createElement("div");
    line.className = "log-line";
    line.textContent = formatLogEntry(entry);
    logPanel.appendChild(line);
    while (logPanel.childNodes.length > LOG_DISPLAY_CAP) {
      logPanel.removeChild(logPanel.firstChild);
    }
  }

  logsToggle.addEventListener("click", function () {
    logPanel.hidden = !logPanel.hidden;
    logsToggle.textContent = logPanel.hidden ? "Show logs" : "Hide logs";
  });

  if (typeof EventSource !== "undefined") {
    var logSource = new EventSource("/api/logs");
    logSource.addEventListener("message", function (event) {
      var entry = null;
      try {
        entry = JSON.parse(event.data);
      } catch (_) {
        return; // unparseable payload: nothing to show
      }
      appendLogEntry(entry);
    });
    // EventSource reconnects automatically; nothing to do on error.
  }

  // Load once on page load. There is no automatic polling (design decision 6).
  loadSavedList();
  loadProviders();
  loadSettings();
})();
