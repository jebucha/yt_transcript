"""Error taxonomy for transcript retrieval.

Each error carries a machine-readable ``code`` and an HTTP ``status``, plus a
stable human-readable ``message`` the UI can display directly.
"""

from __future__ import annotations


class TranscriptError(Exception):
    """Base class for all transcript fetch errors."""

    code: str = ""
    status: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message

    @property
    def default_message(self) -> str:
        return ""


class InvalidUrlError(TranscriptError):
    code = "INVALID_URL"
    status = 400

    @property
    def default_message(self) -> str:
        return "That does not look like a valid YouTube video URL or ID."


class VideoUnavailableError(TranscriptError):
    code = "VIDEO_UNAVAILABLE"
    status = 404

    @property
    def default_message(self) -> str:
        return "This video is unavailable. It may be private, deleted, or region-locked."


class NoCaptionsError(TranscriptError):
    code = "NO_CAPTIONS"
    status = 404

    @property
    def default_message(self) -> str:
        return "This video has no captions available."


class UpstreamFailureError(TranscriptError):
    code = "UPSTREAM_FAILURE"
    status = 502

    @property
    def default_message(self) -> str:
        return (
            "Could not fetch the transcript from YouTube. This can happen when "
            "YouTube is rate-limiting or blocking the server; please try again later."
        )


class BusyError(TranscriptError):
    code = "BUSY"
    status = 503

    @property
    def default_message(self) -> str:
        return "The server is busy with another transcript. Please try again in a moment."


class SummaryNotConfiguredError(TranscriptError):
    code = "NOT_CONFIGURED"
    status = 503

    @property
    def default_message(self) -> str:
        return (
            "Summarization is not configured — no usable providers were found. "
            "Add a providers.json file (or point PROVIDERS_CONFIG at one) to enable it."
        )


class InvalidProviderError(TranscriptError):
    code = "INVALID_PROVIDER"
    status = 400

    @property
    def default_message(self) -> str:
        return (
            "Unknown provider or model — it may no longer be configured. "
            "Reload the page and try again."
        )


class ProviderError(TranscriptError):
    code = "PROVIDER_ERROR"
    status = 502

    @property
    def default_message(self) -> str:
        return "The summarization backend failed. Please try again."


class InputTooLongError(TranscriptError):
    code = "INPUT_TOO_LONG"
    status = 400

    @property
    def default_message(self) -> str:
        return "This transcript is too long to summarize (over 100,000 characters)."


# Codes for which a fallback attempt is made (transient upstream problems only).
FALLBACK_CODES = frozenset({"UPSTREAM_FAILURE"})
