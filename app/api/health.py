from fastapi import APIRouter
from app.models import HealthResponse, GatewayInfo
from app.services.health_manager import health_manager
from app.services.camera_manager import camera_manager

router = APIRouter(tags=["Health & Info"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Public health probe endpoint."""
    ffmpeg_ok, ffmpeg_ver = health_manager.check_ffmpeg()
    cameras = camera_manager.get_all_cameras()
    cam_status_dict = {cam.camera_id: cam.status.value for cam in cameras}

    return HealthResponse(
        status="ONLINE",
        gateway="ONLINE",
        ffmpeg="ONLINE" if ffmpeg_ok else "UNAVAILABLE",
        cameras=cam_status_dict,
        timestamp=health_manager.utc_iso_now(),
    )


@router.get("/api/info", response_model=GatewayInfo)
def get_info() -> GatewayInfo:
    """Detailed gateway metadata."""
    ffmpeg_ok, ffmpeg_ver = health_manager.check_ffmpeg()
    cameras = camera_manager.get_all_cameras()
    online_count = sum(1 for c in cameras if c.status.value == "ONLINE")
    active_streams = sum(1 for c in cameras if c.active_subscribers_count > 0)

    return GatewayInfo(
        name="Standalone Video Gateway",
        version="1.0.0",
        status="ONLINE",
        uptime_seconds=health_manager.uptime_seconds,
        camera_count=len(cameras),
        online_cameras=online_count,
        ffmpeg_available=ffmpeg_ok,
        ffmpeg_version=ffmpeg_ver,
        active_streams=active_streams,
    )
