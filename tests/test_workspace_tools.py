import json
import tempfile
from pathlib import Path

import pytest

from backend.tools.workspace_tools import WorkspaceService, WorkspaceToolError


def test_workspace_listing_returns_relative_safe_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "notes.txt").write_text("hello", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
        (root / ".secret").write_text("hidden", encoding="utf-8")

        result = json.loads(WorkspaceService([directory]).list_files(recursive=True))

        assert result["workspace_root"] == "root_0"
        assert {item["path"] for item in result["items"]} == {"notes.txt", "src", "src/main.py"}
        assert all(directory not in item["path"] for item in result["items"])


def test_workspace_listing_enforces_root_boundaries_and_result_limits():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index in range(3):
            (root / f"file-{index}.txt").write_text(str(index), encoding="utf-8")
        service = WorkspaceService([directory], max_results=2)

        result = json.loads(service.list_files(max_results=2))
        assert len(result["items"]) == 2
        assert result["truncated"] is True
        with pytest.raises(WorkspaceToolError):
            service.list_files(relative_path="../")


def test_workspace_listing_requires_an_explicit_configured_root():
    with pytest.raises(WorkspaceToolError):
        WorkspaceService([])


def test_workspace_search_returns_filename_and_content_matches():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "notes.txt").write_text("alpha\nneedle appears here\nomega\n", encoding="utf-8")
        (root / "other.py").write_text("needle = True\n", encoding="utf-8")

        result = json.loads(WorkspaceService([directory]).search(query="needle"))

        assert {item["path"] for item in result["items"]} == {"notes.txt", "other.py"}
        assert any(item["line_number"] == 2 for item in result["items"])


def test_workspace_read_file_returns_bounded_numbered_excerpt():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "README.md").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

        result = json.loads(WorkspaceService([directory]).read_file(relative_path="README.md", start_line=2, max_lines=2))

        assert result["path"] == "README.md"
        assert result["content"] == "2: two\n3: three\n"
        assert result["truncated"] is True


def test_workspace_read_file_rejects_binary_content():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "image.bin"
        path.write_bytes(b"\x00\x01\x02")
        with pytest.raises(WorkspaceToolError):
            WorkspaceService([directory]).read_file(relative_path="image.bin")


def test_workspace_rejects_secret_files_and_disallowed_extensions(monkeypatch):
    from backend.core import config
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "credentials.json").write_text('{"token":"secret"}', encoding="utf-8")
        (root / "notes.md").write_text("safe", encoding="utf-8")
        service = WorkspaceService([directory])
        with pytest.raises(WorkspaceToolError):
            service.read_file(relative_path="credentials.json")
        monkeypatch.setattr(config.settings, "WORKSPACE_ALLOWED_EXTENSIONS", [".txt"])
        with pytest.raises(WorkspaceToolError):
            service.read_file(relative_path="notes.md")
