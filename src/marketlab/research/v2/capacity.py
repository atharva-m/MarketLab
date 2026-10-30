"""Compatibility import for the shared fingerprinted dataset capacity helper."""

from marketlab.datasets.v2.capacity import OUTPUT, SCRATCH, SPILL, outstanding, release, reserve

__all__ = ["OUTPUT", "SCRATCH", "SPILL", "outstanding", "release", "reserve"]
