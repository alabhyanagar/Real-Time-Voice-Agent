# Phase 3 — `workspace_list_files`

Phase 3 adds the first real workspace capability as a read-only tool.

## Configuration

Configure approved roots explicitly in `.env`:

```env
WORKSPACE_ROOTS=["D:/Alabhya/Real-Time-Voice-Agent"]
WORKSPACE_MAX_LIST_RESULTS=100
TOOLS_ENABLED=true
```

The tool refuses to run when no root is configured. Roots are addressed to the
model as `default` or `root_N`; absolute filesystem paths are never accepted as
tool input and are never returned in the result.

## Safety behavior

- Only configured directories can be listed.
- Absolute paths and `..` traversal are rejected.
- Resolved paths must remain inside the selected root.
- Symlinks are skipped to prevent root escapes.
- Hidden files are excluded unless `include_hidden=true`.
- Results are bounded by `WORKSPACE_MAX_LIST_RESULTS`.
- Results contain relative paths, type, size, and local modification time.
- The operation is read-only and low risk, so confirmation is not required.

## Result shape

```json
{
  "workspace_root": "root_0",
  "relative_path": ".",
  "recursive": true,
  "items": [
    {"path": "README.md", "name": "README.md", "kind": "file", "size_bytes": 1234}
  ],
  "truncated": false
}
```

The next workspace tools are `workspace_search` and `workspace_read_file`.
