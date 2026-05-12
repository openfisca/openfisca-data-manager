import json

import yaml

from openfisca_data_manager.config.models import Config
from openfisca_data_manager.core.dataset import SurveyCollection


def test_config_loads_data_manager_yaml(tmp_path):
    collections_dir = tmp_path / "collections"
    collections_dir.mkdir()
    metadata = collections_dir / "fake.json"
    metadata.write_text('{"name": "fake", "surveys": {}}')
    (tmp_path / "data-manager.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "storage": {
                    "collections_directory": str(collections_dir),
                    "output_directory": str(tmp_path / "output"),
                    "tmp_directory": str(tmp_path / "tmp"),
                },
                "collections": {
                    "fake": {
                        "metadata": "fake.json",
                    }
                },
            },
            sort_keys=False,
        )
    )

    config = Config(tmp_path)

    assert config.get("collections", "collections_directory") == str(collections_dir)
    assert config.get("collections", "fake") == str(metadata)
    assert config.get("data", "output_directory") == str(tmp_path / "output")


def test_survey_collection_loads_yaml_global_with_json_metadata(tmp_path):
    metadata = tmp_path / "fake.json"
    metadata.write_text(json.dumps({"name": "fake", "surveys": {}}))
    (tmp_path / "data-manager.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "storage": {
                    "collections_directory": str(tmp_path),
                    "output_directory": str(tmp_path / "output"),
                    "tmp_directory": str(tmp_path / "tmp"),
                },
                "collections": {"fake": {"metadata": str(metadata)}},
            },
            sort_keys=False,
        )
    )

    collection = SurveyCollection.load(collection="fake", config_files_directory=tmp_path)

    assert collection.name == "fake"
    assert collection.surveys == []


def test_survey_collection_loads_yaml_global_with_yaml_metadata(tmp_path):
    metadata = tmp_path / "collections" / "fake.yaml"
    metadata.parent.mkdir()
    metadata.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "name": "fake",
                "surveys": {
                    "fake_2020": {
                        "label": "Fake 2020",
                        "parquet_file_path": str(tmp_path / "data" / "fake_2020"),
                        "tables": {
                            "person": {
                                "source_format": "parquet",
                                "variables": ["person_id"],
                            }
                        },
                    }
                },
            },
            sort_keys=False,
        )
    )
    (tmp_path / "data-manager.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "storage": {
                    "collections_directory": str(tmp_path / "collections"),
                    "output_directory": str(tmp_path / "output"),
                    "tmp_directory": str(tmp_path / "tmp"),
                },
                "collections": {"fake": {"metadata": "fake.yaml"}},
            },
            sort_keys=False,
        )
    )

    collection = SurveyCollection.load(collection="fake", config_files_directory=tmp_path)

    assert collection.name == "fake"
    assert collection.surveys[0].name == "fake_2020"
    assert collection.surveys[0].tables["person"]["variables"] == ["person_id"]


def test_survey_collection_dumps_yaml_metadata(tmp_path):
    metadata = tmp_path / "collections" / "fake.yaml"
    metadata.parent.mkdir()
    metadata.write_text(yaml.safe_dump({"version": 1, "name": "fake", "surveys": {}}, sort_keys=False))
    (tmp_path / "data-manager.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "storage": {
                    "collections_directory": str(tmp_path / "collections"),
                    "output_directory": str(tmp_path / "output"),
                    "tmp_directory": str(tmp_path / "tmp"),
                },
                "collections": {"fake": {"metadata": "fake.yaml"}},
            },
            sort_keys=False,
        )
    )

    collection = SurveyCollection.load(collection="fake", config_files_directory=tmp_path)
    collection.dump()

    assert yaml.safe_load(metadata.read_text())["name"] == "fake"
