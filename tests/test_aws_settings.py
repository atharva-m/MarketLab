from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.session import Session

from marketlab.config import Settings
from marketlab.datasets.v2.common import V2Error
from marketlab.storage.backend import ObjectConfig, S3Backend

AWS_NAMES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "S3_BUCKET_NAME",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in tuple(os.environ):
        if name.upper().startswith("MARKETLAB_") and (
            name.upper().startswith("MARKETLAB_STORAGE_")
            or name.upper() in {"MARKETLAB_DATABASE_PASSWORD", "MARKETLAB_WORKER_ROOT_ID"}
        ):
            monkeypatch.delenv(name)
    for name in AWS_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_aws_dotenv_binds_existing_s3_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An operator-selected file with synthetic values. The guarded interpreter
    # continues to forbid opening the repository .env and .env.example.
    fixture = tmp_path / "aws-settings.fixture"
    fixture.write_text(
        "MARKETLAB_STORAGE_BACKEND=s3\n"
        "S3_BUCKET_NAME=fixture-bucket\n"
        "AWS_DEFAULT_REGION=cn-north-1\n"
        "AWS_ACCESS_KEY_ID=fixture-key\n"
        "AWS_SECRET_ACCESS_KEY=fixture-secret\n"
        "AWS_SESSION_TOKEN=fixture-token\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=fixture)  # type: ignore[call-arg]
    config = ObjectConfig.from_settings(settings)
    assert config == ObjectConfig(
        "s3", "https://s3.cn-north-1.amazonaws.com.cn", "cn-north-1", "fixture-bucket", "marketlab"
    )
    assert all(
        word not in repr(settings) for word in ("fixture-key", "fixture-secret", "fixture-token")
    )

    registered = []
    closed = []

    def create_client(_session, service, **options):
        assert service == "s3"
        assert options["endpoint_url"] == config.endpoint
        assert options["region_name"] == config.region
        assert options["aws_access_key_id"] == "fixture-key"
        assert options["aws_secret_access_key"] == "fixture-secret"
        assert options["aws_session_token"] == "fixture-token"
        return SimpleNamespace(
            meta=SimpleNamespace(
                events=SimpleNamespace(register_first=lambda name, _: registered.append(name))
            ),
            close=lambda: closed.append(True),
        )

    monkeypatch.setattr(Session, "create_client", create_client)
    backend = S3Backend.configured(config, settings)
    backend.close()
    assert (registered, closed) == (["needs-retry.s3"], [True])


def test_settings_source_priority_across_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = tmp_path / "precedence-settings.fixture"
    fixture.write_text(
        "MARKETLAB_STORAGE_S3_ACCESS_KEY=file-app\n"
        "AWS_ACCESS_KEY_ID=file-alias\n"
        "MARKETLAB_STORAGE_S3_BUCKET=file-bucket\n"
        "AWS_REGION=eu-west-1\n"
        "AWS_DEFAULT_REGION=us-east-1\n",
        encoding="utf-8",
    )

    def assert_settings(expected_key: str, **kwargs: object) -> Settings:
        settings = Settings(_env_file=fixture, **kwargs)  # type: ignore[call-arg,arg-type]
        assert settings.storage_s3_access_key is not None
        assert settings.storage_s3_access_key.get_secret_value() == expected_key
        return settings

    assert assert_settings("file-app").storage_s3_region == "eu-west-1"
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "environment-alias")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-1")
    monkeypatch.setenv("S3_BUCKET_NAME", "environment-bucket")
    settings = assert_settings("environment-alias")
    assert settings.storage_s3_region == "us-west-1"
    assert settings.storage_s3_bucket == "environment-bucket"
    monkeypatch.setenv("MARKETLAB_STORAGE_S3_ACCESS_KEY", "environment-app")
    assert_settings("environment-app")
    assert_settings("constructor", storage_s3_access_key="constructor")


def test_blank_optional_values_do_not_load_stale_alias_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKETLAB_WORKER_ROOT_ID", "")
    monkeypatch.setenv("MARKETLAB_STORAGE_S3_ENDPOINT", "")
    monkeypatch.setenv("MARKETLAB_STORAGE_S3_ACCESS_KEY", " ")
    monkeypatch.setenv("MARKETLAB_STORAGE_S3_SESSION_TOKEN", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "stale-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "stale-token")
    monkeypatch.setenv("S3_BUCKET_NAME", "fixture-bucket")
    settings = Settings(storage_backend="s3")
    assert settings.worker_root_id is None
    assert settings.storage_s3_endpoint is None
    assert settings.storage_s3_access_key is None
    assert settings.storage_s3_session_token is None
    config = ObjectConfig.from_settings(settings)
    assert config is not None

    def unexpected_client(*args, **kwargs):
        pytest.fail("An incomplete credential pair reached the SDK")

    monkeypatch.setattr(Session, "create_client", unexpected_client)
    with pytest.raises(V2Error, match="credentials required"):
        S3Backend.configured(config, settings)


def test_ambient_aws_aliases_leave_local_storage_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "fixture-bucket")
    assert Settings().storage_backend == "local"
    assert ObjectConfig.from_settings(Settings()) is None


@pytest.mark.parametrize(
    ("region", "endpoint"),
    [
        ("us-east-1", "https://s3.us-east-1.amazonaws.com"),
        ("us-gov-west-1", "https://s3.us-gov-west-1.amazonaws.com"),
    ],
)
def test_known_region_endpoint_without_network(region: str, endpoint: str) -> None:
    config = ObjectConfig.from_settings(
        Settings(storage_backend="s3", storage_s3_bucket="fixture-bucket", storage_s3_region=region)
    )
    assert config is not None and config.endpoint == endpoint


def test_explicit_endpoint_keeps_existing_namespace_and_custom_region() -> None:
    settings = Settings(
        storage_backend="local",
        storage_s3_endpoint="https://OBJECT.example.invalid/",
        storage_s3_bucket="fixture-bucket",
        storage_s3_region="custom-signing-region",
        storage_s3_prefix="stable/path",
    )
    assert ObjectConfig.from_settings(settings) == ObjectConfig(
        "s3",
        "https://object.example.invalid",
        "custom-signing-region",
        "fixture-bucket",
        "stable/path",
    )
    with pytest.raises(V2Error, match="Specify an object storage endpoint"):
        ObjectConfig.from_settings(
            Settings(
                storage_backend="s3",
                storage_s3_bucket="fixture-bucket",
                storage_s3_region="us-fake-2",
            )
        )
