import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.models import VideoFileMetadata
from app.services.file_manager import file_manager

router = APIRouter(prefix="/api/files", tags=["Recorded Files"])


@router.post("/upload", response_model=VideoFileMetadata, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    camera_id: str = Form(...),
    capture_start_utc: Optional[str] = Form(None),
    timestamp: Optional[str] = Form(None),
) -> VideoFileMetadata:
    """
    Upload a recorded video file with chunked disk streaming.
    Supports either capture_start_utc or timestamp form field.
    """
    chosen_timestamp = capture_start_utc or timestamp or datetime.now(timezone.utc).isoformat()
    return await file_manager.save_upload(
        file=file,
        camera_id=camera_id,
        capture_start_utc=chosen_timestamp,
    )


@router.get("", response_model=List[VideoFileMetadata])
def list_files(camera_id: Optional[str] = None) -> List[VideoFileMetadata]:
    """List stored recorded video files, optionally filtered by camera_id."""
    return file_manager.list_files(camera_id=camera_id)


@router.get("/{file_id}", response_model=VideoFileMetadata)
def get_file_metadata(file_id: str) -> VideoFileMetadata:
    """Retrieve metadata for a specific recorded video file."""
    return file_manager.get_file_metadata(file_id)


@router.get("/{file_id}/download")
def download_file(file_id: str):
    """
    Stream download a recorded video file with HTTP Range support for video scrubbing.
    """
    meta = file_manager.get_file_metadata(file_id)
    video_path = file_manager.get_video_file_path(file_id)

    # Determine media type based on extension
    ext = os.path.splitext(meta.filename)[1].lower()
    media_type = "video/mp4" if ext == ".mp4" else "application/octet-stream"

    return FileResponse(
        path=str(video_path),
        filename=meta.filename,
        media_type=media_type,
    )
