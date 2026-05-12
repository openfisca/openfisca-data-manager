"""Migrate OpenFisca Survey Manager config files to OpenFisca Data Manager."""

from __future__ import annotations

import argparse
import configparser
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml
from xdg import BaseDirectory

LEGACY_APP_NAME = "openfisca-survey-manager"
DATA_MANAGER_APP_NAME = "openfisca-data-manager"
CONFIG_FILES = ("config.ini", "raw_data.ini")
REQUIRED_CONFIG_OPTIONS = {
    "collections": ("collections_directory",),
    "data": ("output_directory", "tmp_directory"),
}


@dataclass(frozen=True)
class MigrationResult:
    source: Path
    target: Path
    copied_files: tuple[Path, ...]
    backup_directory: Path | None = None
    dry_run: bool = False


def default_source_directory() -> Path:
    return Path(BaseDirectory.xdg_config_home) / LEGACY_APP_NAME


def default_target_directory() -> Path:
    return Path(BaseDirectory.xdg_config_home) / DATA_MANAGER_APP_NAME


def migrate_config(
    *,
    source: Path | str | None = None,
    target: Path | str | None = None,
    rewrite_paths: bool = False,
    dry_run: bool = False,
    force: bool = False,
    output_format: str = "ini",
    convert_collections: bool = False,
) -> MigrationResult:
    if output_format not in {"ini", "yaml"}:
        raise ValueError("output_format must be 'ini' or 'yaml'")

    source_dir = Path(source) if source is not None else default_source_directory()
    target_dir = Path(target) if target is not None else default_target_directory()
    source_config_files = [source_dir / file_name for file_name in CONFIG_FILES if (source_dir / file_name).exists()]
    copied_files = source_config_files.copy()

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source config directory does not exist: {source_dir}")
    if not source_config_files:
        raise FileNotFoundError(f"No config files found in source directory: {source_dir}")
    if source_dir.resolve() == target_dir.resolve():
        raise ValueError("Source and target config directories must be different")

    if dry_run:
        _validate_config_file(source_dir / "config.ini", source_dir=source_dir)
        return MigrationResult(source_dir, target_dir, tuple(copied_files), dry_run=True)

    backup_dir = _backup_existing_target(target_dir) if target_dir.exists() else None
    target_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "yaml":
        target_file = target_dir / "data-manager.yaml"
        _assert_can_write(target_file, force=force, backup_dir=backup_dir)
        yaml_config = _build_yaml_config(
            source_dir=source_dir,
            target_dir=target_dir,
            rewrite_paths=rewrite_paths,
            convert_collections=convert_collections,
        )
        target_file.write_text(yaml.safe_dump(yaml_config, sort_keys=False, allow_unicode=True))
        if convert_collections:
            copied_files.extend(
                _convert_collection_files(
                    source_dir=source_dir,
                    target_dir=target_dir,
                    yaml_config=yaml_config,
                    rewrite_paths=rewrite_paths,
                    force=force,
                    backup_dir=backup_dir,
                )
            )
    else:
        for source_file in copied_files:
            target_file = target_dir / source_file.name
            _assert_can_write(target_file, force=force, backup_dir=backup_dir)
            _copy_config_file(source_file, target_file, rewrite_paths=rewrite_paths)

        copied_files.extend(
            _copy_collection_files(source_dir=source_dir, target_dir=target_dir, rewrite_paths=rewrite_paths)
        )

    if output_format == "ini":
        _validate_config_file(target_dir / "config.ini", source_dir=target_dir)
    return MigrationResult(source_dir, target_dir, tuple(copied_files), backup_directory=backup_dir)


def _assert_can_write(target_file: Path, *, force: bool, backup_dir: Path | None) -> None:
    if target_file.exists() and not force:
        raise FileExistsError(
            f"Target file already exists: {target_file}. Use --force to overwrite. "
            f"A backup was created at: {backup_dir}"
        )


