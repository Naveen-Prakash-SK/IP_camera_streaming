import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Tuple
import cv2
import numpy as np

from app.models import CameraStatus, CameraDetail, StreamInfo

logger = logging.getLogger(__name__)


def make_status_frame(camera_id: str, name: str, status_text: str, detail: str = "") -> bytes:
    """Generate a clean 640x360 JPEG image displaying the current camera state."""
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    # Slate dark background with subtle border
    img[:] = (24, 24, 27)  # Zinc 900
    cv2.rectangle(img, (10, 10), (630, 350), (45, 45, 50), 1)

    # Title
    cv2.putText(img, f"{camera_id}: {name}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    
    # Status indicator color
    status_upper = status_text.upper()
    if status_upper == "ONLINE":
        color = (50, 205, 50)  # Green
    elif status_upper in ("CONNECTING", "RECONNECTING"):
        color = (0, 165, 255)  # Orange
    elif status_upper == "ERROR":
        color = (71, 71, 239)  # Red
    else:
        color = (160, 160, 160)  # Gray

    cv2.circle(img, (40, 130), 10, color, -1)
    cv2.putText(img, f"STATUS: {status_upper}", (65, 138), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Detail / Message
    if detail:
        # Wrap or truncate detail
        truncated = detail[:50]
        cv2.putText(img, truncated, (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

    # Timestamp
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cv2.putText(img, ts, (30, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1)

    ret, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buffer.tobytes() if ret else b""


class CameraStream:
    def __init__(self, camera_id: str, name: str, source_url: str = "", enabled: bool = True):
        self.camera_id = camera_id
        self.name = name
        self.source_url = source_url.strip()
        self.enabled = enabled

        self.status: CameraStatus = (
            CameraStatus.NOT_CONFIGURED if not self.source_url else (CameraStatus.OFFLINE if not enabled else CameraStatus.CONNECTING)
        )
        self.last_seen: Optional[str] = None
        self.last_frame_time: Optional[str] = None
        self.reconnect_count: int = 0
        self.error_message: Optional[str] = None
        self.fps: float = 0.0
        self.resolution: Optional[str] = None

        self._latest_jpeg: Optional[bytes] = None
        self._latest_timestamp: Optional[str] = None
        self._lock = threading.Lock()
        self._subscribers: Set[asyncio.Queue] = set()

        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start background worker thread for this camera."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        if loop is not None:
            self._loop = loop
        self._stop_event.clear()
        self.enabled = True

        if not self.source_url:
            self.status = CameraStatus.NOT_CONFIGURED
            self.error_message = "No stream source URL configured in config/cameras.json"
            return

        self.status = CameraStatus.CONNECTING
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name=f"CameraWorker-{self.camera_id}",
            daemon=True,
        )
        self._worker_thread.start()
        logger.info(f"[{self.camera_id}] Started capture worker thread for source: {self.source_url}")

    def stop(self):
        """Stop background worker thread."""
        self._stop_event.set()
        self.enabled = False
        self.status = CameraStatus.STOPPED
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        logger.info(f"[{self.camera_id}] Stopped capture worker")

    def restart(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Force restart worker connection."""
        self.stop()
        time.sleep(0.2)
        self.start(loop)

    def update_config(self, source_url: str, name: Optional[str] = None, enabled: bool = True):
        """Update stream configuration."""
        url_changed = self.source_url != source_url.strip()
        self.source_url = source_url.strip()
        if name:
            self.name = name
        self.enabled = enabled

        if not self.source_url:
            self.stop()
            self.status = CameraStatus.NOT_CONFIGURED
            self.error_message = "No stream source URL configured in config/cameras.json"
        elif url_changed and self.enabled:
            self.restart(self._loop)

    def _worker_loop(self):
        """Isolated worker thread for continuous frame capture and reconnection."""
        backoff_delay = 1.0
        max_backoff = 10.0

        while not self._stop_event.is_set():
            if not self.enabled or not self.source_url:
                self.status = CameraStatus.STOPPED if not self.enabled else CameraStatus.NOT_CONFIGURED
                break

            logger.info(f"[{self.camera_id}] Connecting to video source: {self.source_url}")
            self.status = CameraStatus.CONNECTING if self.reconnect_count == 0 else CameraStatus.RECONNECTING

            cap = None
            try:
                # Open with CAP_FFMPEG backend for network streams
                cap = cv2.VideoCapture(self.source_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    raise RuntimeError(f"Unable to open stream at {self.source_url}")

                logger.info(f"[{self.camera_id}] Stream connected successfully")
                self.status = CameraStatus.ONLINE
                self.error_message = None
                self.reconnect_count = 0
                backoff_delay = 1.0

                frame_count = 0
                start_fps_time = time.time()

                while not self._stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret or frame is None or frame.size == 0:
                        raise RuntimeError("Failed to read frame from stream (connection closed or empty frame)")

                    now_utc = datetime.now(timezone.utc).isoformat()
                    h, w = frame.shape[:2]
                    self.resolution = f"{w}x{h}"

                    # Encode to JPEG
                    encode_success, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not encode_success:
                        continue

                    jpeg_bytes = jpeg_buf.tobytes()

                    with self._lock:
                        self._latest_jpeg = jpeg_bytes
                        self._latest_timestamp = now_utc
                        self.last_seen = now_utc
                        self.last_frame_time = now_utc

                    frame_count += 1
                    elapsed = time.time() - start_fps_time
                    if elapsed >= 2.0:
                        self.fps = round(frame_count / elapsed, 1)
                        frame_count = 0
                        start_fps_time = time.time()

                    # Push to async subscribers safely
                    self._dispatch_to_subscribers(jpeg_bytes, now_utc)

            except Exception as e:
                err = str(e)
                logger.warning(f"[{self.camera_id}] Stream disconnected or error: {err}")
                self.status = CameraStatus.RECONNECTING
                self.error_message = err
                self.reconnect_count += 1

                # Clean up video capture
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None

                # Wait with backoff before reconnecting
                sleep_steps = int(backoff_delay * 10)
                for _ in range(sleep_steps):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)

                backoff_delay = min(backoff_delay * 1.5, max_backoff)

            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

        if self._stop_event.is_set():
            self.status = CameraStatus.STOPPED

    def _dispatch_to_subscribers(self, jpeg_bytes: bytes, timestamp: str):
        """Deliver frame to all waiting async queues without blocking the capture thread."""
        with self._lock:
            subs = list(self._subscribers)

        for q in subs:
            loop = getattr(q, "_bound_loop", None)
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(self._put_frame_safe, q, jpeg_bytes, timestamp)

    @staticmethod
    def _put_frame_safe(q: asyncio.Queue, jpeg_bytes: bytes, timestamp: str):
        if q.full():
            try:
                q.get_nowait()
            except Exception:
                pass
        try:
            q.put_nowait((jpeg_bytes, timestamp))
        except Exception:
            pass

    def get_latest_frame(self) -> Tuple[bytes, str]:
        """Return the latest frame or a dynamically generated status placeholder."""
        with self._lock:
            if self.status == CameraStatus.ONLINE and self._latest_jpeg is not None:
                return self._latest_jpeg, self._latest_timestamp or datetime.now(timezone.utc).isoformat()

        # Generate status frame
        status_frame = make_status_frame(
            self.camera_id,
            self.name,
            self.status.value,
            self.error_message or ("Awaiting camera connection" if self.status == CameraStatus.CONNECTING else ""),
        )
        return status_frame, datetime.now(timezone.utc).isoformat()

    async def subscribe(self) -> asyncio.Queue:
        """Register a new stream subscriber."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        q._bound_loop = loop
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Unregister a stream subscriber."""
        with self._lock:
            self._subscribers.discard(q)

    @property
    def active_subscribers_count(self) -> int:
        return len(self._subscribers)

    def to_detail(self, base_url: str = "") -> CameraDetail:
        stream_endpoint = f"{base_url}/api/stream/{self.camera_id}" if base_url else f"/api/stream/{self.camera_id}"
        # Mask credentials in source_url if present
        safe_source_url = self.source_url
        if "@" in safe_source_url:
            parts = safe_source_url.split("@")
            prefix = parts[0].split("//")[0]
            safe_source_url = f"{prefix}//***:***@{parts[1]}"

        return CameraDetail(
            camera_id=self.camera_id,
            name=self.name,
            enabled=self.enabled,
            status=self.status,
            source_url=safe_source_url,
            last_seen=self.last_seen,
            last_frame_time=self.last_frame_time,
            reconnect_count=self.reconnect_count,
            error_message=self.error_message,
            stream_url=stream_endpoint,
            fps=self.fps,
            resolution=self.resolution,
        )

    def to_stream_info(self, base_url: str = "") -> StreamInfo:
        stream_endpoint = f"{base_url}/api/stream/{self.camera_id}" if base_url else f"/api/stream/{self.camera_id}"
        return StreamInfo(
            camera_id=self.camera_id,
            name=self.name,
            stream_url=stream_endpoint,
            status=self.status,
            fps=self.fps,
            resolution=self.resolution,
            active_subscribers=self.active_subscribers_count,
        )
