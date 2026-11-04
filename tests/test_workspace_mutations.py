import json

import pytest

from backend.tools.workspace_tools import WorkspaceService, WorkspaceToolError


def service(tmp_path):
    return WorkspaceService(roots=[str(tmp_path)], max_results=20)


def test_preview_and_apply_patch_are_bounded_and_hash_checked(tmp_path, monkeypatch):
    from backend.core import config
    monkeypatch.setattr(config.settings, "WORKSPACE_MAX_WRITE_BYTES", 10_000)
    target = tmp_path / "notes.txt"
    target.write_text("hello world\n", encoding="utf-8")
    workspace = service(tmp_path)
    preview = json.loads(workspace.preview_patch(relative_path="notes.txt", old_text="world", new_text="agent"))
    assert preview["would_change"] is True
    assert "-hello world" in preview["diff"]
    assert target.read_text(encoding="utf-8") == "hello world\n"
    result = json.loads(workspace.apply_patch(relative_path="notes.txt", old_text="world", new_text="agent", expected_sha256=preview["expected_sha256"]))
    assert result["sha256"]
    assert target.read_text(encoding="utf-8") == "hello agent\n"
    with pytest.raises(WorkspaceToolError, match="changed since the preview"):
        workspace.apply_patch(relative_path="notes.txt", old_text="agent", new_text="user", expected_sha256=preview["expected_sha256"])


def test_mutations_reject_traversal_and_delete_is_reversible(tmp_path):
    workspace = service(tmp_path)
    with pytest.raises(WorkspaceToolError):
        workspace.create_file(relative_path="../outside.txt", content="no")
    target = tmp_path / "remove.txt"
    target.write_text("keep", encoding="utf-8")
    result = json.loads(workspace.delete_file(relative_path="remove.txt"))
    assert result["reversible"] is True
    assert not target.exists()
    assert (tmp_path / result["trash_path"]).read_text(encoding="utf-8") == "keep"


def test_create_and_rename_never_overwrite_destination(tmp_path):
    workspace = service(tmp_path)
    workspace.create_file(relative_path="one.txt", content="one")
    workspace.create_file(relative_path="two.txt", content="two")
    with pytest.raises(WorkspaceToolError, match="already exists"):
        workspace.rename_file(source_path="one.txt", destination_path="two.txt")
    workspace.rename_file(source_path="one.txt", destination_path="three.txt")
    assert (tmp_path / "three.txt").read_text(encoding="utf-8") == "one"
