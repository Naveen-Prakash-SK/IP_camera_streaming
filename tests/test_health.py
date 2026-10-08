from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_public():
    """Verify /health is public and returns operational status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert data["gateway"] == "ONLINE"
    assert "cameras" in data
    assert "timestamp" in data


def test_api_info():
    """Verify /api/info succeeds without authentication."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Standalone Video Gateway"
    assert data["status"] == "ONLINE"
    assert data["camera_count"] >= 4
