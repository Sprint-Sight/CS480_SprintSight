from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

AUDIT_LOG_DIR = Path(os.getenv("LLM_AUDIT_LOG_DIR", "/app/audit_logs"))
# One JSON line per Ollama request with wall-clock start/end, so
# research/gpu_report.py can tell GPU samples taken while a request was in
# flight from samples taken while the GPU had nothing to do.
REQUEST_MARKERS_PATH = Path(
    os.getenv("LLM_REQUEST_MARKERS_PATH", str(AUDIT_LOG_DIR / "request_markers.jsonl"))
)
_write_lock = Lock()


def write_request_marker(marker: dict[str, Any]) -> None:
    """Append one request's timing marker to the JSONL file."""
    REQUEST_MARKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(marker, default=str)
    with _write_lock, REQUEST_MARKERS_PATH.open("a", encoding="utf-8") as markers:
        markers.write(line + "\n")


def write_audit_record(record: dict[str, Any]) -> None:
    """Write one complete LLM request/response record to a readable text file."""
    logged_at = datetime.now(UTC)
    request_id = str(record.get("request_id", "unknown"))
    dimension = str(record.get("dimension", "unknown"))
    safe_request_id = request_id.replace("-", "")[:12]
    safe_dimension = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in dimension
    )
    filename = (
        f"llm_{logged_at.strftime('%Y%m%dT%H%M%S_%fZ')}_"
        f"{safe_request_id}_{safe_dimension}.txt"
    )
    metadata = {
        key: value
        for key, value in record.items()
        if key not in {"request", "raw_response", "error", "request_started_at", "awaiting_response"}
    }
    request = record.get("request")
    raw_response = record.get("raw_response", "")
    content = "\n".join(
        [
            "SPRINTSIGHT LLM AUDIT RECORD",
            "=" * 80,
            "",
            "METADATA",
            "--------",
            json.dumps({"logged_at": logged_at.isoformat(), **metadata}, indent=2, default=str),
            "",
            "INPUT SENT TO OLLAMA",
            "--------------------",
            json.dumps(request, indent=2, ensure_ascii=True, default=str)
            if not isinstance(request, str)
            else request,
            "",
            "RAW OUTPUT FROM OLLAMA",
            "----------------------",
            str(raw_response),
        ]
    )
    if "error" in record:
        content += f"\n\nCLIENT ERROR\n------------\n{record['error']}\n"

    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        (AUDIT_LOG_DIR / filename).write_text(content, encoding="utf-8")