"""T-TRANSCRIPT-RETRIEVAL-006 .. 010 (library mocked)"""

import pytest

from app import fetchers


# --- fakes ------------------------------------------------------------------

class FakeSnippet:
    def __init__(self, text):
        self.text = text


class FakeFetched:
    def __init__(self, texts, language_code):
        self.snippets = [FakeSnippet(t) for t in texts]
        self.language_code = language_code


class FakeTranscript:
    def __init__(self, language_code, is_generated, texts):
        self.language_code = language_code
        self.is_generated = is_generated
        self._texts = texts

    def fetch(self, preserve_formatting=False):
        return FakeFetched(self._texts, self.language_code)


class FakeApi:
    def __init__(self, http_client=None, transcripts=()):
        self._transcripts = list(transcripts)

    def list(self, video_id):
        return self._transcripts


def _install(monkeypatch, transcripts):
    monkeypatch.setattr(fetchers, "YouTubeTranscriptApi",
                        lambda http_client=None: FakeApi(transcripts=transcripts))
    monkeypatch.setattr(fetchers, "fetch_video_title", lambda video_id: "Fake Title")


def _fetch(monkeypatch, transcripts):
    _install(monkeypatch, transcripts)
    return fetchers.primary_fetch("dQw4w9WgXcQ", "en")


# --- tests ------------------------------------------------------------------

def test_manual_track_preferred(monkeypatch):
    transcripts = (
        FakeTranscript("en", True, ["auto generated text"]),
        FakeTranscript("en", False, ["manual text"]),
    )
    text, language, title = _fetch(monkeypatch, transcripts)
    assert text == "manual text"
    assert language == "en"
    assert title == "Fake Title"


def test_auto_generated_track_used(monkeypatch):
    transcripts = (FakeTranscript("en", True, ["only auto text"]),)
    text, language, _ = _fetch(monkeypatch, transcripts)
    assert text == "only auto text"
    assert language == "en"


def test_english_track_preferred(monkeypatch):
    transcripts = (
        FakeTranscript("de", False, ["german text"]),
        FakeTranscript("en", False, ["english text"]),
    )
    text, language, _ = _fetch(monkeypatch, transcripts)
    assert language == "en"
    assert text == "english text"


def test_non_english_track_reported(monkeypatch):
    transcripts = (FakeTranscript("de", False, ["nur deutsch"]),)
    text, language, _ = _fetch(monkeypatch, transcripts)
    assert language == "de"
    assert text == "nur deutsch"


def test_output_is_clean_plain_text(monkeypatch):
    dirty = [
        "Hello&nbsp;world",          # HTML entity
        "Second&nbsp;line&nbsp;with&nbsp;-->",
        "[00:12] bracket timestamp",
        "<s>ssml tag</s> here",
        "plain   spaced    out",
    ]
    transcripts = (FakeTranscript("en", False, dirty),)
    text, _, _ = _fetch(monkeypatch, transcripts)

    assert "Hello world" in text
    assert "&nbsp;" not in text
    assert "<" not in text and ">" not in text
    assert "[00:12]" not in text
    assert "-->" not in text
    assert "plain spaced out" in text


def test_response_includes_derived_name(monkeypatch, tmp_path):
    """T-TRANSCRIPT-RETRIEVAL-017 — the fetch response's file-name field is
    the exact name the persistence layer writes the file under."""
    from starlette.testclient import TestClient

    from app import chain as chain_mod
    from app.chain import FetchResult
    from app.main import create_app

    class FakeChain:
        def __init__(self):
            self.calls = []

        async def run(self, url):
            self.calls.append(url)
            return FetchResult(
                text="The end of the LLMs, NCM and all.",
                video_id="dQw4w9WgXcQ",
                title="The End of LLMs? (NCM)",
                language="en",
                source="primary",
            )

    fake = FakeChain()
    monkeypatch.setattr(chain_mod, "default_chain", fake)
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path / "transcripts"))

    client = TestClient(create_app())
    with client:
        response = client.post(
            "/api/transcript",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 200
    # the same title-based derivation the persistence layer uses
    assert response.json()["name"] == "the_end_of_llms_ncm.txt"
