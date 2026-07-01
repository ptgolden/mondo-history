# Mondo History Index — Design

*A concrete design for the vision in [`PLAN.md`](./PLAN.md).*

## Context

`PLAN.md` describes the goal: turn Mondo's git history into a compact, queryable
artifact so ontology developers can ask *ontology-centric* historical questions
("when did this synonym appear?", "how did this term's classification evolve?")
without cloning the full repository or doing GitHub archaeology. The vision doc
deliberately leaves the implementation unspecified. This document commits to
concrete choices.

`mondo-history` is a **separate artifact** from Mondo. The extraction step builds
its *own* clone of Mondo — scoped to a single file's history (see §3) — as a
build-time input. `../mondo` is only a shallow, depth-1 snapshot and is **not**
used as the history source. The artifact is entirely *derived from* Mondo's git
history (recreated here for the single file `src/ontology/mondo-edit.obo`), but
once built it is self-contained: **querying** it — via the CLI, API, or hosted
app — needs no access to Mondo's git history at all. The build depends on that
history; consumers do not. The artifact versions and releases on its own cadence.

Chosen stack:
- **fastobo** (Python bindings) for OBO parsing.
- **Parquet + DuckDB** for storage and query.
- A **self-contained** extraction tool that fetches just the history it needs.

### What the target looks like
- Target file: `src/ontology/mondo-edit.obo` — ~45 MB, ~35,362 `[Term]` stanzas,
  OBO 1.2. Terms carry the multivalued fields queries care about: `synonym`,
  `xref`, `is_a`, `relationship`, `subset`, `def`, `is_obsolete`, `replaced_by`.
- Commit messages embed PR numbers like `(#10400)` → PR-linking is nearly free.
- The file has moved paths over the years → extraction must use `git log --follow`.

---

## Core design decisions

### 1. Historical unit: snapshots are primitive, events are derived
- **Term-version snapshots**, stored *only on commits where a given term changed*
  (change detected by content-hashing each normalized term frame). Reconstructing
  "state of `MONDO:x` at commit `c`" = the latest snapshot with `commit_seq <= seq(c)`.
- **Change events**, materialized by diffing adjacent snapshots of the same term:
  `(mondo_id, commit_seq, predicate, value, operation)` where operation ∈ {add, remove}.
  A synonym text edit is naturally a remove+add of that clause. This table is the
  queryable spine for "when did X change".
- Snapshots are the source of truth; events are a convenience view over them.

### 2. Artifact: Parquet canonical, DuckDB query layer
- Canonical artifact = a few Parquet files. Highly compressible for repetitive
  ontology strings; engine-neutral; archival.
- CLI/API query them with **DuckDB**. DuckDB reads Parquet locally *and* range-queries
  it over HTTP, so the "hosted service" can be static file hosting (GitHub Releases /
  S3) with **no server** — clients fetch only the byte ranges they need.
- Optionally emit a convenience single-file `.duckdb` later; Parquet stays primitive.

### 3. History acquisition: build our own, scoped to one file
- **`../mondo` is NOT the source** — it's a shallow snapshot. This repo builds its
  own clone as part of the artifact build.
- Do a `git clone --filter=blob:none --no-checkout` of the source repo: full commit
  graph + trees, **no blob contents** until requested. Then walk
  `git log --follow --reverse -- src/ontology/mondo-edit.obo` and lazily `git cat-file`
  **only that one file's blobs** across history. So we only ever download the history
  of `mondo-edit.obo`, not the rest of the repo. Reproducible from a URL.
- The source URL/ref is a build parameter recorded in `build_meta`.

---

## Data model (Parquet schema)

- **`commits`** — one row per commit touching the OBO file:
  `commit_seq` (monotonic linear index, oldest=0), `sha`, `author_name`,
  `author_email`, `committed_date`, `message`, `pr_number` (nullable, parsed from
  message), `parent_sha`.
- **`releases`** — release tags mapped to commits: `tag`, `sha`, `date`, `commit_seq`.
  Enables "what changed between two releases".
- **`term_snapshots`** — one row per (term, commit-where-it-changed):
  `mondo_id`, `commit_seq`, `sha`, `name`, `is_obsolete`, `replaced_by`,
  `content_hash`, `clauses` (list<struct{predicate, value}> — canonical normalized
  frame), `frame_text` (canonical OBO serialization for exact reconstruction).
- **`events`** — derived: `mondo_id`, `commit_seq`, `sha`, `predicate`, `value`,
  `operation` (add|remove). Semantic events (term_created / term_obsoleted /
  term_merged) are just filtered views over this table.
