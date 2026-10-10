"""Raised when every rubric dimension fails evaluation for a sprint.

Lets callers distinguish a total evaluation failure (no dimension produced a
usable score) from a partial one (some dimensions failed but an average can
still be computed from the remaining dimensions).
"""
from __future__ import annotations


class AllDimensionsFailedError(Exception):
    """All rubric dimensions failed to evaluate.

    Args:
        failed_dimensions: mapping of dimension name -> error message for the
            dimensions that failed.
    """

    def __init__(self, failed_dimensions: dict[str, str]):
        self.failed_dimensions = failed_dimensions
        detail = "; ".join(f"{dim}: {err}" for dim, err in failed_dimensions.items())
        super().__init__(
            f"All {len(failed_dimensions)} rubric dimensions failed to evaluate: {detail}"
        )
