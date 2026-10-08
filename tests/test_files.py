import io
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_file_upload_and_download_flow():
    """Verify chunked upload, metadata retrieval, listing, and download without auth."""
    # 1. Create dummy video bytes
    dummy_video_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"A" * 1024
    file_payload = ("test_recording.mp4", io.BytesIO(dummy_video_bytes), "video/mp4")

    # Upload
    res_upload = client.post(
        "/api/files/upload",
        files={"file": file_payload},
        data={"camera_id": "CAM01", "capture_start_utc": "2026-10-08T12:00:00Z"},
    )
    assert res_upload.status_code == 201
    meta = res_upload.json()
    assert "file_id" in meta
    file_id = meta["file_id"]
    assert meta["camera_id"] == "CAM01"
    assert meta["filename"] == "test_recording.mp4"
    assert meta["size_bytes"] == len(dummy_video_bytes)
    assert len(meta["checksum_sha256"]) == 64

    # 2. List files
    res_list = client.get("/api/files")
    assert res_list.status_code == 200
    files = res_list.json()
    assert any(f["file_id"] == file_id for f in files)

    # 3. Filter by camera
    res_filter = client.get("/api/files?camera_id=CAM01")
    assert res_filter.status_code == 200
    assert all(f["camera_id"] == "CAM01" for f in res_filter.json())

    # 4. Get metadata
    res_meta = client.get(f"/api/files/{file_id}")
    assert res_meta.status_code == 200
    assert res_meta.json()["file_id"] == file_id

    # 5. Download file
    res_dl = client.get(f"/api/files/{file_id}/download")
    assert res_dl.status_code == 200
    assert res_dl.content == dummy_video_bytes


def test_file_not_found():
    """Verify 404 for non-existent file UUID."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/files/{fake_id}")
    assert res.status_code == 404


def test_path_traversal_protection():
    """Verify non-UUID / path traversal file_id is rejected with 400 Bad Request."""
    res_traversal = client.get("/api/files/..-..-secret_key.txt")
    assert res_traversal.status_code == 400
    assert "Invalid file_id format" in res_traversal.json()["detail"]

    res_invalid = client.get("/api/files/invalid-filename.mp4")
    assert res_invalid.status_code == 400
    assert "Invalid file_id format" in res_invalid.json()["detail"]
