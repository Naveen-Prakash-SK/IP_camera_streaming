import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.api.health import router as health_router
from app.api.cameras import router as cameras_router
from app.api.streams import router as streams_router
from app.api.files import router as files_router
from app.services.health_manager import health_manager
from app.services.camera_manager import camera_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("video-gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start camera workers and clean up on shutdown."""
    logger.info("=" * 60)
    logger.info(f"Starting Video Gateway v{__version__}")
    logger.info(f"Binding to {settings.GATEWAY_HOST}:{settings.GATEWAY_PORT}")
    logger.info(f"Storage directory: {settings.STORAGE_PATH}")
    logger.info("=" * 60)

    # Check FFmpeg dependency
    ffmpeg_ok, ffmpeg_ver = health_manager.check_ffmpeg()
    if ffmpeg_ok:
        logger.info(f"FFmpeg system check: OK ({ffmpeg_ver})")
    else:
        logger.warning(
            "FFmpeg system check: NOT FOUND ON PATH! "
            "Please install FFmpeg and add it to system PATH for full stream/file transcoding."
        )

    # Initialize cameras
    loop = asyncio.get_running_loop()
    camera_manager.initialize(loop)
    camera_manager.start_all()

    yield

    logger.info("Shutting down Video Gateway. Stopping all camera workers...")
    camera_manager.stop_all()
    logger.info("All camera workers stopped.")


app = FastAPI(
    title="Standalone Video Gateway",
    description="Multi-Camera Streaming and Storage Gateway for IP Webcam phone cameras and Main Application ingestion.",
    version=__version__,
    lifespan=lifespan,
)

# Enable CORS for Main Application frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(cameras_router)
app.include_router(streams_router)
app.include_router(files_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.GATEWAY_HOST,
        port=settings.GATEWAY_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )
