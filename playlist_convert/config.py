from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Spotify
    spotify_client_id: str = Field(default="", alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str = Field(default="", alias="SPOTIFY_CLIENT_SECRET")
    spotify_redirect_uri: str = Field(
        default="http://localhost:8888/callback",
        alias="SPOTIFY_REDIRECT_URI",
    )

    # Apple Music — optional override for library path; auto-detected if not set
    apple_library_path: str = Field(default="", alias="APPLE_LIBRARY_PATH")

    # Matching
    fuzzy_match_threshold: float = Field(default=85.0, alias="FUZZY_MATCH_THRESHOLD")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
