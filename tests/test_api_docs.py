import importlib

import pytest
from fastapi.testclient import TestClient

import app.main
from app.core.config import get_settings


@pytest.fixture
def docs_disabled(monkeypatch):
    # The setting is read when the app is built, so build a separate one and restore afterwards.
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    get_settings.cache_clear()
    original = app.main.app
    yield importlib.reload(app.main).app
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(app.main)
    app.main.app = original


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_are_served_by_default(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_can_be_turned_off(docs_disabled, path):
    client = TestClient(docs_disabled)
    assert client.get(path).status_code == 404
    assert client.get("/health").status_code == 200
