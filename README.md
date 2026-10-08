# Standalone Video Gateway

A high-performance, lightweight, multi-camera streaming and storage gateway built with **Python 3**, **FastAPI**, **FFmpeg**, and **OpenCV**.

This project runs directly on the **Streaming Laptop** (Windows host OS) **without Docker**. It ingests live video feeds from 4 Android phones running IP Webcam over local Wi-Fi, buffers and manages connection health independently, and directly exposes live MJPEG video streams and recorded video files to the **Main Application** laptop without authentication requirements.

---

## Architecture Overview

```
Android Phone 1 (CAM01) ──┐
Android Phone 2 (CAM02) ──┼──> [Local Wi-Fi Network]
Android Phone 3 (CAM03) ──┤
Android Phone 4 (CAM04) ──┘
         │
         ▼
[Streaming Laptop (Windows OS - No Docker)]
┌──────────────────────────────────────────────────────────────┐
│                    VIDEO GATEWAY (:8001)                     │
│                                                              │
│  ┌────────────────────┐      ┌─────────────────────────────┐ │
│  │   Config Loader    │      │         FastAPI App         │ │
│  │ (config/cameras)   │      │ - GET  /health              │ │
│  └─────────┬──────────┘      │ - GET  /api/cameras         │ │
│            │                 │ - GET  /api/streams         │ │
│            ▼                 │ - GET  /api/stream/{id}     │ │
│  ┌────────────────────┐      │ - POST /api/files/upload    │ │
│  │ Camera Manager     │◄────►│ - GET  /api/files/{id}/dl   │ │
│  │ - Worker CAM01     │      └──────────────┬──────────────┘ │
│  │ - Worker CAM02     │                     │                │
│  │ - Worker CAM03     │                     ▼                │
│  │ - Worker CAM04     │      ┌─────────────────────────────┐ │
│  └─────────┬──────────┘      │ Storage (storage/videos)    │ │
│            │                 └─────────────────────────────┘ │
│            ▼                                                 │
│  ┌────────────────────┐                                      │
│  │ Stream Hub & Buffer│                                      │
│  │ (Decoupled Readers)│                                      │
│  └────────────────────┘                                      │
└─────────────────────────────────────────────┬────────────────┘
                                              │
                      LAN / VS Code Port Fwd  │
                                              ▼
[Main Application Laptop (Dockerized)]
┌──────────────────────────────────────────────────────────────┐
│ - Next.js UI (Directly streams /api/stream/CAM01..04)        │
│ - Celery Ingestion Workers (Pulls live frames or downloads)  │
│ - Backend AI Pipeline (YOLO / SigLIP / Qdrant)               │
└──────────────────────────────────────────────────────────────┘
```

### Key Highlights
* **Zero AI Processing on Gateway:** No YOLO, PyTorch, Ollama, Qdrant, or Postgres on the streaming laptop.
* **Direct Unauthenticated Access:** Endpoints are publicly open on the local network; no API keys or auth headers required.
* **Independent Camera Isolation:** If CAM02 loses Wi-Fi connection, CAM01, CAM03, and CAM04 continue streaming without interruption while CAM02 automatically reconnects with exponential backoff.
* **Single Connection Decoupling:** Connects once to each phone to save phone CPU and Wi-Fi bandwidth, multiplexing frames in memory to multiple consumers.
* **Standard MJPEG Live Streams:** Live video is streamed via HTTP multipart `multipart/x-mixed-replace; boundary=frame`. Continuous video is **never** encoded into JSON or base64.
* **UTC Timestamps:** All frames and metadata strictly adhere to ISO-8601 UTC timestamps.
* **RAM-Safe Chunked Storage:** Large video uploads and downloads stream in 64 KB chunks directly to disk with SHA-256 checksum verification.

---

## Prerequisites (Windows Streaming Laptop)

1. **Python 3.10+** (Python 3.12 or 3.14 recommended).
2. **FFmpeg & FFprobe on PATH**:
   * **Option A (winget - Recommended):**
     ```powershell
     winget install Gyan.FFmpeg
     ```
   * **Option B (Manual Download):**
     1. Download `ffmpeg-release-full.7z` from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) or [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html).
     2. Extract to `C:\ffmpeg`.
     3. Add `C:\ffmpeg\bin` to your Windows System Environment Variables `PATH`.
     4. Open a new terminal and verify:
        ```powershell
        ffmpeg -version
        ffprobe -version
        ```

---

## Installation & Setup

### 1. Open Terminal in `video-gateway`
```powershell
cd "d:\1.KPR\2nd year\git projects\camera streaming\video-gateway"
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Create Environment Configuration (`.env`)
```powershell
Copy-Item .env.example .env
```
Open `.env` and verify port and paths:
```env
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8001
CAMERA_CONFIG_PATH=config/cameras.json
STORAGE_PATH=storage
REQUIRE_FFMPEG=true
LOG_LEVEL=INFO
```

### 5. Create Camera Configuration (`config/cameras.json`)
```powershell
Copy-Item config\cameras.example.json config\cameras.json
```

---

## Configuring Android Phone IP Webcam URLs

The user will configure the 4 phone stream URLs in `config/cameras.json`.

1. Install **IP Webcam** (by Pavel Khlebovich) from Google Play Store on all 4 Android phones.
2. Connect all phones and the Streaming Laptop to the same Wi-Fi network.
3. In IP Webcam on each phone, scroll to the bottom and tap **Start server**.
4. The phone screen will display an address (e.g. `http://192.168.1.101:8080`).
5. Open `config/cameras.json` on the Streaming Laptop and enter the complete stream URLs:

