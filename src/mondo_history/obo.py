"""Parse an OBO document into normalized, hashable per-term state.

Normalization leans entirely on fastobo: every clause serializes to its canonical
OBO line (``predicate: value``) via ``str(clause)``, so we never hand-maintain a
mapping of clause classes. A term's state is the *set* of those clauses plus a
content hash, which is what lets the extractor detect "did this term change?"
cheaply and diff two versions clause-by-clause.
"""

import hashlib
import io
from collections import Counter
from dataclasses import dataclass

import fastobo


@dataclass(frozen=True, order=True)
class Clause:
    """One canonical OBO clause of a term, split into tag and remainder.

    ``predicate`` is the OBO tag (``name``, ``synonym``, ``xref``, ``is_a``,
    ``relationship``, ``subset``, ``def``, ``is_obsolete``, ``replaced_by``, ...);
    ``value`` is the rest of the serialized line.
    """

    predicate: str
    value: str


@dataclass(frozen=True)
class TermState:
    """A term's normalized content at one point in history."""

    mondo_id: str
    clauses: tuple[Clause, ...]  # sorted, canonical
    content_hash: str


def clauses_of(frame: fastobo.term.TermFrame) -> tuple[Clause, ...]:
    """Canonical, order-independent clause set for a term frame."""
    out = [_split(str(clause)) for clause in frame]
    return tuple(sorted(out))


def _split(line: str) -> Clause:
    predicate, _, value = line.partition(": ")
    return Clause(predicate, value)


def hash_clauses(clauses: tuple[Clause, ...]) -> str:
    h = hashlib.sha1()
    for clause in clauses:
        h.update(clause.predicate.encode())
        h.update(b"\x00")
        h.update(clause.value.encode())
        h.update(b"\x00")
    return h.hexdigest()


def clause_delta(
    before: tuple[Clause, ...], after: tuple[Clause, ...]
) -> tuple[list[Clause], list[Clause]]:
    """Return ``(added, removed)`` clauses between two states of a term.

    Clauses are compared as a multiset, so an edited single-valued field (a new
    ``name``) and a swapped multi-valued entry (one synonym replaced by another)
    both surface as a removal paired with an addition.
    """
    b, a = Counter(before), Counter(after)
    added = list((a - b).elements())
    removed = list((b - a).elements())
    return added, removed


def parse_terms(data: bytes, threads: int = 1) -> dict[str, TermState]:
    """Parse one OBO document into ``{mondo_id: TermState}`` for its term frames.

    Non-term frames (typedefs, instances) and the header are ignored — the index
    is about ontology terms.

    ``threads=1`` (the default) uses fastobo's single-threaded parser: it avoids
    CPU oversubscription when many builds run in parallel, and sidesteps the
    threaded parser's habit of *panicking* (rather than raising) on a few
    malformed historical clauses. Callers still guard against parse failure.
    """
    doc = fastobo.load(io.BytesIO(data), threads=threads)
    result: dict[str, TermState] = {}
    for frame in doc:
        if isinstance(frame, fastobo.term.TermFrame):
            mondo_id = str(frame.id)
            clauses = clauses_of(frame)
            result[mondo_id] = TermState(mondo_id, clauses, hash_clauses(clauses))
    return result
