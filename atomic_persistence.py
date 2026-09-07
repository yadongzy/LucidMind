"""Shared crash-safe helpers for local file persistence."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def repair_jsonl_tail(path: Path | str) -> bool:
    """Atomically remove an invalid final JSONL record only."""
    destination = Path(path)
    if not destination.exists() or destination.stat().st_size == 0:
        return False

    lines = destination.read_bytes().splitlines(keepends=True)
    non_empty = [index for index, line in enumerate(lines) if line.strip()]
    if not non_empty:
        return False

    last_index = non_empty[-1]
    for index in non_empty:
        try:
            json.loads(lines[index].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if index != last_index:
                raise ValueError(
                    f"JSONL corruption before final record: {destination}"
                ) from exc
            atomic_write_text(
                destination, b"".join(lines[:index]).decode("utf-8")
            )
            return True
    return False


def atomic_write_text(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """Flush a temporary file and atomically replace the destination."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path | str, data: Any) -> None:
    """Serialize JSON through the shared crash-safe text writer."""
    atomic_write_text(
        path, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