```json
{
  "cameras": [
    {
      "camera_id": "CAM01",
      "name": "Entrance Camera",
      "source_url": "http://192.168.1.101:8080/video",
      "enabled": true
    },
    {
      "camera_id": "CAM02",
      "name": "Hallway Camera",
      "source_url": "http://192.168.1.102:8080/video",
      "enabled": true
    },
    {
      "camera_id": "CAM03",
      "name": "Lobby Camera",
      "source_url": "http://192.168.1.103:8080/video",
      "enabled": true
    },
    {
      "camera_id": "CAM04",
      "name": "Exit Camera",
      "source_url": "http://192.168.1.104:8080/video",
      "enabled": true
    }
  ]
}
```

> **Note:**
> If any camera has `source_url: ""` or is not yet configured, the gateway starts normally and marks the camera as `NOT_CONFIGURED` or `OFFLINE` without crashing.

---

## Starting the Gateway

Run from the `video-gateway` directory:
```powershell
python -m app.main
```

The gateway binds to `0.0.0.0:8001`.

Verify in your browser:
* Public health probe: [http://localhost:8001/health](http://localhost:8001/health)
* Interactive Swagger Docs: [http://localhost:8001/docs](http://localhost:8001/docs)
* Direct CAM01 Live Stream: [http://localhost:8001/api/stream/CAM01](http://localhost:8001/api/stream/CAM01)

---

## VS Code Port Forwarding (Remote / Multi-Laptop Access)

If the Streaming Laptop and Main Application Laptop are not on the exact same subnet or you are using VS Code Remoting:

1. In VS Code on the Streaming Laptop, click the **Ports** tab in the bottom panel (or press `Ctrl+Shift+P` -> `Ports: Focus on Ports View`).
2. Click **Add Port** (or Forward a Port) and type `8001`.
3. Right-click the forwarded port `8001` -> **Port Visibility** -> choose **Public**.
4. Copy the **Forwarded Address** (e.g. `https://xxxx-8001.app.github.dev`).
5. Use this Forwarded URL as `GATEWAY_URL` on the Main Application laptop.

---

## Connecting the Main Application to the Gateway

On the **Main Application Laptop**, set the gateway parameters in the backend's `.env`:

```env
GATEWAY_URL=http://<streaming-laptop-ip>:8001
```
*(Or use the VS Code forwarded address if using port forwarding)*

### 1. Consuming Live Video in Next.js Frontend
In the Main Application's Next.js UI (`frontend/src/app/...`), embed camera feeds directly without authentication:
```tsx
<img
  src={`${process.env.NEXT_PUBLIC_GATEWAY_URL}/api/stream/CAM01`}
  alt="CAM01 Live Feed"
  className="w-full h-auto rounded-lg shadow"
/>
```

### 2. Ingesting Live Video in Python / Celery / OpenCV
```python
import cv2

stream_url = f"{GATEWAY_URL}/api/stream/CAM01"
cap = cv2.VideoCapture(stream_url)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    # Run YOLO / AI inference here on Main Application laptop
```

### 3. Fetching Camera Metadata
```bash
curl http://localhost:8001/api/cameras
```

---

## REST API Reference

| Method | Endpoint | Purpose | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public liveness probe & system overview | No |
| `GET` | `/api/info` | Gateway uptime, active streams, FFmpeg info | No |
| `GET` | `/api/cameras` | List metadata and state of all 4 cameras | No |
| `GET` | `/api/cameras/{camera_id}` | Detailed status for a specific camera | No |
| `POST` | `/api/cameras/{camera_id}/start` | Start ingestion for a camera | No |
| `POST` | `/api/cameras/{camera_id}/stop` | Stop ingestion for a camera | No |
| `POST` | `/api/cameras/{camera_id}/restart` | Reconnect ingestion for a camera | No |
| `GET` | `/api/streams` | List live stream metadata for all cameras | No |
| `GET` | `/api/streams/{camera_id}` | Live stream metadata for a single camera | No |
| `GET` | `/api/stream/{camera_id}` | **Live MJPEG video stream** (`multipart/x-mixed-replace`) | No |
| `GET` | `/api/files` | List recorded video files (optional `?camera_id=`) | No |
| `GET` | `/api/files/{file_id}` | Metadata for a specific recorded video file | No |
| `GET` | `/api/files/{file_id}/download` | Stream download recorded video with Range support | No |
| `POST` | `/api/files/upload` | Upload video file with metadata | No |

---

## Testing

### Automated Unit and API Tests
Run pytest with the virtual environment activated:
```powershell
pytest -v
```

### Manual Testing Procedure
1. Start the gateway (`python -m app.main`).
2. Open [http://localhost:8001/health](http://localhost:8001/health) -> verify `status: ONLINE` and cameras report status.
3. Open `config/cameras.json`, enter the `source_url` for `CAM01` only, and restart or trigger `POST /api/cameras/CAM01/start`.
4. Verify `CAM01` transitions to `ONLINE` on `GET /api/cameras/CAM01`.
5. Open `http://localhost:8001/api/stream/CAM01` in a browser -> verify live video appears without prompt/key.
6. Configure `CAM02` in `config/cameras.json` -> verify `CAM02` transitions to `ONLINE`.
7. Configure `CAM03` in `config/cameras.json` -> verify `CAM03` transitions to `ONLINE`.
8. Configure `CAM04` in `config/cameras.json` -> verify `CAM04` transitions to `ONLINE`.
9. Disconnect Wi-Fi on the phone running `CAM02`.
10. Confirm only `CAM02` transitions to `RECONNECTING`. Confirm `CAM01`, `CAM03`, and `CAM04` continue streaming without interruption.
11. Reconnect Wi-Fi on the `CAM02` phone.
12. Confirm `CAM02` automatically recovers and transitions back to `ONLINE`.
13. Upload a sample video file via `POST /api/files/upload` and verify download via `GET /api/files/{file_id}/download`.
