"""Configuration model (Config class from config.ini)."""

from __future__ import annotations

import configparser
import logging
from pathlib import Path
from typing import Any, Optional, Union

import yaml

log = logging.getLogger(__name__)


class Config(configparser.ConfigParser):
    """Parser for config.ini; used by SurveyCollection and build scripts."""

    config_ini: Optional[Path] = None
    yaml_config: Optional[dict[str, Any]] = None

    def __init__(
        self,
        config_files_directory: Optional[Union[Path, str]] = None,
    ) -> None:
        configparser.ConfigParser.__init__(self)
        if config_files_directory is not None:
            config_files_directory = Path(config_files_directory)
            yaml_config = config_files_directory / "data-manager.yaml"
            config_ini = config_files_directory / "config.ini"
            if yaml_config.exists():
                self.config_ini = yaml_config
                self._read_yaml_config(yaml_config)
                log.debug("Loaded config from %s", yaml_config)
            else:
                assert config_ini.exists(), f"{config_ini} is not a valid path"
                self.config_ini = config_ini
                self.read([config_ini])
                log.debug("Loaded config from %s", config_ini)

    def save(self) -> None:
        assert self.config_ini, "configuration file path is not defined"
        assert self.config_ini.exists()
        if self.config_ini.suffix in {".yaml", ".yml"}:
            self._write_yaml_config(self.config_ini)
        else:
            config_file = self.config_ini.open("w")
            self.write(config_file)
            config_file.close()
        log.debug("Saved config to %s", self.config_ini)

    def _read_yaml_config(self, yaml_config_path: Path) -> None:
        self.yaml_config = yaml.safe_load(yaml_config_path.read_text()) or {}
        storage = self.yaml_config.get("storage", {})
        collections = self.yaml_config.get("collections", {})

        self["collections"] = {}
        self["data"] = {}
        for option in ("collections_directory",):
            if option in storage:
                self.set("collections", option, str(_resolve_path(storage[option], base_dir=yaml_config_path.parent)))
        for option in ("output_directory", "tmp_directory"):
            if option in storage:
                self.set("data", option, str(_resolve_path(storage[option], base_dir=yaml_config_path.parent)))

        collections_directory = Path(
            self.get("collections", "collections_directory", fallback=yaml_config_path.parent)
        )
        for collection_name, collection in collections.items():
            metadata_path = collection.get("metadata")
            if metadata_path is None:
                metadata_path = collections_directory / f"{collection_name}.yaml"
            else:
                metadata_path = _resolve_metadata_path(
                    metadata_path,
                    collections_directory=collections_directory,
                    config_directory=yaml_config_path.parent,
                )
            self.set("collections", collection_name, str(metadata_path))

    def _write_yaml_config(self, yaml_config_path: Path) -> None:
        yaml_config = self.yaml_config.copy() if self.yaml_config is not None else {"version": 1}
        storage = yaml_config.setdefault("storage", {})
        collections = yaml_config.setdefault("collections", {})

        storage["collections_directory"] = self.get("collections", "collections_directory")
        storage["output_directory"] = self.get("data", "output_directory")
        storage["tmp_directory"] = self.get("data", "tmp_directory")

        for collection_name, metadata_path in self.items("collections"):
            if collection_name == "collections_directory":
                continue
            collections.setdefault(collection_name, {})["metadata"] = metadata_path

        yaml_config_path.write_text(yaml.safe_dump(yaml_config, sort_keys=False, allow_unicode=True))

    def get_collection_raw_surveys(self, collection_name: str) -> dict[str, str]:
        if self.yaml_config is None:
            return {}
        collection = self.yaml_config.get("collections", {}).get(collection_name, {})
        raw_surveys = collection.get("raw_surveys", {})
        return {
            str(survey_suffix): _raw_survey_path(survey_definition)
            for survey_suffix, survey_definition in raw_surveys.items()
        }

    def get_collection_defaults(self, collection_name: str) -> dict[str, Any]:
        if self.yaml_config is None:
            return {}
        defaults = dict(self.yaml_config.get("defaults", {}))
        collection = self.yaml_config.get("collections", {}).get(collection_name, {})
        for option in ("source_format", "store_format", "categorical_strategy"):
            if option in collection:
                defaults[option] = collection[option]
        return defaults


def _resolve_path(path: Any, *, base_dir: Path) -> Path:
    path = Path(str(path)).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _resolve_metadata_path(path: Any, *, collections_directory: Path, config_directory: Path) -> Path:
    path = Path(str(path)).expanduser()
    if path.is_absolute():
        return path
    if collections_directory.is_absolute():
        return collections_directory / path
    return config_directory / collections_directory / path


def _raw_survey_path(survey_definition: Any) -> str:
    if isinstance(survey_definition, dict):
        return str(survey_definition.get("path"))
    return str(survey_definition)
