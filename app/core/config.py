from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    database_url: str = "sqlite+pysqlite:///:memory:"
    log_level: str = "INFO"
    log_json: bool = False
    timezone: str = "Europe/Madrid"
    request_timeout_seconds: int = 20
    request_retries: int = 3
    request_backoff_seconds: float = 0.75
    user_agent: str = "FutbolBalearBot/0.1"
    respect_robots_txt: bool = True
    debug_response_dir: str = ".debug_responses"
    dry_run: bool = False
    x_client_id: str | None = None
    x_client_secret: str | None = None
    x_redirect_uri: str | None = None
    x_scopes: str = "tweet.read tweet.write users.read offline.access"
    x_auth_state_ttl_minutes: int = 15
    x_token_refresh_buffer_seconds: int = 60
    x_authorize_url: str = "https://x.com/i/oauth2/authorize"
    x_token_url: str = "https://api.x.com/2/oauth2/token"
    x_bearer_token: str | None = None
    x_api_base_url: str = "https://api.x.com"
    typefully_api_key: str | None = None
    typefully_api_url: str | None = None
    typefully_social_set_id: str | None = None
    editorial_rewrite_provider: str = "openai"
    editorial_rewrite_api_key: str | None = None
    editorial_rewrite_api_url: str = "https://api.openai.com/v1/responses"
    editorial_rewrite_model: str | None = None
    editorial_rewrite_max_chars: int = 280
    enable_team_mentions: bool = True
    max_mentions_per_post: int = 3
    app_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def debug_path(self) -> Path:
        return self.app_root / self.debug_response_dir

    @property
    def x_scope_list(self) -> list[str]:
        return [scope for scope in self.x_scopes.split() if scope.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