def _backup_existing_target(target_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = target_dir.with_name(f"{target_dir.name}.backup-{timestamp}")
    suffix = 1
    while backup_dir.exists():
        backup_dir = target_dir.with_name(f"{target_dir.name}.backup-{timestamp}-{suffix}")
        suffix += 1
    shutil.copytree(target_dir, backup_dir)
    return backup_dir


def _copy_config_file(source_file: Path, target_file: Path, *, rewrite_paths: bool) -> None:
    if rewrite_paths:
        content = source_file.read_text()
        content = content.replace(LEGACY_APP_NAME, DATA_MANAGER_APP_NAME)
        target_file.write_text(content)
    else:
        shutil.copy2(source_file, target_file)


def _copy_collection_files(*, source_dir: Path, target_dir: Path, rewrite_paths: bool) -> list[Path]:
    source_config = source_dir / "config.ini"
    target_config = target_dir / "config.ini"
    if not source_config.exists() or not target_config.exists():
        return []

    source_parser = configparser.ConfigParser()
    target_parser = configparser.ConfigParser()
    source_parser.read(source_config)
    target_parser.read(target_config)
    if not source_parser.has_section("collections") or not target_parser.has_section("collections"):
        return []

    copied_files = []
    for option, source_value in source_parser.items("collections"):
        if option == "collections_directory" or source_value.strip().lower() == "none":
            continue
        target_value = target_parser.get("collections", option, fallback=source_value)
        source_path = _resolve_config_path(source_value, base_dir=source_dir)
        target_path = _resolve_config_path(target_value, base_dir=target_dir)
        if not source_path.is_file() or target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if rewrite_paths:
            content = source_path.read_text().replace(LEGACY_APP_NAME, DATA_MANAGER_APP_NAME)
            target_path.write_text(content)
        else:
            shutil.copy2(source_path, target_path)
        copied_files.append(source_path)
    return copied_files


def _build_yaml_config(
    *,
    source_dir: Path,
    target_dir: Path,
    rewrite_paths: bool,
    convert_collections: bool,
) -> dict[str, Any]:
    config_parser = _read_ini_file(source_dir / "config.ini")
    raw_data_parser = _read_ini_file(source_dir / "raw_data.ini")
    _validate_config_file(source_dir / "config.ini", source_dir=source_dir)

    collections_directory = _optional_rewrite(
        config_parser.get("collections", "collections_directory"), rewrite_paths=rewrite_paths
    )
    output_directory = _optional_rewrite(config_parser.get("data", "output_directory"), rewrite_paths=rewrite_paths)
    tmp_directory = _optional_rewrite(config_parser.get("data", "tmp_directory"), rewrite_paths=rewrite_paths)
    yaml_config: dict[str, Any] = {
        "version": 1,
        "storage": {
            "collections_directory": collections_directory,
            "output_directory": output_directory,
            "tmp_directory": tmp_directory,
        },
        "collections": {},
    }

    collections = yaml_config["collections"]
    for collection_name, metadata_path in config_parser.items("collections"):
        if collection_name == "collections_directory" or metadata_path.strip().lower() == "none":
            continue
        if convert_collections:
            metadata_path = str(target_dir / "collections" / f"{collection_name}.yaml")
        else:
            metadata_path = _optional_rewrite(metadata_path, rewrite_paths=rewrite_paths)
        collections[collection_name] = {"metadata": metadata_path}

    for collection_name in raw_data_parser.sections():
        collection = collections.setdefault(collection_name, {})
        raw_surveys = {}
        for survey_suffix, raw_path in raw_data_parser.items(collection_name):
            raw_surveys[str(survey_suffix)] = _optional_rewrite(raw_path, rewrite_paths=rewrite_paths)
        if raw_surveys:
            collection["raw_surveys"] = raw_surveys

    return yaml_config


def _convert_collection_files(
    *,
    source_dir: Path,
    target_dir: Path,
    yaml_config: dict[str, Any],
    rewrite_paths: bool,
    force: bool,
    backup_dir: Path | None,
) -> list[Path]:
    config_parser = _read_ini_file(source_dir / "config.ini")
    if not config_parser.has_section("collections"):
        return []

    copied_files = []
    for collection_name, source_metadata in config_parser.items("collections"):
        if collection_name == "collections_directory" or source_metadata.strip().lower() == "none":
            continue

        source_path = _resolve_config_path(source_metadata, base_dir=source_dir)
        if not source_path.is_file():
            continue

        target_metadata = yaml_config["collections"][collection_name]["metadata"]
        target_path = _resolve_config_path(target_metadata, base_dir=target_dir)
        _assert_can_write(target_path, force=force, backup_dir=backup_dir)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            yaml.safe_dump(
                _convert_collection_json(source_path, rewrite_paths=rewrite_paths),
                sort_keys=False,
                allow_unicode=True,
            )
        )
        copied_files.append(source_path)
    return copied_files


