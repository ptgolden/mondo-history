# mondo-history

*A queryable history of Mondo ontology evolution.*

`mondo-history` builds a compact, queryable artifact describing how every term in
Mondo's `src/ontology/mondo-edit.obo` has changed over time, so historical
questions can be answered without cloning Mondo's full git history.

See [`DESIGN.md`](./DESIGN.md) for the architecture and [`PLAN.md`](./PLAN.md) for
the original vision.

## Status

Early development — the end-to-end pipeline works on a slice of history:

- `gitsource` — file-scoped, blob-filtered clone + single-file history walk,
  following renames, reading blob content by OID.
- `obo` — normalize term frames to canonical clause sets (via fastobo) and diff
  adjacent versions clause-by-clause.
- `extract` / `model` — stream the diff into a Parquet artifact
  (`commits`, `term_snapshots`, `events`, `build_meta`).
- `query` / `cli` — DuckDB-backed queries rendered with `rich`.

## Try it

```sh
uv sync --extra dev

# Build an artifact from a recent slice of Mondo, cloning it blob-filtered.
# (Only the history of mondo-edit.obo is downloaded, lazily.)
uv run mondo-history build --out artifact --since 2026-06-01

# ...or reuse an existing local clone instead of cloning:
uv run mondo-history build --repo ../mondo --out artifact --limit 25

# A term's change history (optionally one clause kind), a point-in-time state,
# and everything that changed together in a commit.
uv run mondo-history term MONDO:0012350
uv run mondo-history term MONDO:0012350 --only synonym
uv run mondo-history term MONDO:0000002 --at 169
uv run mondo-history commit 1ac4db2

# Release-oriented views: list releases, a PR's terms, or a range diff.
uv run mondo-history releases
uv run mondo-history pr 10400
uv run mondo-history diff v2026-06-02 HEAD --term MONDO:0001213
```

## Development

```sh
uv sync --extra dev
uv run pytest
```
