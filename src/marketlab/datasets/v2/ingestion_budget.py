"""Physical and logical budgets for a targeted, checksum-pinned official import."""

from dataclasses import dataclass

from .common import DEFAULT_LIMITS, HASH, Limits, V2Error
from .core import uid

CHECKSUM_BYTES = 4096
COMPACT_LIMITS = Limits(
    source_bytes=128 * 1024**2,
    compressed_bytes=128 * 1024**2,
    parquet_bytes=256 * 1024**2,
    scratch_bytes=1024**3,
)
COMPACT_OUTPUT_BYTES = COMPACT_LIMITS.parquet_bytes + 2 * COMPACT_LIMITS.metadata_bytes
COMPACT_SCRATCH_BYTES = (
    COMPACT_LIMITS.scratch_bytes + COMPACT_LIMITS.compressed_bytes + CHECKSUM_BYTES
)
COMPACT_LOGICAL_BYTES = COMPACT_LIMITS.compressed_bytes + CHECKSUM_BYTES + COMPACT_OUTPUT_BYTES


@dataclass(frozen=True)
class OfficialBudget:
    submission_id: str
    source_sha256: str

    def __post_init__(self) -> None:
        uid(self.submission_id)
        if not isinstance(self.source_sha256, str) or not HASH.fullmatch(self.source_sha256):
            raise V2Error("invalid_request", "Compact official ingestion requires an archive hash")

    @property
    def limits(self) -> Limits:
        return COMPACT_LIMITS

    @property
    def output_bytes(self) -> int:
        return COMPACT_OUTPUT_BYTES

    @property
    def scratch_bytes(self) -> int:
        return COMPACT_SCRATCH_BYTES

    @property
    def physical_bytes(self) -> int:
        return self.scratch_bytes + self.output_bytes

    @property
    def logical_bytes(self) -> int:
        return COMPACT_LOGICAL_BYTES


DEFAULT_OUTPUT_BYTES = DEFAULT_LIMITS.parquet_bytes + 2 * DEFAULT_LIMITS.metadata_bytes
