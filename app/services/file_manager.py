import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import aiofiles
import cv2
from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.models import VideoFileMetadata

logger = logging.getLogger(__name__)

UUID_REGEX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class FileManager:
    def __init__(self):
        self._videos_dir = settings.videos_dir
        self._metadata_dir = settings.metadata_dir

    def _sanitize_file_id(self, file_id: str) -> str:
        clean_id = file_id.strip()
        if not UUID_REGEX.match(clean_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file_id format: '{file_id}'. Must be a standard UUID.",
            )
        return clean_id

    def _get_video_path(self, file_id: str, extension: str = ".mp4") -> Path:
        clean_id = self._sanitize_file_id(file_id)
        path = (self._videos_dir / f"{clean_id}{extension}").resolve()
        # Verify path traversal protection
        if not str(path).startswith(str(self._videos_dir.resolve())):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal detected",
            )
        return path

    def _get_metadata_path(self, file_id: str) -> Path:
        clean_id = self._sanitize_file_id(file_id)
        path = (self._metadata_dir / f"{clean_id}.json").resolve()
        if not str(path).startswith(str(self._metadata_dir.resolve())):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal detected",
            )
        return path

    def probe_video_metadata(self, file_path: Path) -> Tuple[Optional[str], Optional[float], Optional[float]]:
        """
        Probe codec, fps, and duration_s.
        Uses ffprobe if available on PATH; otherwise falls back to OpenCV.
        """
        codec: Optional[str] = None
        fps: Optional[float] = None
        duration_s: Optional[float] = None

        # 1. Attempt probing via ffprobe
        ffprobe_bin = shutil.which("ffprobe")
        if ffprobe_bin:
            try:
                cmd = [
                    ffprobe_bin,
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name,r_frame_rate,duration:format=duration",
                    "-of", "json",
                    str(file_path),
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    streams = data.get("streams", [])
                    if streams:
                        vstream = streams[0]
                        codec = vstream.get("codec_name")
                        rate_str = vstream.get("r_frame_rate")
                        if rate_str and "/" in rate_str:
                            num, den = rate_str.split("/")
                            if float(den) > 0:
                                fps = round(float(num) / float(den), 2)
                        if "duration" in vstream:
                            try:
                                duration_s = round(float(vstream["duration"]), 2)
                            except Exception:
                                pass

                    format_info = data.get("format", {})
                    if duration_s is None and "duration" in format_info:
                        try:
                            duration_s = round(float(format_info["duration"]), 2)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"ffprobe probe failed: {e}")

        # 2. Fallback to OpenCV if ffprobe couldn't determine fields
        if codec is None or fps is None or duration_s is None:
            try:
                cap = cv2.VideoCapture(str(file_path))
                if cap.isOpened():
                    if fps is None:
                        f = cap.get(cv2.CAP_PROP_FPS)
                        if f > 0:
                            fps = round(f, 2)
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if duration_s is None and fps and fps > 0 and frame_count > 0:
                        duration_s = round(frame_count / fps, 2)
                    if codec is None:
                        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
                        fourcc_str = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).strip()
                        if fourcc_str:
                            codec = fourcc_str
                    cap.release()
            except Exception as e:
                logger.debug(f"OpenCV fallback probe failed: {e}")

        return codec, fps, duration_s

    async def save_upload(
        self,
        file: UploadFile,
        camera_id: str,
        capture_start_utc: str,
    ) -> VideoFileMetadata:
        """Stream uploaded file directly to disk in 64KB chunks to protect RAM."""
        safe_filename = os.path.basename(file.filename or "recording.mp4")
        ext = os.path.splitext(safe_filename)[1].lower()
        if not ext:
            ext = ".mp4"

        file_id = str(uuid.uuid4())
        dest_video_path = self._get_video_path(file_id, extension=ext)
        metadata_path = self._get_metadata_path(file_id)

        sha256 = hashlib.sha256()
        total_size = 0
        chunk_size = 65536  # 64 KB

        try:
            async with aiofiles.open(dest_video_path, "wb") as out_file:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    sha256.update(chunk)
                    total_size += len(chunk)
                    await out_file.write(chunk)
        except Exception as e:
            # Clean up partial video on error
            if dest_video_path.is_file():
                try:
                    dest_video_path.unlink()
                except Exception:
                    pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to stream and store file: {str(e)}",
            )

        # Probe video metrics
        codec, fps, duration_s = self.probe_video_metadata(dest_video_path)

        meta = VideoFileMetadata(
            file_id=file_id,
            filename=safe_filename,
            camera_id=camera_id.upper(),
            capture_start_utc=capture_start_utc,
            size_bytes=total_size,
            checksum_sha256=sha256.hexdigest(),
            duration_s=duration_s,
            codec=codec,
            fps=fps,
            storage_path=str(dest_video_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Write metadata file
        async with aiofiles.open(metadata_path, "w", encoding="utf-8") as meta_file:
            await meta_file.write(meta.model_dump_json(indent=2))

        logger.info(f"Successfully stored video file {file_id} ({safe_filename}, {total_size} bytes)")
        return meta

    def list_files(self, camera_id: Optional[str] = None) -> List[VideoFileMetadata]:
        """List all stored recorded files with metadata."""
        results: List[VideoFileMetadata] = []
        for meta_file in self._metadata_dir.glob("*.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                item = VideoFileMetadata(**data)
                if camera_id is None or item.camera_id == camera_id.upper():
                    results.append(item)
            except Exception as e:
                logger.warning(f"Failed to read metadata file {meta_file}: {e}")

        # Sort newest first
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results

    def get_file_metadata(self, file_id: str) -> VideoFileMetadata:
        """Fetch metadata for a specific file."""
        meta_path = self._get_metadata_path(file_id)
        if not meta_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File {file_id} not found")

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VideoFileMetadata(**data)

    def get_video_file_path(self, file_id: str) -> Path:
        """Locate the actual video file path for download."""
        meta = self.get_file_metadata(file_id)
        p = Path(meta.storage_path)
        if not p.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file missing on disk")
        return p


file_manager = FileManager()
