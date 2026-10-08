from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class CameraConfigItem(BaseModel):
    camera_id: str
    name: str
    source_url: str = ""
    enabled: bool = True


class CamerasConfigFile(BaseModel):
    cameras: List[CameraConfigItem]


class CameraDetail(BaseModel):
    camera_id: str
    name: str
    enabled: bool
    status: CameraStatus
    source_url: Optional[str] = None
    last_seen: Optional[str] = None
    last_frame_time: Optional[str] = None
    reconnect_count: int = 0
    error_message: Optional[str] = None
    stream_url: str
    fps: float = 0.0
    resolution: Optional[str] = None


class StreamInfo(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    status: CameraStatus
    fps: float = 0.0
    resolution: Optional[str] = None
    active_subscribers: int = 0


class VideoFileMetadata(BaseModel):
    file_id: str
    filename: str
    camera_id: str
    capture_start_utc: str
    size_bytes: int
    checksum_sha256: str
    duration_s: Optional[float] = None
    codec: Optional[str] = None
    fps: Optional[float] = None
    storage_path: str
    created_at: str


class GatewayInfo(BaseModel):
    name: str = "Standalone Video Gateway"
    version: str = "1.0.0"
    status: str = "ONLINE"
    uptime_seconds: float
    camera_count: int
    online_cameras: int
    ffmpeg_available: bool
    ffmpeg_version: Optional[str] = None
    active_streams: int


class HealthResponse(BaseModel):
    status: str
    gateway: str
    ffmpeg: str
    cameras: Dict[str, str]
    timestamp: str
