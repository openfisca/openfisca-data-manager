# Migrate From OpenFisca Survey Manager

This guide explains how to migrate an existing OpenFisca Survey Manager configuration to OpenFisca Data Manager's YAML configuration format.

The migration keeps the original files. It creates a new target directory and, when requested, converts collection metadata JSON files to YAML.

## Legacy Inputs

A typical Survey Manager configuration directory contains:

```text
~/.config/openfisca-survey-manager/
├── config.ini
└── raw_data.ini
```

`config.ini` points to collection metadata files, usually JSON:

```ini
[collections]
collections_directory = /path/to/collections
erfs = /path/to/collections/erfs.json

[data]
output_directory = /path/to/data
tmp_directory = /path/to/tmp
```

`raw_data.ini` points to raw survey directories:

```ini
[erfs]
2019 = /raw/erfs/2019
2020 = /raw/erfs/2020
```

## Recommended Migration

Run a dry run first:

```shell
migrate-survey-manager-config \
  --source ~/.config/openfisca-survey-manager \
  --target ~/.config/openfisca-data-manager \
  --format yaml \
  --collections \
  --dry-run
```

Then run the migration:

```shell
migrate-survey-manager-config \
  --source ~/.config/openfisca-survey-manager \
  --target ~/.config/openfisca-data-manager \
  --format yaml \
  --collections
```

Use `--rewrite-paths` only if your paths explicitly contain `openfisca-survey-manager` and you want them rewritten to `openfisca-data-manager`:

```shell
migrate-survey-manager-config \
  --source ~/.config/openfisca-survey-manager \
  --target ~/.config/openfisca-data-manager \
  --format yaml \
  --collections \
  --rewrite-paths
```

If the target already exists, the command creates a backup. Use `--force` to overwrite target files:

```shell
migrate-survey-manager-config \
  --source ~/.config/openfisca-survey-manager \
  --target ~/.config/openfisca-data-manager \
  --format yaml \
  --collections \
  --force
```

## Generated Files

With `--format yaml --collections`, the target directory contains:

```text
~/.config/openfisca-data-manager/
├── data-manager.yaml
└── collections/
    └── erfs.yaml
```

`data-manager.yaml` contains global storage settings and raw survey paths:

```yaml
version: 1
storage:
  collections_directory: /path/to/collections
  output_directory: /path/to/data
  tmp_directory: /path/to/tmp
collections:
  erfs:
    metadata: /home/user/.config/openfisca-data-manager/collections/erfs.yaml
    raw_surveys:
      "2019": /raw/erfs/2019
      "2020": /raw/erfs/2020
```

`collections/erfs.yaml` contains collection, survey and table metadata converted from the legacy collection JSON.

## Build From YAML

Once migrated, build a collection directly from the YAML configuration:

```shell
build-collection \
  --collection erfs \
  --path ~/.config/openfisca-data-manager \
  --replace-metadata \
  --replace-data \
  --parquet
```

When `data-manager.yaml` exists, `build-collection` reads raw survey paths from `collections.<name>.raw_surveys`. If no YAML file exists, it keeps using `raw_data.ini`.

## Supported Transitions

OpenFisca Data Manager currently supports these combinations:

- INI global config + JSON collection metadata.
- YAML global config + JSON collection metadata.
- YAML global config + YAML collection metadata.

The canonical target is YAML global config + YAML collection metadata.

## Safety Notes

- The migration command never deletes legacy files.
- Existing target directories are backed up before changes.
- `--rewrite-paths` is textual and should be reviewed before use on production paths.
- Absolute data paths are preserved unless `--rewrite-paths` changes their text.
