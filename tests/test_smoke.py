def test_data_manager_imports():
    from openfisca_data_manager.config.paths import default_config_files_directory
    from openfisca_data_manager.core import Survey, SurveyCollection, Table
    from openfisca_data_manager.io import read_sas
    from openfisca_data_manager.processing import clean_data_frame

    assert default_config_files_directory is not None
    assert Survey is not None
    assert SurveyCollection is not None
    assert Table is not None
    assert read_sas is not None
    assert clean_data_frame is not None
