from pathlib import Path
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKETLAB_", env_file=".env", extra="ignore", populate_by_name=True
    )

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
    worker_root_id: UUID | None = None
    storage_backend: str = "local"
    storage_s3_alias: str = "s3"
    storage_s3_endpoint: str | None = None
    storage_s3_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices(
            "MARKETLAB_STORAGE_S3_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"
        ),
    )
    storage_s3_bucket: str | None = Field(
        default=None, validation_alias=AliasChoices("MARKETLAB_STORAGE_S3_BUCKET", "S3_BUCKET_NAME")
    )
    storage_s3_prefix: str = "marketlab"
    storage_s3_access_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("MARKETLAB_STORAGE_S3_ACCESS_KEY", "AWS_ACCESS_KEY_ID"),
    )
    storage_s3_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("MARKETLAB_STORAGE_S3_SECRET_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    storage_s3_session_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("MARKETLAB_STORAGE_S3_SESSION_TOKEN", "AWS_SESSION_TOKEN"),
    )
    dependency_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    database_connect_timeout_seconds: int = Field(default=5, ge=2, le=30)
    metrics_port: int = Field(default=0, ge=0, le=65535)
    metrics_bind: str = "127.0.0.1"

    @field_validator(
        "database_password",
        "worker_root_id",
        "storage_s3_endpoint",
        "storage_s3_bucket",
        "storage_s3_access_key",
        "storage_s3_secret_key",
        "storage_s3_session_token",
        mode="before",
    )
    @classmethod
    def empty_optional_setting(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

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
