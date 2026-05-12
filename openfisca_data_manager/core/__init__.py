# Survey, Table, SurveyCollection. Legacy modules re-export for compatibility.
from openfisca_data_manager.core.dataset import SurveyCollection, load_table
from openfisca_data_manager.core.survey import NoMoreDataError, Survey
from openfisca_data_manager.core.table import Table

__all__ = ["NoMoreDataError", "Survey", "SurveyCollection", "Table", "load_table"]
