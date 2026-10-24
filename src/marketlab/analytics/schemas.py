"""Documented immutable analytical response schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

DecimalText = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,19})\.[0-9]{18}$")]
VwapText = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,37})\.[0-9]{18}$")]
VersionText = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Bar(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    start: str = Field(description="Inclusive UTC bar boundary")
    end: str = Field(description="Exclusive UTC bar boundary")
    open: DecimalText
    high: DecimalText
    low: DecimalText
    close: DecimalText
    base_volume: DecimalText
    quote_volume: DecimalText
    trade_count: int = Field(ge=1, le=100_000_000)
    vwap: VwapText = Field(description="Source quote/base volume, half-even to 18 decimal places")


class BarResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dataset_versions: list[VersionText] = Field(min_length=1, max_length=5)
    symbol: Literal["BTCUSDT", "ETHUSDT"]
    interval: Literal["1m", "5m"]
    start: str
    end: str
    definition: Literal["bars-v1"]
    expected_buckets: int = Field(ge=1, le=1440)
    returned_buckets: int = Field(ge=0, le=1440)
    empty_buckets: int = Field(ge=0, le=1440)
    bars: list[Bar] = Field(max_length=1440)