def _convert_collection_json(source_path: Path, *, rewrite_paths: bool) -> dict[str, Any]:
    data = json.loads(source_path.read_text())
    converted: dict[str, Any] = {
        "version": 1,
        "name": data["name"],
    }
    if data.get("label") is not None:
        converted["label"] = data["label"]

    converted_surveys = {}
    for survey_name, survey_data in data.get("surveys", {}).items():
        converted_surveys[survey_name] = _convert_survey_json(survey_data, rewrite_paths=rewrite_paths)
    converted["surveys"] = converted_surveys
    return converted


def _convert_survey_json(survey_data: dict[str, Any], *, rewrite_paths: bool) -> dict[str, Any]:
    converted = {}
    for key in ("label", "hdf5_file_path", "parquet_file_path"):
        value = survey_data.get(key)
        if value is not None:
            converted[key] = _rewrite_value(value, rewrite_paths=rewrite_paths)

    informations = survey_data.get("informations") or {}
    for key, value in informations.items():
        converted[key] = _rewrite_value(value, rewrite_paths=rewrite_paths)

    tables = survey_data.get("tables") or {}
    if tables:
        converted["tables"] = _rewrite_value(tables, rewrite_paths=rewrite_paths)
    return converted


def _rewrite_value(value: Any, *, rewrite_paths: bool) -> Any:
    if isinstance(value, str):
        return _optional_rewrite(value, rewrite_paths=rewrite_paths)
    if isinstance(value, list):
        return [_rewrite_value(item, rewrite_paths=rewrite_paths) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_value(item, rewrite_paths=rewrite_paths) for key, item in value.items()}
    return value


def _read_ini_file(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path)
    return parser


def _optional_rewrite(value: str, *, rewrite_paths: bool) -> str:
    if not rewrite_paths:
        return value
    return value.replace(LEGACY_APP_NAME, DATA_MANAGER_APP_NAME)


def _validate_config_file(config_file: Path, *, source_dir: Path) -> None:
    if not config_file.exists():
        return

    parser = configparser.ConfigParser()
    parser.read(config_file)
    for section, options in REQUIRED_CONFIG_OPTIONS.items():
        if not parser.has_section(section):
            raise ValueError(f"Missing section [{section}] in {config_file}")
        for option in options:
            if not parser.has_option(section, option):
                raise ValueError(f"Missing option {section}.{option} in {config_file}")

    _validate_collection_paths(parser, config_file=config_file, source_dir=source_dir)


def _validate_collection_paths(parser: configparser.ConfigParser, *, config_file: Path, source_dir: Path) -> None:
    for option, value in parser.items("collections"):
        if option == "collections_directory" or value.strip().lower() == "none":
            continue
        collection_path = _resolve_config_path(value, base_dir=source_dir)
        if not collection_path.exists():
            raise FileNotFoundError(f"Collection path from {config_file} does not exist: {collection_path}")


def _resolve_config_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _format_result(result: MigrationResult) -> Iterable[str]:
    action = "Would copy" if result.dry_run else "Copied"
    yield f"Source: {result.source}"
    yield f"Target: {result.target}"
    for file_path in result.copied_files:
        yield f"{action}: {file_path.name}"
    if result.backup_directory is not None:
        yield f"Backup: {result.backup_directory}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=default_source_directory())
    parser.add_argument("--target", type=Path, default=default_target_directory())
    parser.add_argument("--rewrite-paths", action="store_true")
    parser.add_argument("--format", choices=("ini", "yaml"), default="ini", dest="output_format")
    parser.add_argument("--collections", action="store_true", help="Convert referenced collection JSON files to YAML")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = migrate_config(
        source=args.source,
        target=args.target,
        rewrite_paths=args.rewrite_paths,
        dry_run=args.dry_run,
        force=args.force,
        output_format=args.output_format,
        convert_collections=args.collections,
    )
    for line in _format_result(result):
        sys.stdout.write(f"{line}\n")


if __name__ == "__main__":
    main()
