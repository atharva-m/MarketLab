from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARKETLAB_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://marketlab:marketlab@127.0.0.1:5432/marketlab"
    )
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    database_password: SecretStr | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    copilot_model: str = "qwen3.5:9b-q4_K_M"
    copilot_model_digest: str | None = (
        "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90"
    )
    storage_path: Path = Path("./data")
    dependency_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    database_connect_timeout_seconds: int = Field(default=5, ge=2, le=30)
    metrics_port: int = Field(default=0, ge=0, le=65535)
    metrics_bind: str = "127.0.0.1"

    @field_validator("metrics_bind")
    @classmethod
    def require_metrics_bind(cls, value: str) -> str:
        if value not in {"127.0.0.1", "0.0.0.0"}:
            raise ValueError("metrics bind must be loopback or explicit container bind")
        return value

    @property
    def database_connect_args(self) -> dict[str, int]:
        return {"connect_timeout": self.database_connect_timeout_seconds}

    @property
    def sqlalchemy_url(self) -> URL:
        url = make_url(self.database_url.get_secret_value())
        if self.database_password is not None:
            url = url.set(password=self.database_password.get_secret_value())
        return url

    @field_validator("database_url")
    @classmethod
    def require_psycopg(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("database URL must use postgresql+psycopg://")
        return value
