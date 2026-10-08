from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_streams():
    """Verify listing all streams metadata without auth."""
    response = client.get("/api/streams")
    assert response.status_code == 200
    streams = response.json()
    assert len(streams) >= 4
    cam_ids = [s["camera_id"] for s in streams]
    assert "CAM01" in cam_ids
    assert "stream_url" in streams[0]


def test_stream_info_single():
    """Verify stream metadata for a single camera without auth."""
    response = client.get("/api/streams/CAM01")
    assert response.status_code == 200
    info = response.json()
    assert info["camera_id"] == "CAM01"
    assert "/api/stream/CAM01" in info["stream_url"]


def test_stream_info_not_found():
    """Verify 404 for unknown stream ID."""
    response = client.get("/api/streams/CAM99")
    assert response.status_code == 404


def test_live_stream_endpoint_content_type():
    """Verify /api/stream/CAM01 returns multipart/x-mixed-replace with status frame without auth."""
    response = client.get("/api/stream/CAM01?max_frames=1")
    assert response.status_code == 200
    assert "multipart/x-mixed-replace" in response.headers["content-type"]
    assert "boundary=frame" in response.headers["content-type"]
    assert b"--frame" in response.content
    assert b"Content-Type: image/jpeg" in response.content
    assert b"X-Timestamp" in response.content
