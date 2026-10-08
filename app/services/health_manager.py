import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from app import __version__
from app.config import settings


class HealthManager:
    def __init__(self):
        self.start_time = time.time()
        self._ffmpeg_cached_info: Optional[Tuple[bool, Optional[str]]] = None

    def check_ffmpeg(self) -> Tuple[bool, Optional[str]]:
        """Check if FFmpeg is installed and available on system PATH."""
        if self._ffmpeg_cached_info is not None:
            return self._ffmpeg_cached_info

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            self._ffmpeg_cached_info = (False, None)
            return (False, None)

        try:
            res = subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            if res.returncode == 0:
                first_line = res.stdout.splitlines()[0] if res.stdout else "Available"
                self._ffmpeg_cached_info = (True, first_line)
                return (True, first_line)
        except Exception:
            pass

        self._ffmpeg_cached_info = (False, None)
        return (False, None)

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.start_time, 2)

    @staticmethod
    def utc_iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()


health_manager = HealthManager()
