from typing import List
from fastapi import APIRouter, HTTPException, Request, status
from app.models import CameraDetail
from app.services.camera_manager import camera_manager

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])


def _get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("", response_model=List[CameraDetail])
async def list_cameras(request: Request) -> List[CameraDetail]:
    """Retrieve status and metadata for all managed cameras."""
    base_url = _get_base_url(request)
    return [cam.to_detail(base_url) for cam in camera_manager.get_all_cameras()]


@router.get("/{camera_id}", response_model=CameraDetail)
async def get_camera(camera_id: str, request: Request) -> CameraDetail:
    """Retrieve status and metadata for a specific camera."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )
    return cam.to_detail(_get_base_url(request))


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str):
    """Start stream worker for a camera."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )
    success = camera_manager.start_camera(camera_id)
    return {
        "camera_id": cam.camera_id,
        "status": cam.status.value,
        "message": f"Camera {cam.camera_id} worker started",
    }


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str):
    """Stop stream worker for a camera."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )
    camera_manager.stop_camera(camera_id)
    return {
        "camera_id": cam.camera_id,
        "status": cam.status.value,
        "message": f"Camera {cam.camera_id} worker stopped",
    }


@router.post("/{camera_id}/restart")
async def restart_camera(camera_id: str):
    """Force restart connection for a camera."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found.",
        )
    camera_manager.restart_camera(camera_id)
    return {
        "camera_id": cam.camera_id,
        "status": cam.status.value,
        "message": f"Camera {cam.camera_id} connection restart initiated",
    }
