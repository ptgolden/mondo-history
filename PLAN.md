# Mondo History Index

*A queryable history of ontology evolution.*

## Overview

Git is the authoritative source of Mondo's history, but in practice that history is not available during normal development.

The Mondo repository has grown to the point where maintaining a complete clone with full history is impractical. Development is therefore performed using shallow clones (for example, `--depth 1`), which intentionally omit historical commits.

As a result, historical investigation becomes awkward. Questions such as

* When did this mapping change?
* Why was this synonym removed?
* When did this classification change?
* Has this issue occurred before?

cannot be answered directly from a local checkout.

Instead, developers must resort to the GitHub web interface, manually search commit history, inspect pull requests, or invent one-off techniques to reconstruct the evolution of the ontology. These approaches are often slow, incomplete, and disruptive to normal development workflows.

This is particularly unfortunate because many ontology debugging and maintenance tasks are fundamentally historical. Understanding the current state of the ontology frequently requires understanding how that state was reached.

The Mondo History Index addresses this by treating complete Git history as a build-time dependency rather than a user dependency.

A history extraction process runs once against a complete repository clone and produces a compact, queryable artifact describing the evolution of `mondo-edit.obo`. Developers query this artifact directly rather than traversing repository history.

The result is that historical investigation becomes a routine part of ontology development instead of an exceptional task requiring web searches, bespoke scripts, or access to a complete repository clone.

---

# Goals

The project aims to provide a historical view of Mondo that is:

* organized around ontology concepts rather than Git commits
* fast to query
* reproducible
* distributable as a generated artifact
* usable without cloning the Mondo repository
* suitable for both local and hosted use

The emphasis is on supporting day-to-day ontology development, debugging, review, and maintenance.

Rather than asking "Which commit changed this file?", users should be able to ask questions such as:

* When did this term last change?
* What changed for this term over time?
* When was this synonym introduced?
* When did this xref disappear?
* How has this disease classification evolved?
* Which terms changed together?
* What happened between two releases?
* Why does this term look the way it does today?

---

# Non-Goals

The Mondo History Index is **not** intended to:

* replace Git
* replace repository history
* become a second source of truth
* store a mutable copy of the ontology

Git remains authoritative. The history index is a derived representation built solely to improve historical querying.

---

# Design Principles

## Ontology-Centric

The primary unit of navigation should be ontology entities rather than commits.

Users should begin with a MONDO identifier or another ontology concept—not a commit SHA.

## Derived Artifact

The history index is generated from repository history.

The expensive work of processing Git history should occur once during artifact generation rather than every time a user asks a question.

## Independent of Repository History

Historical queries should not depend on the presence of Git history.

The generated artifact should contain sufficient historical information to answer routine ontology questions without requiring users to clone or search the complete repository.

## Deterministic

Historical queries should produce deterministic answers based on a specific version of the generated artifact.

The artifact itself should be versioned alongside Mondo releases (or another well-defined build cadence) so that historical results are reproducible.

---

# Conceptual Architecture

The system has three logical components.

```text
                Mondo Repository
                        │
                        │
              History Extraction
                        │
                        ▼
         Generated History Artifact
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
    Local CLI                  Hosted Query Service
```

Only the history extraction process requires access to the complete repository.

All user-facing tools operate against the generated history artifact.

This separation is fundamental to the design.

---

# History Artifact

The generated history artifact is the central product of the system.

It should be:

* compact
* highly compressible
* portable
* query-efficient
* immutable once generated
* versioned alongside Mondo

The implementation technology is intentionally unspecified. The design should remain compatible with modern analytical storage formats and embedded query engines without depending on any particular implementation.

Ideally, the artifact should be distributable as a single file that can be downloaded, cached, archived, and queried locally.

---

# Conceptual Data Model

Rather than organizing history around commits, the system organizes history around ontology entities.

Conceptually:

```text
Git history
        │
        ▼
Structured ontology changes
        │
        ▼
Entity history index
        │
        ▼
Historical queries
```

Each commit contributes one or more historical events associated with ontology entities.

The exact representation of those events is intentionally left unspecified. The important design decision is that users interact with ontology history rather than Git history.

---

# Query Model

Representative queries include:

* Show the complete history of `MONDO:...`.
* Show every modification to xrefs for a term.
* Show when a synonym was introduced or removed.
* Show the history of parent relationships.
* Which commits modified this term?
* Which terms changed together?
* Which ontology entities were affected by this pull request?
* What changed between two releases for this disease?
* Explain how the current state of this term evolved over time.

The design should support both interactive exploration and scripted workflows.

---

# Access Model

The history artifact should support multiple access methods while remaining the single source for historical queries.

Potential interfaces include:

* a command-line interface
* a hosted web application
* a programmatic API

Each interface should operate over the same generated artifact and produce consistent answers.

The web application should expose the same information available through the downloadable artifact rather than maintaining an independent representation.

---

# Future Directions

Although initially focused on `mondo-edit.obo`, the overall design should not be inherently Mondo-specific.

The same architecture could be applied to other version-controlled OBO ontologies or ontology-derived artifacts.

Longer term, the project could provide a general mechanism for exploring ontology evolution independently of any particular repository.

---

# Open Questions

The design intentionally leaves several questions open.

Examples include:

* What is the appropriate granularity of a historical event?
* How should ontology changes be represented internally?
* How much contextual information should accompany each event?
* Should users be able to reconstruct the state of a term at an arbitrary point in history?
* How should release information be incorporated?
* What indexing strategy best supports interactive queries?
* How should the artifact balance completeness against size?
* Which historical questions arise most frequently during ontology development?

These questions should be informed primarily by real debugging and maintenance workflows rather than implementation convenience.

---

# Vision

The Mondo History Index aims to make ontology history as easy to explore as the ontology itself.

Instead of manually traversing commits, GitHub history, and pull requests, developers should be able to ask historical questions directly and receive answers in terms of ontology concepts.

The project is fundamentally about improving the observability of ontology evolution. By transforming repository history into a compact, queryable artifact, it enables historical investigation to become a routine part of ontology development rather than a specialized form of repository archaeology.

