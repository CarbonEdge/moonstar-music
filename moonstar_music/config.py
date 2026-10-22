from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    moonstar_gateway_url: str
    moonstar_auth_token: str
    elevenlabs_api_key: str
    minimax_api_key: str = ""
    publish_enabled: bool = False
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    loop_interval_seconds: int = 21600
    max_tracks_per_day: int = 4
    cycle_max_usd: float = 1.00
    publish_privacy: str = "private"
    output_dir: str = "./data"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
