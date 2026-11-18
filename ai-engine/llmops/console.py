"""Console setup shared by the command-line entry points."""

import sys


def use_utf8_streams() -> None:
    """MLflow prints emoji ("🏃 View run ..."); on Windows a cp1252 stdout raises
    UnicodeEncodeError inside MLflow before it marks the run FINISHED, leaving it RUNNING."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
