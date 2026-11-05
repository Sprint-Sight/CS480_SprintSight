class AllDimensionsFailedError(RuntimeError):
    """No rubric dimension produced a score, so manual review is required."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        first = next(iter(errors.values()), "unknown error")
        super().__init__(
            f"All {len(errors)} rubric dimensions failed. First error: {first[:200]}"
        )
