from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_cameras():
    """Verify listing all 4 cameras."""
    response = client.get("/api/cameras")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) >= 4
    cam_ids = [c["camera_id"] for c in cameras]
    assert "CAM01" in cam_ids
    assert "CAM02" in cam_ids
    assert "CAM03" in cam_ids
    assert "CAM04" in cam_ids


def test_unconfigured_camera_status():
    """Verify unconfigured cameras have NOT_CONFIGURED or OFFLINE status."""
    response = client.get("/api/cameras/CAM01")
    assert response.status_code == 200
    cam = response.json()
    assert cam["camera_id"] == "CAM01"
    assert cam["status"] in ["NOT_CONFIGURED", "OFFLINE", "CONNECTING"]


def test_camera_not_found():
    """Verify 404 for non-existent camera ID."""
    response = client.get("/api/cameras/UNKNOWN_99")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_camera_controls():
    """Verify start, stop, and restart endpoints for a camera."""
    # Stop
    res_stop = client.post("/api/cameras/CAM01/stop")
    assert res_stop.status_code == 200
    assert res_stop.json()["camera_id"] == "CAM01"
    assert res_stop.json()["status"] == "STOPPED"

    # Start
    res_start = client.post("/api/cameras/CAM01/start")
    assert res_start.status_code == 200
    assert res_start.json()["camera_id"] == "CAM01"

    # Restart
    res_restart = client.post("/api/cameras/CAM01/restart")
    assert res_restart.status_code == 200
    assert res_restart.json()["camera_id"] == "CAM01"
