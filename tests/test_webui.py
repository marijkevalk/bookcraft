"""Tests for the local web UI (Flask). Gemini is mocked; no network."""

import json
import re
from pathlib import Path

import pytest

from bookcraft import ai_chapters, webui

FIXTURES = Path(__file__).parent / "fixtures"

# Chapter structure the mocked model returns for author A's manuscript.
_CHAPTERS_JSON = (
    '{"chapters": ['
    '{"title_idx": 0, "pov_idx": -1, "pov": "Aria"},'
    '{"title_idx": 3, "pov_idx": -1, "pov": "Ryder"}'
    "]}"
)


class _FakeGeminiResponse:
    def __init__(self, text):
        self._payload = {
            "candidates": [{"content": {"parts": [{"text": text}]}}]
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


@pytest.fixture
def client(monkeypatch):
    # Never touch the real ~/.bookcraft during tests.
    monkeypatch.setattr(webui, "get_saved_api_key", lambda: "")
    monkeypatch.setattr(webui, "save_config", lambda values: None)
    app = webui.create_app()
    app.testing = True
    return app.test_client()


def _mock_gemini_ok(monkeypatch, text=_CHAPTERS_JSON):
    monkeypatch.setattr(
        ai_chapters.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeGeminiResponse(text),
    )


def _post_book(client, **overrides):
    data = {
        "api_key": "test-key",
        "title": "Claimed by the Enemy",
        "subtitle": "A Steamy Mafia Romance",
        "series": "Claimed Series",
        "pen_name": "Sylvia Heart",
        "book_number": "1",
        "about": "Sylvia writes romance.\nShe lives in the Netherlands.",
    }
    data.update(overrides)
    with open(FIXTURES / "book_author_A.docx", "rb") as fh:
        data["manuscript"] = (fh, "book_author_A.docx")
        return client.post("/format", data=data,
                           content_type="multipart/form-data")


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Gemini" in body
    assert "Format my book" in body


def test_format_end_to_end(client, monkeypatch):
    _mock_gemini_ok(monkeypatch)
    resp = _post_book(client)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Download your files" in body

    token = re.search(r"/download/([0-9a-f]+)/ebook", body).group(1)
    for which in ("ebook", "paperback", "zip"):
        dl = client.get(f"/download/{token}/{which}")
        assert dl.status_code == 200
        assert len(dl.get_data()) > 0


def test_format_requires_manuscript(client):
    resp = client.post("/format", data={"api_key": "k", "title": "t"},
                       content_type="multipart/form-data")
    assert "choose a manuscript" in resp.get_data(as_text=True)


def test_format_requires_key(client):
    with open(FIXTURES / "book_author_A.docx", "rb") as fh:
        resp = client.post(
            "/format",
            data={"api_key": "", "title": "t", "subtitle": "s",
                  "series": "x", "pen_name": "p",
                  "manuscript": (fh, "book_author_A.docx")},
            content_type="multipart/form-data",
        )
    assert "Gemini API key" in resp.get_data(as_text=True)


def test_format_requires_metadata(client, monkeypatch):
    _mock_gemini_ok(monkeypatch)
    resp = _post_book(client, title="", subtitle="")
    body = resp.get_data(as_text=True)
    assert "Please fill in" in body
    assert "Title" in body


def test_bad_key_gives_friendly_error(client, monkeypatch):
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(ai_chapters.urllib.request, "urlopen", boom)
    body = _post_book(client).get_data(as_text=True)
    assert "rejected" in body.lower() or "api key" in body.lower()


def test_unknown_download_token_404(client):
    assert client.get("/download/deadbeef/ebook").status_code == 404
