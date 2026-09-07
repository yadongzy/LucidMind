import json

import pytest

from scripts.safe_refactor_backup import create_snapshot, verify_snapshot


def test_snapshot_round_trip_and_checksum(tmp_path):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    (data / "queue.json").write_text('{"tasks": []}\n', encoding="utf-8")
    (data / "nested").mkdir()
    (data / "nested" / "memory.jsonl").write_text('{"id": 1}\n', encoding="utf-8")

    snapshot = create_snapshot(project, tmp_path / "backups")
    result = verify_snapshot(snapshot)

    assert result["verified"] is True
    assert result["restored_files"] == 2
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format_version"] == 1
    assert len(manifest["sha256"]) == 64


def test_snapshot_verification_rejects_corruption(tmp_path):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    (data / "queue.json").write_text("{}\n", encoding="utf-8")
    snapshot = create_snapshot(project, tmp_path / "backups")
    archive = snapshot / "data.tar.gz"
    archive.write_bytes(archive.read_bytes() + b"corrupt")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_snapshot(snapshot)
