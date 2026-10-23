import asyncio
from collections.abc import Callable


def pytest_asyncio_loop_factories() -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    # Psycopg async connections require the selector loop on Windows.
    return {"selector": asyncio.SelectorEventLoop}
