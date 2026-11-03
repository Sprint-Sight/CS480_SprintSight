class AllDimensionsFailedError(RuntimeError):
    """No rubric dimension produced a score (typically: the LLM backend is unreachable)."""
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        first = next(iter(errors.values()), "unknown error")
        super().__init__(f"All {len(errors)} rubric dimensions failed. First error: {first[:200]}")