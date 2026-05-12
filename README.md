# OpenFisca Data Manager

Survey and administrative data access tools extracted from OpenFisca Survey Manager.

This package contains the data-management layer: configuration, survey collections, survey tables, readers, writers and data-cleaning helpers.

## Configuration

The target YAML configuration format is specified in [docs/configuration-v1.md](docs/configuration-v1.md).

## Development

```shell
uv sync --extra dev
uv run pytest
uv run ruff check
```
