"""Runtime configuration (SRS 24). Precedence: environment > .env file > built-in default.

Measurement-affecting values (thresholds, condition parameters, seeds) are always snapshotted onto the
run row, so a later configuration change cannot retroactively alter a stored result.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from gauntlet.common.paths import DATA_DIR, REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(REPO_ROOT / ".env"), ".env"), extra="ignore")

    environment: str = "development"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    database_url: str = ""
    redis_url: str = ""
    secret_encryption_key: str = ""
    cors_origins: str = ""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_secret: str = ""

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    speechmatics_api_key: str = ""
    speechmatics_rt_url: str = "wss://eu2.rt.speechmatics.com/v2"
    elevenlabs_api_key: str = ""
    elevenlabs_default_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model: str = "eleven_flash_v2_5"

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    caller_model: str = "llama-3.1-8b-instant"
    referee_model: str = "llama-3.3-70b-versatile"

    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""

    max_concurrent_calls: int = 20
    max_calls_per_worker: int = 4
    max_calls_per_run: int = 200
    max_run_duration_s: int = 1800
    default_run_spend_cap_usd: float = 2.0
    workspace_daily_spend_cap_usd: float = 5.0
    caller_llm_timeout_ms: int = 400
    turn_timeout_ms: int = 8000
    yield_timeout_ms: int = 2000
    dead_air_threshold_ms: int = 1500
    speech_margin_db: float = 12.0
    calibration_max_acceptable_ms: float = 50.0
    audio_retention_days: int = 7
    greeting_wait_ms: int = 3500

    log_level: str = "INFO"
    allow_guest: bool = Field(default=False, description="accept the shared guest session outside development")
    static_dir: str = Field(default="", description="built dashboard to serve from the API origin")
    public_fixture_host: str = Field(default="", description="public host serving /fixtures/* for bundled targets")

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            return url
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{(DATA_DIR / 'gauntlet.db').as_posix()}"

    @property
    def providers(self) -> dict[str, bool]:
        return {
            "caller_llm": bool(self.groq_api_key),
            "caller_tts": bool(self.elevenlabs_api_key),
            "referee_stt": bool(self.speechmatics_api_key),
            "livekit": bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret),
            "object_storage": bool(self.s3_bucket),
            "github_oauth": bool(self.supabase_url),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
