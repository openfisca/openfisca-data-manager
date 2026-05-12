from pathlib import Path

import pytest
import yaml

from openfisca_data_manager.scripts.migrate_config import migrate_config


def write_config(directory: Path, collections_directory: Path | None = None) -> None:
    collections_directory = collections_directory or directory
    (directory / "config.ini").write_text(
        f"""
[collections]
collections_directory = {collections_directory}
fake = {collections_directory / "fake.json"}

[data]
output_directory = {directory / "openfisca-survey-manager-output"}
tmp_directory = {directory / "openfisca-survey-manager-tmp"}
""".strip()
    )
    (collections_directory / "fake.json").write_text('{"name": "fake", "surveys": {}}')


def write_collection_json(directory: Path) -> None:
    (directory / "fake.json").write_text(
        """
{
  "name": "fake",
  "label": "Fake collection",
  "surveys": {
    "fake_2020": {
      "name": "fake_2020",
      "label": "Fake 2020",
      "parquet_file_path": "/tmp/openfisca-survey-manager/fake_2020",
      "informations": {
        "parquet_files": ["/tmp/openfisca-survey-manager/raw/person.parquet"]
      },
      "tables": {
        "person": {
          "source_format": "parquet",
          "variables": ["person_id"],
          "parquet_file": "/tmp/openfisca-survey-manager/fake_2020/person.parquet"
        }
      }
    }
  }
}
""".strip()
    )


def test_migrate_config_copies_ini_files(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)
    (source / "raw_data.ini").write_text("[fake]\n2020 = /data/fake\n")

    result = migrate_config(source=source, target=target)

    assert result.target == target
    assert (target / "config.ini").exists()
    assert (target / "raw_data.ini").read_text() == "[fake]\n2020 = /data/fake\n"


def test_migrate_config_dry_run_does_not_write(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)

    result = migrate_config(source=source, target=target, dry_run=True)

    assert result.dry_run is True
    assert not target.exists()


def test_migrate_config_rewrites_paths_when_requested(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)

    migrate_config(source=source, target=target, rewrite_paths=True)

    assert "openfisca-data-manager" in (target / "config.ini").read_text()
    assert "openfisca-survey-manager" not in (target / "config.ini").read_text()
    assert (target / "fake.json").exists()


def test_migrate_config_backs_up_existing_target_and_requires_force(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    target.mkdir()
    write_config(source)
    (target / "config.ini").write_text("existing")

    with pytest.raises(FileExistsError):
        migrate_config(source=source, target=target)

    assert list(tmp_path.glob("openfisca-data-manager.backup-*"))


def test_migrate_config_force_overwrites_existing_target(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    target.mkdir()
    write_config(source)
    (target / "config.ini").write_text("existing")

    migrate_config(source=source, target=target, force=True)

    assert "[collections]" in (target / "config.ini").read_text()


def test_migrate_config_validates_required_sections(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    (source / "config.ini").write_text("[collections]\ncollections_directory = None\n")

    with pytest.raises(ValueError, match="Missing section"):
        migrate_config(source=source, target=target, dry_run=True)


def test_migrate_config_writes_yaml_from_ini_files(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)
    (source / "raw_data.ini").write_text("[fake]\n2020 = /raw/fake/2020\n")

    migrate_config(source=source, target=target, output_format="yaml")

    data = yaml.safe_load((target / "data-manager.yaml").read_text())
    assert data["version"] == 1
    assert data["storage"]["collections_directory"] == str(source)
    assert data["collections"]["fake"]["metadata"].endswith("fake.json")
    assert data["collections"]["fake"]["raw_surveys"] == {"2020": "/raw/fake/2020"}
    assert not (target / "config.ini").exists()


def test_migrate_config_writes_yaml_with_rewritten_paths(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)

    migrate_config(source=source, target=target, rewrite_paths=True, output_format="yaml")

    data = yaml.safe_load((target / "data-manager.yaml").read_text())
    assert "openfisca-data-manager" in data["storage"]["output_directory"]
    assert data["collections"]["fake"]["metadata"].endswith("fake.json")


def test_migrate_config_yaml_without_collections_keeps_json_metadata(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)

    migrate_config(source=source, target=target, output_format="yaml")

    data = yaml.safe_load((target / "data-manager.yaml").read_text())
    assert data["collections"]["fake"]["metadata"].endswith("fake.json")
    assert not (target / "fake.yaml").exists()


def test_migrate_config_yaml_with_collections_converts_json_metadata(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)
    write_collection_json(source)

    migrate_config(source=source, target=target, output_format="yaml", convert_collections=True)

    data = yaml.safe_load((target / "data-manager.yaml").read_text())
    collection_data = yaml.safe_load((target / "collections" / "fake.yaml").read_text())
    assert data["collections"]["fake"]["metadata"].endswith("fake.yaml")
    assert collection_data["version"] == 1
    assert collection_data["name"] == "fake"
    assert collection_data["surveys"]["fake_2020"]["label"] == "Fake 2020"
    assert collection_data["surveys"]["fake_2020"]["tables"]["person"]["variables"] == ["person_id"]


def test_migrate_config_yaml_with_collections_rewrites_nested_paths(tmp_path):
    source = tmp_path / "openfisca-survey-manager"
    target = tmp_path / "openfisca-data-manager"
    source.mkdir()
    write_config(source)
    write_collection_json(source)

    migrate_config(
        source=source,
        target=target,
        rewrite_paths=True,
        output_format="yaml",
        convert_collections=True,
    )

    collection_text = (target / "collections" / "fake.yaml").read_text()
    assert "openfisca-data-manager" in collection_text
    assert "openfisca-survey-manager" not in collection_text
