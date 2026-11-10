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
      "This transcript is too long to summarize (over 100,000 characters)."
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

  function messageFor(code, serverMessage) {
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

  function renderProviderPicker() {
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
    // Pre-select the default provider's first model; without a usable
    // default, the first option.
    providerPicker.selectedIndex = defaultOptionIndex();
  }

  async function loadProviders() {
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
    renderProviderPicker();
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
