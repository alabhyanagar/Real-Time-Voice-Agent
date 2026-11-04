# Phase 4 — Workspace Search and File Reading

Phase 4 adds two read-only workspace tools on top of the Phase 3 root sandbox:

- `workspace_search` searches filenames and UTF-8 text.
- `workspace_read_file` returns a bounded, numbered text excerpt.

## Search behavior

- Searches only inside configured `WORKSPACE_ROOTS`.
- Supports recursive search, extension filters, case sensitivity, and result limits.
- Returns relative paths, match type, line number, and short snippets.
- Skips symlinks, hidden paths by default, binary files, and oversized files.

## Read behavior

- Accepts a relative path inside an approved root.
- Rejects traversal, symlink paths, binary content, and oversized files.
- Supports `start_line` and bounded `max_lines`.
- Returns numbered content and total line count without exposing an absolute path.

Configure limits with:

```env
WORKSPACE_MAX_SEARCH_FILE_BYTES=1000000
WORKSPACE_MAX_READ_BYTES=256000
WORKSPACE_MAX_READ_LINES=300
```

Both tools are low-risk read operations and do not require confirmation. The
next workspace phase adds mutation only after diff previews and confirmation.
