import json

import pytest

from atomic_persistence import atomic_write_json, atomic_write_text, repair_jsonl_tail


def test_atomic_json_replaces_destination_and_leaves_no_temporary_file(tmp_path):
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    atomic_write_json(destination, {"version": 2, "value": "安全"})
    assert json.loads(destination.read_text("utf-8")) == {
        "version": 2, "value": "安全"
    }
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_failed_replace_preserves_previous_file_and_cleans_temporary(
    tmp_path, monkeypatch
):
    destination = tmp_path / "state.txt"
    destination.write_text("stable", encoding="utf-8")

    def fail_replace(source, target):
        raise OSError("injected replace failure")

    monkeypatch.setattr("atomic_persistence.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        atomic_write_text(destination, "new")
    assert destination.read_text("utf-8") == "stable"
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_repair_jsonl_tail_removes_only_incomplete_final_record(tmp_path):
    destination = tmp_path / "events.jsonl"
    destination.write_bytes(b'{"id": 1}\n{"id": 2')

    assert repair_jsonl_tail(destination) is True
    assert destination.read_bytes() == b'{"id": 1}\n'
    assert repair_jsonl_tail(destination) is False


def test_repair_jsonl_tail_rejects_middle_corruption(tmp_path):
    destination = tmp_path / "events.jsonl"
    original = b'{"id": 1}\ninvalid\n{"id": 3}\n'
    destination.write_bytes(original)

    with pytest.raises(ValueError, match="corruption before final record"):
        repair_jsonl_tail(destination)
    assert destination.read_bytes() == original
