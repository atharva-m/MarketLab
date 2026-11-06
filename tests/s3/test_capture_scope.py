"""Offline regressions for ordinary CI versus retained owned-S3 evidence."""

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_v2_ingestion_integration as fixtures

pytestmark = pytest.mark.s3
SPEC = importlib.util.spec_from_file_location(
    "phase6_capture_scope_hooks", Path(__file__).with_name("conftest.py")
)
hooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hooks)
OWNED = "MARKETLAB_PHASE6_OWNED_S3"


def _set_optin(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(OWNED, raising=False)
    else:
        monkeypatch.setenv(OWNED, value)


def _request(s3=True):
    return SimpleNamespace(
        node=SimpleNamespace(get_closest_marker=lambda name: object() if s3 else None)
    )


def _schema_fixture(monkeypatch, request):
    statements = []
    engines = []

    class Connection:
        def execute(self, statement):
            statements.append(str(statement))

        def exec_driver_sql(self, statement):
            pass

    class Engine:
        disposed = False

        def begin(self):
            return nullcontext(Connection())

        def dispose(self):
            self.disposed = True

    def create_engine(*args, **kwargs):
        engine = Engine()
        engines.append(engine)
        return engine

    monkeypatch.setenv("MARKETLAB_DATABASE_URL", "synthetic-no-endpoint")
    monkeypatch.setattr(
        fixtures, "Settings", lambda: SimpleNamespace(sqlalchemy_url="synthetic-no-endpoint")
    )
    monkeypatch.setattr(fixtures.sa, "create_engine", create_engine)
    generator = fixtures.v2_engine.__wrapped__(request)
    engine = next(generator)
    return engine, generator, statements, engines


@pytest.mark.parametrize("optin", [None, "not-an-owned-campaign"])
def test_ordinary_s3_marked_fixture_does_not_require_live_capture(monkeypatch, optin):
    _set_optin(monkeypatch, optin)

    def unexpected_capture(*args):
        raise AssertionError("Ordinary local fixture attempted owned S3 capture")

    monkeypatch.setattr(hooks, "capture", unexpected_capture)
    fixturedef = SimpleNamespace(argname="storage_engine", cached_result=(object(), None, None))
    hooks.pytest_fixture_post_finalizer(fixturedef, _request())


@pytest.mark.parametrize(
    ("optin", "s3", "retained"),
    [
        (None, True, False),
        ("not-an-owned-campaign", True, False),
        ("confirmed-disposable-prefix", True, True),
        ("confirmed-disposable-prefix", False, False),
    ],
)
def test_real_schema_fixture_cleans_only_ordinary_cases(monkeypatch, optin, s3, retained):
    _set_optin(monkeypatch, optin)
    _, generator, statements, engines = _schema_fixture(monkeypatch, _request(s3))
    generator.close()
    assert any(statement.startswith("DROP SCHEMA") for statement in statements) is not retained
    assert len(engines) == 2 and all(engine.disposed for engine in engines)


def test_opted_in_capture_failure_remains_blocking_and_retains_schema(monkeypatch):
    _set_optin(monkeypatch, "confirmed-disposable-prefix")
    monkeypatch.delenv("MARKETLAB_PHASE6_S3_DATABASE_IDENTITY_SHA256", raising=False)
    request = _request()
    engine, generator, statements, engines = _schema_fixture(monkeypatch, request)
    fixturedef = SimpleNamespace(argname="storage_engine", cached_result=(engine, None, None))
    try:
        with pytest.raises(AssertionError, match="Owned S3 case snapshot failed"):
            hooks.pytest_fixture_post_finalizer(fixturedef, request)
    finally:
        generator.close()
    assert not any(statement.startswith("DROP SCHEMA") for statement in statements)
    assert len(engines) == 2 and all(engine.disposed for engine in engines)
