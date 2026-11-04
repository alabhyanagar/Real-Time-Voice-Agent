"""Read-only tools for explicitly approved local workspace roots."""
import json
import difflib
import hashlib
import os
import shutil
import tempfile
import uuid
import subprocess
from fnmatch import fnmatch
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from backend.core.config import settings


class WorkspaceToolError(ValueError):
    """Raised when a workspace request is not safe or cannot be completed."""


class WorkspaceService:
    def __init__(self, roots: list[str] | None = None, max_results: int | None = None):
        configured = roots if roots is not None else settings.WORKSPACE_ROOTS
        if not configured:
            raise WorkspaceToolError("No workspace roots are configured")
        self.roots = []
        for raw_root in configured:
            root = Path(raw_root).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise WorkspaceToolError(f"Configured workspace root is unavailable: {raw_root}")
            self.roots.append(root)
        self.max_results = max_results or settings.WORKSPACE_MAX_LIST_RESULTS

    def _select_root(self, workspace_root: str) -> tuple[str, Path]:
        selector = workspace_root.strip().lower()
        if selector == "default":
            return "root_0", self.roots[0]
        if selector.startswith("root_"):
            try:
                index = int(selector.removeprefix("root_"))
            except ValueError as exc:
                raise WorkspaceToolError("Workspace root must be 'default' or root_N") from exc
            if index < 0 or index >= len(self.roots):
                raise WorkspaceToolError("Requested workspace root is not configured")
            return f"root_{index}", self.roots[index]
        raise WorkspaceToolError("Workspace root must be 'default' or root_N")

    @staticmethod
    def _safe_relative_path(relative_path: str) -> Path:
        requested = Path(relative_path or ".")
        if requested.is_absolute() or ".." in requested.parts:
            raise WorkspaceToolError("Workspace path must stay inside the configured root")
        return requested

    @staticmethod
    def _is_hidden(path: Path) -> bool:
        return any(part.startswith(".") for part in path.parts if part not in {".", ".."})

    @staticmethod
    def _is_secret(path: Path) -> bool:
        name = path.name.lower()
        return any(fnmatch(name, pattern.lower()) for pattern in settings.WORKSPACE_SECRET_FILE_PATTERNS)

    @staticmethod
    def _extension_allowed(path: Path) -> bool:
        allowed = {value.lower() if value.startswith(".") else f".{value.lower()}" for value in settings.WORKSPACE_ALLOWED_EXTENSIONS}
        return not allowed or not path.suffix or path.suffix.lower() in allowed

    def _resolve_target(self, workspace_root: str, relative_path: str, *, include_hidden: bool, kind: str) -> tuple[str, Path, Path]:
        root_id, root = self._select_root(workspace_root)
        requested = self._safe_relative_path(relative_path)
        original = root / requested
        target = original.resolve()
        if target != root and root not in target.parents:
            raise WorkspaceToolError("Workspace path resolves outside the configured root")
        if original.is_symlink() or (not include_hidden and self._is_hidden(requested)) or self._is_secret(requested):
            raise WorkspaceToolError("Hidden and symlink workspace paths are not available")
        if kind == "file" and not self._extension_allowed(requested):
            raise WorkspaceToolError("File extension is not allowed")
        if kind == "directory" and (not target.exists() or not target.is_dir()):
            raise WorkspaceToolError("Workspace path is not an accessible directory")
        if kind == "file" and (not target.exists() or not target.is_file()):
            raise WorkspaceToolError("Workspace path is not an accessible file")
        return root_id, root, target

    def search(
        self,
        *,
        workspace_root: str = "default",
        relative_path: str = ".",
        query: str,
        recursive: bool = True,
        include_hidden: bool = False,
        file_extensions: list[str] | None = None,
        max_results: int = 50,
        case_sensitive: bool = False,
    ) -> str:
        query = query.strip()
        if not query:
            raise WorkspaceToolError("Search query cannot be empty")
        if max_results <= 0:
            raise WorkspaceToolError("max_results must be positive")
        root_id, root, target = self._resolve_target(workspace_root, relative_path, include_hidden=include_hidden, kind="directory")
        extensions = None if not file_extensions else {
            extension.lower() if extension.startswith(".") else f".{extension.lower()}"
            for extension in file_extensions
        }
        needle = query if case_sensitive else query.lower()
        candidates = target.rglob("*") if recursive else target.iterdir()
        results = []
        truncated = False
        for item in sorted(candidates, key=lambda value: value.as_posix().lower()):
            try:
                if item.is_symlink() or not item.is_file() or (not include_hidden and self._is_hidden(item.relative_to(root))) or self._is_secret(item.relative_to(root)) or not self._extension_allowed(item):
                    continue
                if extensions and item.suffix.lower() not in extensions:
                    continue
                resolved = item.resolve()
                if resolved != root and root not in resolved.parents:
                    continue
                if len(results) >= min(max_results, self.max_results):
                    truncated = True
                    break
                relative = item.relative_to(root).as_posix()
                filename = item.name if case_sensitive else item.name.lower()
                if needle in filename:
                    results.append({"path": relative, "match_type": "filename", "line_number": None, "snippet": item.name})
                    if len(results) >= min(max_results, self.max_results):
                        continue
                stat = item.stat()
                if stat.st_size > settings.WORKSPACE_MAX_SEARCH_FILE_BYTES:
                    continue
                sample = item.read_bytes()[:4096]
                if b"\x00" in sample:
                    continue
                with item.open("r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        haystack = line if case_sensitive else line.lower()
                        if needle in haystack:
                            if len(results) >= min(max_results, self.max_results):
                                truncated = True
                                break
                            results.append({
                                "path": relative,
                                "match_type": "content",
                                "line_number": line_number,
                                "snippet": line.strip()[:240],
                            })
                            if len(results) >= min(max_results, self.max_results):
                                break
            except (OSError, UnicodeError, ValueError):
                continue
        return json.dumps({
            "workspace_root": root_id,
            "relative_path": self._safe_relative_path(relative_path).as_posix(),
            "query": query,
            "items": results,
            "truncated": truncated,
        }, separators=(",", ":"))

    def read_file(
        self,
        *,
        workspace_root: str = "default",
        relative_path: str,
        start_line: int = 1,
        max_lines: int = 200,
        include_hidden: bool = False,
    ) -> str:
        if start_line <= 0 or max_lines <= 0:
            raise WorkspaceToolError("start_line and max_lines must be positive")
        root_id, root, target = self._resolve_target(workspace_root, relative_path, include_hidden=include_hidden, kind="file")
        if target.stat().st_size > settings.WORKSPACE_MAX_READ_BYTES:
            raise WorkspaceToolError("File exceeds the configured read limit")
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            raise WorkspaceToolError("Binary files are not available through the text reader")
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        limit = min(max_lines, settings.WORKSPACE_MAX_READ_LINES)
        selected = lines[start_line - 1:start_line - 1 + limit]
        end_line = start_line + len(selected) - 1 if selected else start_line - 1
        return json.dumps({
            "workspace_root": root_id,
            "path": target.relative_to(root).as_posix(),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": len(lines),
            "content": "".join(f"{number}: {line}\n" for number, line in enumerate(selected, start=start_line)),
            "truncated": end_line < len(lines),
        }, separators=(",", ":"))

    def list_files(
        self,
        *,
        workspace_root: str = "default",
        relative_path: str = ".",
        recursive: bool = False,
        include_hidden: bool = False,
        max_results: int = 100,
    ) -> str:
        if max_results <= 0:
            raise WorkspaceToolError("max_results must be positive")
        root_id, root = self._select_root(workspace_root)
        requested = self._safe_relative_path(relative_path)
        target = (root / requested).resolve()
        if target != root and root not in target.parents:
            raise WorkspaceToolError("Workspace path resolves outside the configured root")
        if target.is_symlink() or not target.exists() or not target.is_dir():
            raise WorkspaceToolError("Workspace path is not an accessible directory")

        limit = min(max_results, self.max_results)
        candidates = target.rglob("*") if recursive else target.iterdir()
        entries = []
        truncated = False
        for item in sorted(candidates, key=lambda value: value.as_posix().lower()):
            try:
                if item.is_symlink() or (not include_hidden and self._is_hidden(item.relative_to(root))) or self._is_secret(item.relative_to(root)) or (item.is_file() and not self._extension_allowed(item)):
                    continue
                resolved = item.resolve()
                if resolved != root and root not in resolved.parents:
                    continue
                stat = item.stat()
            except (OSError, ValueError):
                continue
            if len(entries) >= limit:
                truncated = True
                break
            relative = item.relative_to(root).as_posix()
            entries.append({
                "path": relative,
                "name": item.name,
                "kind": "directory" if item.is_dir() else "file",
                "size_bytes": stat.st_size if item.is_file() else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            })
        return json.dumps({
            "workspace_root": root_id,
            "relative_path": requested.as_posix(),
            "recursive": recursive,
            "items": entries,
            "truncated": truncated,
        }, separators=(",", ":"))

    def _resolve_write_target(self, workspace_root: str, relative_path: str, *, include_hidden: bool, must_exist: bool = False) -> tuple[str, Path, Path]:
        root_id, root = self._select_root(workspace_root)
        requested = self._safe_relative_path(relative_path)
        if requested == Path("."):
            raise WorkspaceToolError("A file path is required")
        if not include_hidden and self._is_hidden(requested) or self._is_secret(requested):
            raise WorkspaceToolError("Hidden or secret workspace paths are not available")
        if not self._extension_allowed(requested):
            raise WorkspaceToolError("File extension is not allowed")
        original = root / requested
        if original.exists() and original.is_symlink():
            raise WorkspaceToolError("Symlink workspace paths are not available")
        target = original.resolve()
        if target != root and root not in target.parents:
            raise WorkspaceToolError("Workspace path resolves outside the configured root")
        parent = original.parent.resolve()
        if parent != root and root not in parent.parents:
            raise WorkspaceToolError("Workspace parent resolves outside the configured root")
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise WorkspaceToolError("Workspace parent directory is unavailable")
        if must_exist and (not target.exists() or not target.is_file()):
            raise WorkspaceToolError("Workspace path is not an accessible file")
        return root_id, root, target

    @staticmethod
    def _hash_bytes(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _read_editable(self, workspace_root: str, relative_path: str, include_hidden: bool) -> tuple[str, Path, Path, str, bytes]:
        root_id, root, target = self._resolve_write_target(workspace_root, relative_path, include_hidden=include_hidden, must_exist=True)
        raw = target.read_bytes()
        if len(raw) > settings.WORKSPACE_MAX_WRITE_BYTES:
            raise WorkspaceToolError("File exceeds the configured write limit")
        if b"\x00" in raw[:4096]:
            raise WorkspaceToolError("Binary files are not available through the text editor")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceToolError("File is not valid UTF-8 text") from exc
        return root_id, root, target, text, raw

    @staticmethod
    def _patch_text(current: str, old_text: str, new_text: str, replace_all: bool) -> tuple[str, int]:
        if not old_text:
            raise WorkspaceToolError("old_text cannot be empty")
        matches = current.count(old_text)
        if matches == 0:
            raise WorkspaceToolError("old_text was not found in the target file")
        if matches > 1 and not replace_all:
            raise WorkspaceToolError("old_text matched multiple locations; set replace_all=true")
        return current.replace(old_text, new_text, -1 if replace_all else 1), matches

    def preview_patch(self, *, workspace_root: str = "default", relative_path: str, old_text: str, new_text: str, replace_all: bool = False, include_hidden: bool = False) -> str:
        _, root, target, current, raw = self._read_editable(workspace_root, relative_path, include_hidden)
        if len(new_text.encode("utf-8")) > settings.WORKSPACE_MAX_WRITE_BYTES:
            raise WorkspaceToolError("Replacement text exceeds the configured write limit")
        updated, matches = self._patch_text(current, old_text, new_text, replace_all)
        diff = "".join(difflib.unified_diff(current.splitlines(True), updated.splitlines(True), fromfile=target.relative_to(root).as_posix(), tofile=target.relative_to(root).as_posix()))
        return json.dumps({"path": target.relative_to(root).as_posix(), "matches": matches, "would_change": updated != current, "diff": diff, "expected_sha256": self._hash_bytes(raw)}, separators=(",", ":"))

    def _atomic_write(self, target: Path, content: str) -> bytes:
        encoded = content.encode("utf-8")
        if len(encoded) > settings.WORKSPACE_MAX_WRITE_BYTES:
            raise WorkspaceToolError("File exceeds the configured write limit")
        fd, temp_name = tempfile.mkstemp(prefix=".voice-agent-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return encoded

    def apply_patch(self, *, workspace_root: str = "default", relative_path: str, old_text: str, new_text: str, replace_all: bool = False, expected_sha256: str | None = None, include_hidden: bool = False) -> str:
        _, root, target, current, raw = self._read_editable(workspace_root, relative_path, include_hidden)
        actual_hash = self._hash_bytes(raw)
        if expected_sha256 and expected_sha256 != actual_hash:
            raise WorkspaceToolError("Target changed since the preview; refresh the patch")
        updated, matches = self._patch_text(current, old_text, new_text, replace_all)
        encoded = self._atomic_write(target, updated)
        diff = "".join(difflib.unified_diff(current.splitlines(True), updated.splitlines(True), fromfile=target.relative_to(root).as_posix(), tofile=target.relative_to(root).as_posix()))
        return json.dumps({"path": target.relative_to(root).as_posix(), "matches": matches, "bytes_written": len(encoded), "sha256": self._hash_bytes(encoded), "diff": diff}, separators=(",", ":"))

    def create_file(self, *, workspace_root: str = "default", relative_path: str, content: str, overwrite: bool = False, include_hidden: bool = False) -> str:
        _, root, target = self._resolve_write_target(workspace_root, relative_path, include_hidden=include_hidden)
        existed = target.exists()
        if existed and not overwrite:
            raise WorkspaceToolError("Target file already exists; set overwrite=true to replace it")
        if existed and (target.is_symlink() or not target.is_file()):
            raise WorkspaceToolError("Target is not a regular file")
        encoded = self._atomic_write(target, content)
        return json.dumps({"path": target.relative_to(root).as_posix(), "bytes_written": len(encoded), "sha256": self._hash_bytes(encoded), "overwrote": existed}, separators=(",", ":"))

    def rename_file(self, *, workspace_root: str = "default", source_path: str, destination_path: str, include_hidden: bool = False) -> str:
        _, root, source = self._resolve_write_target(workspace_root, source_path, include_hidden=include_hidden, must_exist=True)
        _, _, destination = self._resolve_write_target(workspace_root, destination_path, include_hidden=include_hidden)
        if source.is_dir():
            raise WorkspaceToolError("Only regular files can be renamed by this tool")
        if destination.exists():
            raise WorkspaceToolError("Destination already exists")
        source.rename(destination)
        return json.dumps({"source_path": source.relative_to(root).as_posix(), "destination_path": destination.relative_to(root).as_posix()}, separators=(",", ":"))

    def delete_file(self, *, workspace_root: str = "default", relative_path: str, include_hidden: bool = False) -> str:
        root_id, root, target = self._resolve_write_target(workspace_root, relative_path, include_hidden=include_hidden, must_exist=True)
        if target == root or not target.is_file():
            raise WorkspaceToolError("Only regular files can be moved to trash")
        trash = root / settings.WORKSPACE_TRASH_DIR
        trash_parent = trash.parent.resolve()
        if trash_parent != root and root not in trash_parent.parents:
            raise WorkspaceToolError("Configured trash directory is unsafe")
        if trash.parent.exists() and trash.parent.is_symlink():
            raise WorkspaceToolError("Configured trash directory parent is a symlink")
        if trash.exists() and trash.is_symlink():
            raise WorkspaceToolError("Configured trash directory is a symlink")
        trash.mkdir(parents=True, exist_ok=True)
        if trash.is_symlink() or root not in trash.resolve().parents:
            raise WorkspaceToolError("Configured trash directory is unsafe")
        destination = trash / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex}_{target.name}"
        shutil.move(str(target), str(destination))
        return json.dumps({"workspace_root": root_id, "original_path": target.relative_to(root).as_posix(), "trash_path": destination.relative_to(root).as_posix(), "reversible": True}, separators=(",", ":"))

    def _git(self, workspace_root: str, args: list[str], *, max_bytes: int = 200_000) -> str:
        _, root = self._select_root(workspace_root)
        if not (root / ".git").exists():
            raise WorkspaceToolError("Configured workspace root is not a Git repository")
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=settings.WORKSPACE_GIT_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspaceToolError("Git operation failed or timed out") from exc
        if result.returncode != 0:
            raise WorkspaceToolError(result.stderr.strip()[:1000] or "Git operation failed")
        output = result.stdout[:max_bytes]
        return output

    def git_status(self, *, workspace_root: str = "default") -> str:
        output = self._git(workspace_root, ["status", "--short", "--branch"])
        return json.dumps({"workspace_root": self._select_root(workspace_root)[0], "status": output, "truncated": len(output) >= 200_000}, separators=(",", ":"))

    def git_diff(self, *, workspace_root: str = "default", staged: bool = False, relative_path: str | None = None) -> str:
        args = ["diff"] + (["--cached"] if staged else [])
        if relative_path:
            requested = self._safe_relative_path(relative_path)
            args.extend(["--", requested.as_posix()])
        output = self._git(workspace_root, args)
        return json.dumps({"workspace_root": self._select_root(workspace_root)[0], "staged": staged, "path": relative_path, "diff": output, "truncated": len(output) >= 200_000}, separators=(",", ":"))

    def git_commit(self, *, workspace_root: str = "default", relative_paths: list[str], message: str) -> str:
        if not relative_paths or len(relative_paths) > 100 or not message.strip() or len(message) > 500:
            raise WorkspaceToolError("Commit requires 1-100 paths and a 1-500 character message")
        safe_paths = [self._safe_relative_path(path).as_posix() for path in relative_paths]
        root_id, root = self._select_root(workspace_root)
        self._git(workspace_root, ["add", "--", *safe_paths])
        output = self._git(workspace_root, ["commit", "-m", message, "--", *safe_paths])
        return json.dumps({"workspace_root": root_id, "paths": safe_paths, "message": message, "commit_output": output}, separators=(",", ":"))

    def git_revert_commit(self, *, workspace_root: str = "default", commit_sha: str) -> str:
        if not commit_sha or len(commit_sha) > 64 or not all(char in "0123456789abcdefABCDEF" for char in commit_sha):
            raise WorkspaceToolError("A valid explicit Git commit SHA is required")
        output = self._git(workspace_root, ["revert", "--no-edit", commit_sha])
        return json.dumps({"workspace_root": self._select_root(workspace_root)[0], "reverted_commit": commit_sha, "revert_output": output}, separators=(",", ":"))


@tool
def workspace_list_files(
    workspace_root: str = "default",
    relative_path: str = ".",
    recursive: bool = False,
    include_hidden: bool = False,
    max_results: int = 100,
) -> str:
    """List files and directories under an explicitly approved workspace root."""
    service = WorkspaceService()
    return service.list_files(
        workspace_root=workspace_root,
        relative_path=relative_path,
        recursive=recursive,
        include_hidden=include_hidden,
        max_results=max_results,
    )


@tool
def workspace_search(
    query: str,
    workspace_root: str = "default",
    relative_path: str = ".",
    recursive: bool = True,
    include_hidden: bool = False,
    file_extensions: list[str] | None = None,
    max_results: int = 50,
    case_sensitive: bool = False,
) -> str:
    """Search filenames and UTF-8 text inside an approved workspace root."""
    return WorkspaceService().search(
        workspace_root=workspace_root,
        relative_path=relative_path,
        query=query,
        recursive=recursive,
        include_hidden=include_hidden,
        file_extensions=file_extensions,
        max_results=max_results,
        case_sensitive=case_sensitive,
    )


@tool
def workspace_read_file(
    relative_path: str,
    workspace_root: str = "default",
    start_line: int = 1,
    max_lines: int = 200,
    include_hidden: bool = False,
) -> str:
    """Read a bounded UTF-8 excerpt from an approved workspace file."""
    return WorkspaceService().read_file(
        workspace_root=workspace_root,
        relative_path=relative_path,
        start_line=start_line,
        max_lines=max_lines,
        include_hidden=include_hidden,
    )


@tool
def workspace_preview_patch(relative_path: str, old_text: str, new_text: str, workspace_root: str = "default", replace_all: bool = False, include_hidden: bool = False) -> str:
    """Preview a targeted text replacement without modifying the workspace."""
    return WorkspaceService().preview_patch(workspace_root=workspace_root, relative_path=relative_path, old_text=old_text, new_text=new_text, replace_all=replace_all, include_hidden=include_hidden)


@tool
def workspace_apply_patch(relative_path: str, old_text: str, new_text: str, workspace_root: str = "default", replace_all: bool = False, expected_sha256: str | None = None, include_hidden: bool = False, idempotency_key: str | None = None) -> str:
    """Apply a targeted text replacement after the executor obtains confirmation."""
    return WorkspaceService().apply_patch(workspace_root=workspace_root, relative_path=relative_path, old_text=old_text, new_text=new_text, replace_all=replace_all, expected_sha256=expected_sha256, include_hidden=include_hidden)


@tool
def workspace_create_file(relative_path: str, content: str, workspace_root: str = "default", overwrite: bool = False, include_hidden: bool = False, idempotency_key: str | None = None) -> str:
    """Create a UTF-8 workspace file; execution is confirmation-gated."""
    return WorkspaceService().create_file(workspace_root=workspace_root, relative_path=relative_path, content=content, overwrite=overwrite, include_hidden=include_hidden)


@tool
def workspace_rename_file(source_path: str, destination_path: str, workspace_root: str = "default", include_hidden: bool = False, idempotency_key: str | None = None) -> str:
    """Rename a regular workspace file without crossing the approved root."""
    return WorkspaceService().rename_file(workspace_root=workspace_root, source_path=source_path, destination_path=destination_path, include_hidden=include_hidden)


@tool
def workspace_delete_file(relative_path: str, workspace_root: str = "default", include_hidden: bool = False, idempotency_key: str | None = None) -> str:
    """Move a workspace file to the configured reversible trash directory."""
    return WorkspaceService().delete_file(workspace_root=workspace_root, relative_path=relative_path, include_hidden=include_hidden)


@tool
def workspace_git_status(workspace_root: str = "default") -> str:
    """Return bounded Git status for an approved workspace repository."""
    return WorkspaceService().git_status(workspace_root=workspace_root)


@tool
def workspace_git_diff(workspace_root: str = "default", staged: bool = False, relative_path: str | None = None) -> str:
    """Return a bounded Git diff without changing repository state."""
    return WorkspaceService().git_diff(workspace_root=workspace_root, staged=staged, relative_path=relative_path)


@tool
def workspace_git_commit(relative_paths: list[str], message: str, workspace_root: str = "default", idempotency_key: str | None = None) -> str:
    """Commit explicitly selected workspace paths after executor confirmation."""
    return WorkspaceService().git_commit(workspace_root=workspace_root, relative_paths=relative_paths, message=message)


@tool
def workspace_git_revert_commit(commit_sha: str, workspace_root: str = "default", idempotency_key: str | None = None) -> str:
    """Revert one explicit Git commit after executor confirmation."""
    return WorkspaceService().git_revert_commit(workspace_root=workspace_root, commit_sha=commit_sha)
