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
      "The server is busy with another transcript right now. Please try again in a moment."
  };

  var currentTranscript = "";
  // Real file name of the displayed saved transcript ("" for a freshly
  // fetched transcript, which the UI has no trustworthy name to download).
  var currentSavedName = "";
  var restoreCopyLabelTimer = null;

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
    downloadBtn.disabled = true;
    titleEl.textContent = data.title || "";
    langEl.textContent = data.language ? "Language: " + data.language : "";
    panel.textContent = data.text;
    resultSection.hidden = false;
    copyBtn.disabled = false;
    panel.scrollTop = 0;
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
      titleEl.textContent = data.name;
      langEl.textContent = ""; // no language to show for a saved transcript
      panel.textContent = data.text;
      resultSection.hidden = false;
      copyBtn.disabled = false;
      // Only a saved transcript has a trustworthy file name to download.
      downloadBtn.disabled = false;
      panel.scrollTop = 0;
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

  // Load once on page load. There is no automatic polling (design decision 6).
  loadSavedList();
})();