- **`build_meta`** — schema version, generator version, source repo URL, source
  sha range (first/last `commit_seq`), obo path. Makes results deterministic and
  reproducible; supports incremental rebuilds.

Ordering: `commit_seq` linearizes history (first-parent walk of the OBO file's
commits) so point-in-time queries are simple range comparisons.

---

## Extraction algorithm (build step)

1. Acquire history (blobless clone as in §3); resolve the OBO path with `--follow`
   (handles historical renames).
2. `git log --follow --reverse --format=... -- <path>` → ordered commit list;
   parse PR numbers from messages; collect tags → `releases`.
3. Stream commits oldest→newest, holding only the *previous* version's
   `{mondo_id: (content_hash, clauses)}` in memory:
   - `git cat-file blob <sha>:<path>` → bytes.
   - Parse with **fastobo**. Trust it — no defensive fallback parser, no
     per-commit "unparseable" flagging. If fastobo raises, the build fails loudly.
   - Normalize each `[Term]` frame to a canonical clause set; hash it.
   - For each term whose hash changed (or is new): write a `term_snapshots` row and,
     by diffing clause sets vs the previous version, write `events` rows.
   - Removed terms (present before, absent now) → a removal marker event.
4. Write Parquet via pyarrow/DuckDB; write `build_meta`.
5. **Incremental mode** (`--since ARTIFACT`): read last `commit_seq` from prior
   `build_meta`, seed the "previous version" from the last snapshot state, process
   only newer commits, append. Keeps ongoing per-release rebuilds cheap.

Cost note: parsing is Rust-backed (fastobo) and one-time; term-level hashing avoids
storing/diffing unchanged terms; per-commit parse is independent and parallelizable
if needed.

**Robustness stance:** correctness comes from *types and libraries*, not defensive
code. Model snapshots/events/operations as typed dataclasses (or Pydantic/attrs) and
a small enum for `operation`/`predicate`; let fastobo, pyarrow, and DuckDB enforce
their own invariants and raise on violation. Avoid speculative edge-case handling.

---

## Interfaces (all thin DuckDB SQL over the same Parquet)

CLI (`mondo-history`):
- `term MONDO:x` — event timeline for a term.
- `term MONDO:x --at <sha|date|release>` — reconstructed snapshot at that point.
- `synonyms|xrefs|parents MONDO:x` — filtered event history for one field kind.
- `commit <sha>` — all terms changed together in that commit.
- `pr <n>` — terms affected by a PR.
- `diff <releaseA> <releaseB> [--term MONDO:x]` — changes between two releases.

Programmatic API: a small Python module exposing the same queries (returns
DataFrames/dicts). Hosted web app: reads the identical Parquet (optionally over
HTTP via DuckDB httpfs), no independent representation.

---

## Proposed repository layout

```
DESIGN.md                     # this document
pyproject.toml                # deps: fastobo, duckdb, pyarrow, click/typer
src/mondo_history/
  extract.py                  # git walk + fastobo parse + diff → Parquet
  gitsource.py                # blobless clone / repo acquisition, log --follow
  obo.py                      # frame normalization, canonical clause set, hashing
  model.py                    # Parquet schemas / table writers
  query.py                    # DuckDB query helpers (shared by CLI + API)
  cli.py                      # command-line entry point
tests/
  fixtures/                   # tiny multi-commit OBO git repo for deterministic tests
```

---

## Verification

- **Unit**: build a tiny fixture git repo with a handful of commits mutating a
  small OBO (add synonym, remove xref, reparent, obsolete, merge). Assert exact
  `events` rows and that `--at` reconstruction equals the committed file per commit.
- **Round-trip**: for random (term, commit) pairs, assert the reconstructed
  `frame_text` matches the `git cat-file`-extracted stanza of that term at that commit.
- **Integration (real data)**: run extraction against a real Mondo history
  end-to-end; sanity-check known changes (e.g. a recent PR's terms appear under
  `pr <n>`); confirm artifact size is small and queries are sub-second.
- **Determinism**: rebuild twice → identical Parquet content hashes; incremental
  build from artifact N to N+k equals a full build at N+k.

---

## Open questions deferred to implementation
- Exact canonical clause normalization (whitespace, qualifier ordering, xref-in-def).
- Whether to store `frame_text` in `term_snapshots` or reconstruct purely from `clauses`.
- Release-tag discovery: git tags vs `data-version` header vs GitHub releases API.
- Whether the CLI ships a bundled recent artifact or always downloads one.
