"""Deterministic synthetic trades for offline contract tests and examples."""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketlab.trades.schemas import Trade

_START = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
_SYMBOLS = ("SYN.A", "SYN.B", "SYN.C")


def _decimal(value: int, places: int) -> Decimal:
    whole, fraction = divmod(value, 10**places)
    return Decimal(f"{whole}.{fraction:0{places}d}")


def synthetic_trades(count: int = 8, *, seed: int = 0) -> tuple[Trade, ...]:
    """Return repeatable fixtures without clocks, files, services or global RNG state."""
    if type(count) is not int or count < 0:
        raise ValueError("count must be a nonnegative integer")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer between 0 and 2**32 - 1")
    rng = random.Random(seed)
    return tuple(
        Trade(
            trade_id=f"SYN-{seed}-{index:06d}",
            symbol=_SYMBOLS[rng.randrange(len(_SYMBOLS))],
            executed_at=_START + timedelta(milliseconds=index),
            price=_decimal(rng.randrange(100, 100_001), 2),
            quantity=_decimal(rng.randrange(1, 10_001), 3),
        )
        for index in range(count)
    )
