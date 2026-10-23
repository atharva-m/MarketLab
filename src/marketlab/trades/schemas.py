"""Canonical synthetic execution contract; no persistence or provider assumptions."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?", re.ASCII)
_TIMESTAMP_TEXT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
    re.ASCII,
)

TradeDecimal = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8, strict=True)]
TRADE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"


class Trade(BaseModel):
    """One execution with exact positive price/quantity and an aware UTC timestamp."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    trade_id: str = Field(pattern=TRADE_ID_PATTERN)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,19}$")
    executed_at: datetime
    price: TradeDecimal
    quantity: TradeDecimal

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def exact_decimal(cls, value: Any) -> Decimal:
        if isinstance(value, str) and _DECIMAL_TEXT.fullmatch(value):
            return Decimal(value)
        if isinstance(value, Decimal):
            return value
        raise ValueError("must be a Decimal or plain decimal string with at most 8 decimal places")

    @field_validator("price", "quantity")
    @classmethod
    def bounded_scale(cls, value: Decimal) -> Decimal:
        # Pydantic's decimal_places constraint ignores trailing zeroes; the wire format does not.
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -8:
            raise ValueError("must have at most 8 decimal places, including trailing zeroes")
        return value

    @field_serializer("price", "quantity", when_used="json")
    def decimal_text(self, value: Decimal) -> str:
        # Decimal's default str() can emit exponents for valid small values such as 1E-8.
        return format(value, "f")

    @field_validator("executed_at", mode="before")
    @classmethod
    def aware_utc_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, str) and _TIMESTAMP_TEXT.fullmatch(value):
            try:
                value = datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError("must be a valid timestamp") from error
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("must be an aware datetime or ISO timestamp with a timezone")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError) as error:
            raise ValueError("timestamp must be representable in UTC") from error


class TradePage(BaseModel):
    """A bounded page of canonical trades and an optional exclusive next boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    items: tuple[Trade, ...]
    next_after_id: str | None
