"""Configuration for obohist: which OBO ontologies to track, and where.

An ``obohist.toml`` file at the project root declares one or more ontology
*sources*. Each source pins a git repo, the OBO file within it, and (later)
per-source options. The `--config <path>` CLI flag overrides the default
lookup; otherwise we read ``./obohist.toml`` from the current working
directory. There is no global / XDG search yet.

Example (also shipped as ``obohist.toml.example``)::

    storage = "./data"

    [source.mondo]
    repo = "https://github.com/monarch-initiative/mondo"
    file = "src/ontology/mondo-edit.obo"

    [source.pato]
    repo = "https://github.com/pato-ontology/pato"
    file = "src/ontology/pato-edit.obo"

Per-source paths (``clone_dir``, ``db_dir``) default to
``{storage}/{name}/clone`` and ``{storage}/{name}/db`` respectively, and can
be overridden by explicit fields in the source table.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_NAME = "obohist.toml"
DEFAULT_STORAGE_DIR = Path("./data")


class ConfigError(Exception):
    """Raised for missing / malformed config files or unknown source lookups."""


@dataclass(frozen=True)
class SourceConfig:
    """One ontology's configuration: git source + local storage paths."""

    name: str
    repo: str
    file: str  # path to the OBO file within the repo
    clone_dir: Path
    db_dir: Path


@dataclass(frozen=True)
class Config:
    """The parsed obohist.toml — top-level storage root plus a source table."""

    path: Path  # the config file this was loaded from
    storage: Path
    sources: dict[str, SourceConfig] = field(default_factory=dict)

    def get_source(self, name: str) -> SourceConfig:
        """Look up a source by name; raise a helpful error if it doesn't exist."""
        source = self.sources.get(name)
        if source is not None:
            return source
        available = ", ".join(sorted(self.sources)) or "(none)"
        raise ConfigError(
            f"No source named {name!r} configured in {self.path}. "
            f"Available sources: {available}."
        )


def load_config(path: Path | None = None) -> Config:
    """Load and validate an obohist config file.

    ``path`` may be an explicit path (from ``--config``), or ``None`` — in
    which case we look for ``obohist.toml`` in the current working directory.
    Raises :class:`ConfigError` with a helpful message on any failure.
    """
    resolved = _resolve_config_path(path)
    try:
        data = tomllib.loads(resolved.read_text())
    except FileNotFoundError:
        raise ConfigError(
            f"No obohist config found at {resolved}. "
            f"Create one (see obohist.toml.example) or pass --config <path>."
        )
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"Malformed TOML at {resolved}: {err}")
    return _parse_config(resolved, data)


def _resolve_config_path(path: Path | None) -> Path:
    if path is not None:
        return path
    return Path.cwd() / DEFAULT_CONFIG_NAME


def _parse_config(path: Path, data: dict) -> Config:
    storage = Path(data.get("storage", DEFAULT_STORAGE_DIR)).expanduser()
    raw_sources = data.get("source", {})
    if not isinstance(raw_sources, dict):
        raise ConfigError(f"'source' must be a table in {path}, got {type(raw_sources).__name__}")
    sources: dict[str, SourceConfig] = {}
    for name, section in raw_sources.items():
        if not isinstance(section, dict):
            raise ConfigError(
                f"'source.{name}' must be a table in {path}, got "
                f"{type(section).__name__}"
            )
        sources[name] = _parse_source(name, section, storage, path)
    return Config(path=path, storage=storage, sources=sources)


def _parse_source(name: str, section: dict, storage: Path, path: Path) -> SourceConfig:
    for required in ("repo", "file"):
        if required not in section:
            raise ConfigError(
                f"source.{name} in {path} is missing required field {required!r}"
            )
    default_root = storage / name
    clone_dir = Path(section.get("clone_dir", default_root / "clone")).expanduser()
    db_dir = Path(section.get("db_dir", default_root / "db")).expanduser()
    return SourceConfig(
        name=name,
        repo=str(section["repo"]),
        file=str(section["file"]),
        clone_dir=clone_dir,
        db_dir=db_dir,
    )
