from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from app.routes.transcribe import router as transcribe_router

    app = FastAPI()
    app.include_router(transcribe_router)
    return TestClient(app, raise_server_exceptions=False)


def test_transcribe_happy_path_with_mocked_service():
    with patch("app.routes.transcribe.transcribe_audio_bytes", return_value="hello world"):
        with _client() as client:
            files = {"audio": ("voice.m4a", b"fake-audio-bytes", "audio/m4a")}
            data = {"locale": "en-US"}
            resp = client.post("/transcribe", files=files, data=data)

    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "hello world"
    assert resp.json()["locale"] == "en-US"


def test_transcribe_rejects_non_audio_file():
    with _client() as client:
        files = {"audio": ("notes.txt", b"not-audio", "text/plain")}
        data = {"locale": "en-US"}
        resp = client.post("/transcribe", files=files, data=data)

    assert resp.status_code == 400


def test_transcribe_rejects_empty_file():
    with _client() as client:
        files = {"audio": ("voice.m4a", b"", "audio/m4a")}
        data = {"locale": "en-US"}
        resp = client.post("/transcribe", files=files, data=data)

    assert resp.status_code == 400


def test_transcribe_validates_locale():
    with _client() as client:
        files = {"audio": ("voice.m4a", b"fake-audio", "audio/m4a")}
        data = {"locale": "fr-FR"}
        resp = client.post("/transcribe", files=files, data=data)

    assert resp.status_code == 422
