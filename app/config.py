import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 8001
    CAMERA_CONFIG_PATH: str = "config/cameras.json"
    STORAGE_PATH: str = "storage"
    REQUIRE_FFMPEG: bool = True
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def videos_dir(self) -> Path:
        p = Path(self.STORAGE_PATH) / "videos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def metadata_dir(self) -> Path:
        p = Path(self.STORAGE_PATH) / "metadata"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
