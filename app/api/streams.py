import asyncio
import logging
from typing import AsyncGenerator, List
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.models import CameraStatus, StreamInfo
from app.services.camera_manager import camera_manager
from app.services.stream_manager import CameraStream

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Streams"])


def _get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/api/streams", response_model=List[StreamInfo])
def list_streams(request: Request) -> List[StreamInfo]:
    """Retrieve all available live stream URLs and metadata."""
    base_url = _get_base_url(request)
    return [cam.to_stream_info(base_url) for cam in camera_manager.get_all_cameras()]


@router.get("/api/streams/{camera_id}", response_model=StreamInfo)
def get_stream_info(camera_id: str, request: Request) -> StreamInfo:
    """Retrieve stream metadata for a specific camera."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )
    return cam.to_stream_info(_get_base_url(request))


async def mjpeg_frame_generator(
    cam: CameraStream, request: Request, max_frames: Optional[int] = None
) -> AsyncGenerator[bytes, None]:
    """
    Continuous MJPEG multipart frame stream generator.
    Yields multipart/x-mixed-replace chunks with ISO-8601 UTC timestamps in headers.
    Checks request.is_disconnected() to exit cleanly on client disconnect.
    """
    queue = await cam.subscribe()
    frames_sent = 0
    try:
        while True:
            if await request.is_disconnected():
                break

            if cam.status == CameraStatus.ONLINE:
                try:
                    jpeg_bytes, timestamp = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    jpeg_bytes, timestamp = cam.get_latest_frame()
            else:
                # Camera offline/connecting: yield dynamic status slate
                jpeg_bytes, timestamp = cam.get_latest_frame()

            chunk = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
                b"X-Timestamp: " + timestamp.encode() + b"\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )
            yield chunk
            frames_sent += 1

            if max_frames is not None and frames_sent >= max_frames:
                break

            if cam.status != CameraStatus.ONLINE:
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        logger.debug(f"[{cam.camera_id}] Client disconnected from live stream")
    finally:
        cam.unsubscribe(queue)


@router.get("/api/stream/{camera_id}")
async def get_live_stream(
    camera_id: str,
    request: Request,
):
    """
    Live video stream endpoint (MJPEG).
    Compatible with:
    - Web browsers: <img src="http://.../api/stream/CAM01">
    - OpenCV: cv2.VideoCapture("http://.../api/stream/CAM01")
    - FFmpeg / VLC / Ingestion pipelines.
    No authentication required.
    """
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )

    # Optional query param for test frames or snapshot checks
    max_frames_param = request.query_params.get("max_frames")
    max_frames = int(max_frames_param) if max_frames_param and max_frames_param.isdigit() else None

    return StreamingResponse(
        mjpeg_frame_generator(cam, request, max_frames=max_frames),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        },
    )
