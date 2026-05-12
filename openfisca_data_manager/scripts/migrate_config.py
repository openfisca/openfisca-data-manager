"""Migrate OpenFisca Survey Manager config files to OpenFisca Data Manager."""

from __future__ import annotations

import argparse
import configparser
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

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
) -> MigrationResult:
    source_dir = Path(source) if source is not None else default_source_directory()
    target_dir = Path(target) if target is not None else default_target_directory()
    copied_files = [source_dir / file_name for file_name in CONFIG_FILES if (source_dir / file_name).exists()]

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source config directory does not exist: {source_dir}")
    if not copied_files:
        raise FileNotFoundError(f"No config files found in source directory: {source_dir}")
    if source_dir.resolve() == target_dir.resolve():
        raise ValueError("Source and target config directories must be different")

    if dry_run:
        _validate_config_file(source_dir / "config.ini", source_dir=source_dir)
        return MigrationResult(source_dir, target_dir, tuple(copied_files), dry_run=True)

    backup_dir = _backup_existing_target(target_dir) if target_dir.exists() else None
    target_dir.mkdir(parents=True, exist_ok=True)

    for source_file in copied_files:
        target_file = target_dir / source_file.name
        if target_file.exists() and not force:
            raise FileExistsError(
                f"Target file already exists: {target_file}. Use --force to overwrite. "
                f"A backup was created at: {backup_dir}"
            )
        _copy_config_file(source_file, target_file, rewrite_paths=rewrite_paths)

    copied_files.extend(
        _copy_collection_files(source_dir=source_dir, target_dir=target_dir, rewrite_paths=rewrite_paths)
    )

    _validate_config_file(target_dir / "config.ini", source_dir=target_dir)
    return MigrationResult(source_dir, target_dir, tuple(copied_files), backup_directory=backup_dir)


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
    )
    for line in _format_result(result):
        sys.stdout.write(f"{line}\n")


if __name__ == "__main__":
    main()
