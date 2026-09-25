from fastapi.testclient import TestClient
import pytest
from src.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["security_enabled"] is True
    assert data["runbooks_indexed"] >= 0


def test_security_validate_endpoint(client):
    # Safe command
    resp = client.post("/api/v1/security/validate", json={"command": "df -h"})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Dangerous command
    resp_bad = client.post("/api/v1/security/validate", json={"command": "rm -rf /"})
    assert resp_bad.status_code == 200
    assert resp_bad.json()["allowed"] is False
    assert resp_bad.json()["risk_level"] == "BLOCKED"


def test_system_diagnose_endpoint(client):
    resp = client.post("/api/v1/system/diagnose", json={"target": "disk", "path": "/"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "output" in data


def test_agent_run_endpoint(client):
    resp = client.post("/api/v1/agent/run", json={"query": "Заканчивается свободное место на диске"})
    assert resp.status_code == 200
    data = resp.json()
    assert "final_answer" in data
    assert len(data["steps"]) >= 1
