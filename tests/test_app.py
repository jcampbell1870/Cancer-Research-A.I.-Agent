import pytest

import app as app_module
from agent import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "RESULTS_PATH", str(tmp_path / "results.json"))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    return app_module.app.test_client()


def auth(token):
    return {"Authorization": "Bearer " + token}


def fake_run():
    return {"generated_at": "2026-10-05T23:00:00+00:00", "errors": [], "findings": [{"id": "x"}],
            "stats": {"total": 1}}


def test_health_and_index(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    body = client.get("/").get_json()
    assert body["last_refreshed"] is None
    assert body["endpoints"]["results"] == "/api/results"


def test_results_missing(client):
    assert client.get("/api/results").status_code == 404


def test_refresh_requires_token(client, monkeypatch):
    monkeypatch.delenv("REFRESH_TOKEN", raising=False)
    assert client.post("/api/refresh").status_code == 403
    monkeypatch.setenv("REFRESH_TOKEN", "secret")
    assert client.post("/api/refresh").status_code == 401
    assert client.post("/api/refresh", headers=auth("wrong")).status_code == 401


def test_refresh_runs_agent_and_serves_results(client, monkeypatch):
    monkeypatch.setenv("REFRESH_TOKEN", "secret")
    monkeypatch.setattr(app_module, "run_research", fake_run)
    response = client.post("/api/refresh", headers=auth("secret"))
    assert response.status_code == 200
    results = client.get("/api/results")
    assert results.get_json()["findings"] == [{"id": "x"}]
    assert results.headers["Access-Control-Allow-Origin"] == "*"
    assert client.get("/").get_json()["findings"] == 1


def test_refresh_all_sources_failed(client, monkeypatch):
    monkeypatch.setenv("REFRESH_TOKEN", "secret")
    monkeypatch.setattr(app_module, "run_research",
                        lambda: {"errors": ["a", "b", "c"], "findings": []})
    response = client.post("/api/refresh", headers=auth("secret"))
    assert response.status_code == 502
    assert client.get("/api/results").status_code == 404
