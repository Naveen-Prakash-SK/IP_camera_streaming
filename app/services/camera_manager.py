import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
import asyncio

from app.config import settings
from app.models import CameraConfigItem, CamerasConfigFile, CameraStatus
from app.services.stream_manager import CameraStream

logger = logging.getLogger(__name__)

DEFAULT_CAMERAS = [
    {"camera_id": "CAM01", "name": "Camera 1", "source_url": "", "enabled": True},
    {"camera_id": "CAM02", "name": "Camera 2", "source_url": "", "enabled": True},
    {"camera_id": "CAM03", "name": "Camera 3", "source_url": "", "enabled": True},
    {"camera_id": "CAM04", "name": "Camera 4", "source_url": "", "enabled": True},
]


class CameraManager:
    def __init__(self):
        self._cameras: Dict[str, CameraStream] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._config_path = Path(settings.CAMERA_CONFIG_PATH)
        self.initialize()

    def _ensure_initialized(self):
        if not self._cameras:
            self.initialize(self._loop)

    def initialize(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Load configuration and initialize camera streams."""
        if loop is not None:
            self._loop = loop
        elif self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except Exception:
                self._loop = None

        config_items = self._read_config_file()

        # Ensure all 4 default cameras are represented
        loaded_ids = {item.camera_id for item in config_items}
        for default in DEFAULT_CAMERAS:
            if default["camera_id"] not in loaded_ids:
                config_items.append(CameraConfigItem(**default))

        for item in config_items:
            if item.camera_id in self._cameras:
                self._cameras[item.camera_id].update_config(
                    source_url=item.source_url,
                    name=item.name,
                    enabled=item.enabled,
                )
            else:
                stream = CameraStream(
                    camera_id=item.camera_id,
                    name=item.name,
                    source_url=item.source_url,
                    enabled=item.enabled,
                )
                self._cameras[item.camera_id] = stream

        logger.info(f"Initialized CameraManager with {len(self._cameras)} cameras: {list(self._cameras.keys())}")

    def start_all(self):
        """Start workers for all configured cameras."""
        for cam in self._cameras.values():
            if cam.enabled and cam.source_url:
                cam.start(self._loop)
            elif not cam.source_url:
                cam.status = CameraStatus.NOT_CONFIGURED

    def stop_all(self):
        """Stop all camera capture workers."""
        for cam in self._cameras.values():
            cam.stop()

    def get_camera(self, camera_id: str) -> Optional[CameraStream]:
        self._ensure_initialized()
        return self._cameras.get(camera_id.upper())

    def get_all_cameras(self) -> List[CameraStream]:
        self._ensure_initialized()
        # Return sorted by camera_id
        return sorted(self._cameras.values(), key=lambda c: c.camera_id)

    def start_camera(self, camera_id: str) -> bool:
        cam = self.get_camera(camera_id)
        if not cam:
            return False
        cam.start(self._loop)
        return True

    def stop_camera(self, camera_id: str) -> bool:
        cam = self.get_camera(camera_id)
        if not cam:
            return False
        cam.stop()
        return True

    def restart_camera(self, camera_id: str) -> bool:
        cam = self.get_camera(camera_id)
        if not cam:
            return False
        cam.restart(self._loop)
        return True

    def reload_config(self):
        """Reload configuration from file without restarting running streams unnecessarily."""
        items = self._read_config_file()
        for item in items:
            cam = self._cameras.get(item.camera_id)
            if cam:
                cam.update_config(source_url=item.source_url, name=item.name, enabled=item.enabled)
            else:
                new_cam = CameraStream(
                    camera_id=item.camera_id,
                    name=item.name,
                    source_url=item.source_url,
                    enabled=item.enabled,
                )
                self._cameras[item.camera_id] = new_cam
                if new_cam.enabled and new_cam.source_url:
                    new_cam.start(self._loop)

    def _read_config_file(self) -> List[CameraConfigItem]:
        """Read cameras configuration, falling back to example configuration if missing."""
        path = self._config_path
        if not path.is_file():
            # Try example config
            example_path = path.parent / "cameras.example.json"
            if example_path.is_file():
                logger.info(f"Config {path} not found; reading template {example_path}")
                path = example_path
            else:
                logger.info("No config file found; using default CAM01-CAM04 template")
                return [CameraConfigItem(**c) for c in DEFAULT_CAMERAS]

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            parsed = CamerasConfigFile(**data)
            return parsed.cameras
        except Exception as e:
            logger.error(f"Error reading camera config from {path}: {e}")
            return [CameraConfigItem(**c) for c in DEFAULT_CAMERAS]


camera_manager = CameraManager()
