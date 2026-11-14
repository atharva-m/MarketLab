"""Compatibility import for the shared fingerprinted dataset capacity helper."""

from marketlab.datasets.v2.capacity import (
    DEFAULT_RESEARCH_SPACE,
    OUTPUT,
    SCRATCH,
    SPILL,
    ResearchSpace,
    outstanding,
    release,
    reserve,
)

SMALL_RESEARCH_SPACE = ResearchSpace(scratch=8 * 1024**2, output=1024**2)

__all__ = [
    "DEFAULT_RESEARCH_SPACE",
    "OUTPUT",
    "SCRATCH",
    "SMALL_RESEARCH_SPACE",
    "SPILL",
    "outstanding",
    "release",
    "reserve",
]
