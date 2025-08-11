import unittest
import re
from unittest.mock import patch, MagicMock, PropertyMock, call, ANY
import pandas as pd

from st_app import main_ui

@patch('st_app.st', autospec=True)
class TestMainUIOnly(unittest.TestCase):
    def test_main_ui_displays_fetch_data_section(self, mock_st_global):
        mock_st_global.session_state = MagicMock()
        initial_session_state_attrs = {
            'recent_restaurants_df': None, 'current_project_id': None,
            'current_dataset_id': None, 'displaying_genai_temp': False
        }
        mock_st_global.session_state.configure_mock(**initial_session_state_attrs)

        def session_state_get(name, default=None):
            return getattr(mock_st_global.session_state, name, default)

        def session_state_contains(name):
            return hasattr(mock_st_global.session_state, name)

        mock_st_global.session_state.get = MagicMock(side_effect=session_state_get)
        type(mock_st_global.session_state).__contains__ = MagicMock(side_effect=session_state_contains)

        main_ui()

        mock_st_global.subheader.assert_called_once_with("Fetch API Data and Update Master List")
        mock_st_global.radio.assert_not_called()
