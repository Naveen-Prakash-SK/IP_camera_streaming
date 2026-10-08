from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_public_access_cameras():
    """Verify /api/cameras is accessible without any authentication."""
    response = client.get("/api/cameras")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_public_access_streams():
    """Verify /api/streams is accessible without any authentication."""
    response = client.get("/api/streams")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_public_access_live_stream():
    """Verify /api/stream/CAM01 is accessible without any authentication."""
    response = client.get("/api/stream/CAM01?max_frames=1")
    assert response.status_code == 200
    assert "multipart/x-mixed-replace" in response.headers["content-type"]


def test_public_access_files():
    """Verify /api/files is accessible without any authentication."""
    response = client.get("/api/files")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_public_access_info():
    """Verify /api/info is accessible without any authentication."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
