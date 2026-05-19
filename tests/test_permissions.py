import os
from pathlib import Path

from could_you.permissions import format_permission_report, inspect_permission_boundary


def test_inspect_permission_boundary_reports_key_paths(tmp_workspace: Path):
    report = inspect_permission_boundary(tmp_workspace)

    assert report["workspaceRoot"] == str(tmp_workspace.parent.resolve())
    assert report["configDir"] == str(tmp_workspace.resolve())
    assert report["paths"]["workspaceRoot"]["exists"] is True
    assert report["paths"]["configDir"]["exists"] is True
    assert report["paths"]["dialogueFile"]["exists"] is False
    assert report["currentUser"]["name"]
    assert report["notes"]


def test_inspect_permission_boundary_reports_dialogue_file(tmp_workspace: Path):
    dialogue_path = tmp_workspace / "dialogue.json"
    dialogue_path.write_text("[]")

    report = inspect_permission_boundary(tmp_workspace)

    assert report["paths"]["dialogueFile"]["exists"] is True
    assert report["paths"]["dialogueFile"]["readable"] is True
    assert report["paths"]["dialogueFile"]["path"] == str(dialogue_path.resolve())


def test_format_permission_report_includes_warnings_and_notes(tmp_workspace: Path):
    report = inspect_permission_boundary(tmp_workspace)

    text = format_permission_report(report)

    assert "Permission boundary report" in text
    assert "Current user:" in text
    assert "Workspace root:" in text
    assert "Config dir:" in text
    assert "Paths:" in text
    assert "Notes:" in text


def test_inspect_permission_boundary_warns_for_world_writable_config_dir(tmp_workspace: Path):
    old_mode = tmp_workspace.stat().st_mode

    try:
        tmp_workspace.chmod(old_mode | 0o002)
        report = inspect_permission_boundary(tmp_workspace)
    finally:
        tmp_workspace.chmod(old_mode)

    if os.name != "nt":
        assert any("world-writable" in warning for warning in report["warnings"])
