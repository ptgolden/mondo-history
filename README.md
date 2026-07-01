# mondo-history

*A queryable history of Mondo ontology evolution.*

`mondo-history` builds a compact, queryable artifact describing how every term in
Mondo's `src/ontology/mondo-edit.obo` has changed over time, so historical
questions can be answered without cloning Mondo's full git history.

See [`DESIGN.md`](./DESIGN.md) for the architecture and [`PLAN.md`](./PLAN.md) for
the original vision.

## Status

Early development. Currently implemented:

- `gitsource` — builds a file-scoped, blob-filtered clone of Mondo and walks the
  history of a single file (`src/ontology/mondo-edit.obo`), yielding each version's
  bytes without downloading the rest of the repository.

## Development

```sh
uv sync --extra dev
uv run pytest
```
