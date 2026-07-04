"""Tests for obohog.toml loading and source resolution."""

from pathlib import Path

import pytest

from obohog.config import Config, ConfigError, SourceConfig, load_config


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_load_config_minimal(tmp_path: Path):
    cfg_path = _write(
        tmp_path / "obohog.toml",
        """
        [source.mondo]
        repo = "https://github.com/monarch-initiative/mondo"
        file = "src/ontology/mondo-edit.obo"
        """,
    )
    cfg = load_config(cfg_path)
    assert cfg.path == cfg_path
    assert cfg.storage == Path("data")
    assert set(cfg.sources) == {"mondo"}
    source = cfg.sources["mondo"]
    assert source.name == "mondo"
    assert source.repo == "https://github.com/monarch-initiative/mondo"
    assert source.file == "src/ontology/mondo-edit.obo"
    # Default per-source path convention: {storage}/{name}/{clone,db}.
    assert source.clone_dir == Path("data/mondo/clone")
    assert source.db_dir == Path("data/mondo/db")


def test_load_config_explicit_storage_and_paths(tmp_path: Path):
    cfg_path = _write(
        tmp_path / "obohog.toml",
        """
        storage = "/tmp/obohog-data"

        [source.pato]
        repo = "https://github.com/pato-ontology/pato"
        file = "src/ontology/pato-edit.obo"
        clone_dir = "/big/disk/pato/clone"
        db_dir = "/big/disk/pato/db"
        """,
    )
    cfg = load_config(cfg_path)
    assert cfg.storage == Path("/tmp/obohog-data")
    pato = cfg.sources["pato"]
    assert pato.clone_dir == Path("/big/disk/pato/clone")
    assert pato.db_dir == Path("/big/disk/pato/db")


def test_load_config_multiple_sources(tmp_path: Path):
    cfg_path = _write(
        tmp_path / "obohog.toml",
        """
        [source.mondo]
        repo = "https://github.com/monarch-initiative/mondo"
        file = "src/ontology/mondo-edit.obo"

        [source.pato]
        repo = "https://github.com/pato-ontology/pato"
        file = "src/ontology/pato-edit.obo"
        """,
    )
    cfg = load_config(cfg_path)
    assert set(cfg.sources) == {"mondo", "pato"}


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="No obohog config found"):
        load_config(tmp_path / "does-not-exist.toml")


def test_load_config_malformed_toml(tmp_path: Path):
    cfg_path = _write(tmp_path / "obohog.toml", "[source.mondo\nunterminated")
    with pytest.raises(ConfigError, match="Malformed TOML"):
        load_config(cfg_path)


def test_load_config_missing_required_field(tmp_path: Path):
    cfg_path = _write(
        tmp_path / "obohog.toml",
        """
        [source.mondo]
        repo = "https://example/mondo"
        """,  # missing "file"
    )
    with pytest.raises(ConfigError, match="missing required field 'file'"):
        load_config(cfg_path)


def test_get_source_unknown_lists_available(tmp_path: Path):
    cfg_path = _write(
        tmp_path / "obohog.toml",
        """
        [source.mondo]
        repo = "https://example/mondo"
        file = "a.obo"

        [source.pato]
        repo = "https://example/pato"
        file = "b.obo"
        """,
    )
    cfg = load_config(cfg_path)
    with pytest.raises(ConfigError, match=r"No source named 'go' .* Available sources: mondo, pato"):
        cfg.get_source("go")


def test_get_source_empty_config_error_message(tmp_path: Path):
    cfg_path = _write(tmp_path / "obohog.toml", "")
    cfg = load_config(cfg_path)
    with pytest.raises(ConfigError, match=r"Available sources: \(none\)"):
        cfg.get_source("mondo")
