import unittest
import re
from unittest.mock import patch, MagicMock, PropertyMock, call, ANY
import pandas as pd

from st_app import main_ui

@patch('st_app.st', autospec=True)
class TestMainUIOnly(unittest.TestCase):
    def test_main_ui_radio_options(self, mock_st_global):
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

        mock_st_global.radio.assert_called_once_with(
            "Choose an action:",
            ("Fetch API Data", "Update Fields")
        )


class TestHandleMergeUpdateAction(unittest.TestCase):
    @patch('st_app.display_data')
    @patch('st_app.load_all_data_from_bq')
    @patch('st_app.execute_merge_query')
    @patch('st_app.st') # Mock streamlit module
    def test_handle_merge_update_action_success(self, mock_st, mock_execute_merge_query, mock_load_all_data, mock_display_data):
        mock_execute_merge_query.return_value = True
        sample_data = [{'col1': 'data1', 'col2': 'value1'}]
        mock_load_all_data.return_value = sample_data

        master_path = "proj.dataset.master_table"
        update_path = "proj.dataset.update_table"
        match_id = "common_id"
        field_update = "target_field"

        from st_app import handle_merge_update_action
        handle_merge_update_action(master_path, update_path, match_id, field_update)

        expected_query = f"""
        MERGE `{master_path}` T
        USING `{update_path}` S
        ON T.{match_id} = S.{match_id}
        WHEN MATCHED THEN
          UPDATE SET T.{field_update} = S.{field_update}
        """
        mock_st.info.assert_any_call(f"Initiating MERGE operation to update '{field_update}' in '{master_path}' using '{update_path}' on matching '{match_id}'.")
        mock_execute_merge_query.assert_called_once_with(expected_query, project_id='proj')
        mock_load_all_data.assert_called_once_with(project_id='proj', dataset_id='dataset', table_id='master_table')
        mock_display_data.assert_called_once_with(sample_data)
        mock_st.success.assert_any_call("MERGE operation completed successfully.")

    @patch('st_app.display_data')
    @patch('st_app.load_all_data_from_bq')
    @patch('st_app.execute_merge_query')
    @patch('st_app.st')
    def test_handle_merge_update_action_merge_fails(self, mock_st, mock_execute_merge_query, mock_load_all_data, mock_display_data):
        mock_execute_merge_query.return_value = False

        master_path = "proj.dataset.master_table"
        update_path = "proj.dataset.update_table"
        match_id = "common_id"
        field_update = "target_field"

        from st_app import handle_merge_update_action
        handle_merge_update_action(master_path, update_path, match_id, field_update)

        mock_st.error.assert_any_call("MERGE operation failed. Check logs for details.")
        mock_load_all_data.assert_not_called()
        mock_display_data.assert_not_called()

    @patch('st_app.execute_merge_query')
    @patch('st_app.st')
    def test_handle_merge_update_action_invalid_paths(self, mock_st, mock_execute_merge_query):
        from st_app import handle_merge_update_action

        invalid_paths_to_test = [
            ("proj.dataset", "proj.dataset.update", "id", "field"), # Master path invalid
            ("proj.dataset.master", "proj.update", "id", "field"),   # Update path invalid
            ("", "proj.dataset.update", "id", "field"),              # Master path empty
            ("proj.dataset.master", "", "id", "field"),              # Update path empty
            ("p.d.t.e", "p.d.u", "id", "field")                      # Master path too many parts
        ]

        for paths in invalid_paths_to_test:
            mock_st.error.reset_mock() # Reset mock for each iteration
            mock_execute_merge_query.reset_mock()

            handle_merge_update_action(*paths)

            mock_st.error.assert_called_once() # Check that st.error was called
            self.assertIn("Invalid BigQuery", mock_st.error.call_args[0][0]) # Check part of the error message
            mock_execute_merge_query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
