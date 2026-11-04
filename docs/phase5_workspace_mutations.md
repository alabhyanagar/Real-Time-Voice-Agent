# Phase 5 — Workspace mutation tools

Phase 5 adds controlled file editing to the opt-in LangChain tool graph.

## Safety contract

- Every configured root is an explicit allow-list; traversal, absolute paths,
  symlinks, hidden paths (unless explicitly enabled), and cross-root targets are
  rejected.
- `workspace_preview_patch` is read-only and returns a bounded unified diff plus
  the current SHA-256 hash.
- `workspace_apply_patch`, `workspace_create_file`, and
  `workspace_rename_file` are medium-risk operations; `workspace_delete_file`
  is high-risk. The `ToolExecutor` therefore returns
  `confirmation_required` before invoking any mutation.
- Writes are UTF-8, size-limited, and atomic (`temp file` + `os.replace`).
- Deletes are reversible: the file is moved into `.voice_agent_trash` (or the
  configured `WORKSPACE_TRASH_DIR`) with a unique timestamped name.
- `expected_sha256` prevents applying a stale preview after another process has
  changed the file.

## Tools

| Tool | Purpose | Risk | Confirmation |
|---|---|---:|---:|
| `workspace_preview_patch` | Generate a targeted replacement diff | low | No |
| `workspace_apply_patch` | Apply a reviewed replacement atomically | medium | Yes |
| `workspace_create_file` | Create or explicitly overwrite a UTF-8 file | medium | Yes |
| `workspace_rename_file` | Rename a regular file within one root | medium | Yes |
| `workspace_delete_file` | Move a file to reversible trash | high | Yes |

The active Step 8 graph remains tool-free by default. Set `TOOLS_ENABLED=true`
to select the tool-enabled graph; configure `WORKSPACE_ROOTS` before invoking
workspace tools.

## Verification

Tests cover diff-only previews, confirmation gating, stale-hash protection,
atomic writes, traversal rejection, rename collision handling, and reversible
deletes.
