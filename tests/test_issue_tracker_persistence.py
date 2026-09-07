import json

import pytest


@pytest.fixture(autouse=True)
def isolated_issue_store(tmp_path, monkeypatch):
    import issue_tracker

    monkeypatch.setattr(issue_tracker, "_DATA", tmp_path)
    monkeypatch.setattr(issue_tracker, "_ISSUES_FILE", tmp_path / "issues.json")


def test_issue_updates_use_valid_atomic_json():
    import issue_tracker

    issue = issue_tracker.report_issue("disk warning", "medium", "test")
    issue_tracker.mark_verifying(issue["id"], "fixed")
    stored = json.loads(issue_tracker._ISSUES_FILE.read_text("utf-8"))
    assert stored[0]["status"] == "verifying"
    assert list(issue_tracker._DATA.glob("*.tmp")) == []
    assert list(issue_tracker._DATA.glob(".*.tmp")) == []


def test_failed_issue_replace_preserves_previous_state(tmp_path, monkeypatch):
    import issue_tracker

    issue_tracker._ISSUES_FILE.write_text("[]", encoding="utf-8")

    def fail_replace(source, target):
        raise OSError("injected replace failure")

    monkeypatch.setattr("atomic_persistence.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        issue_tracker.report_issue("new issue")
    assert json.loads(issue_tracker._ISSUES_FILE.read_text("utf-8")) == []
