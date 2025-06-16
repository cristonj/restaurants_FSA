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
            ("Fetch API Data", "Recent Restaurant Analysis", "Update Fields")
        )

@patch('st_app.st', autospec=True)
class TestRecentRestaurantAnalysisGeminiUpdate(unittest.TestCase):

    def setUp(self):
        self.mock_call_gemini = patch('st_app.call_gemini_with_fhrs_data').start()
        self.mock_update_bq = patch('st_app.update_rows_in_bigquery').start()
        self.mock_get_recent_restaurants = patch('st_app.get_recent_restaurants').start()
        self.mock_create_temp_table = patch('st_app.create_recent_restaurants_temp_table').start()
        self.addCleanup(patch.stopall)

    def _setup_initial_session_state(self, mock_st_global_obj):
        mock_st_global_obj.session_state = MagicMock()
        attrs = {
            'recent_restaurants_df': None, 'current_project_id': None,
            'current_dataset_id': None, 'displaying_genai_temp': False
        }
        mock_st_global_obj.session_state.configure_mock(**attrs)

        def session_state_get(name, default=None):
            return getattr(mock_st_global_obj.session_state, name, default)

        def session_state_contains(name):
            if name in attrs: return True # Check against initial known attrs
            return hasattr(mock_st_global_obj.session_state, name)


        mock_st_global_obj.session_state.get = MagicMock(side_effect=session_state_get)
        type(mock_st_global_obj.session_state).__contains__ = MagicMock(side_effect=session_state_contains)

        def set_item(key, value): setattr(mock_st_global_obj.session_state, key, value)
        mock_st_global_obj.session_state.__setitem__ = MagicMock(side_effect=set_item)
        def get_item(key): return getattr(mock_st_global_obj.session_state, key)
        mock_st_global_obj.session_state.__getitem__ = MagicMock(side_effect=get_item)


    def _configure_run_specific_mocks(self, mock_st_global_obj, app_mode="Recent Restaurant Analysis",
                                 n_days=7, bq_source_path="proj.dset.table",
                                 fetch_button_click=False, gemini_analysis_button_click=False):
        mock_st_global_obj.radio.return_value = app_mode
        mock_st_global_obj.number_input.return_value = n_days

        def text_input_side_effect(label, **kwargs):
            if "Enter BigQuery source table" in label: return bq_source_path
            return f"default_for_{label}"
        mock_st_global_obj.text_input.side_effect = text_input_side_effect

        if app_mode == "Recent Restaurant Analysis":
            mock_st_global_obj.button.side_effect = [fetch_button_click, gemini_analysis_button_click]
        else:
            mock_st_global_obj.button.side_effect = []

        mock_st_global_obj.stop = MagicMock()
        mock_st_global_obj.error = MagicMock() # Ensure error is a fresh mock for assertions
        mock_st_global_obj.warning = MagicMock()
        mock_st_global_obj.success = MagicMock()
        mock_st_global_obj.info = MagicMock()
        mock_st_global_obj.dataframe = MagicMock()


    def test_successful_update_path(self, mock_st_global):
        self._setup_initial_session_state(mock_st_global)

        self.mock_get_recent_restaurants.return_value = pd.DataFrame({'fhrsid': [123, 456], 'BusinessName': ['Restaurant A', 'Restaurant B']})
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False, bq_source_path="test_project.test_dataset.test_table")
        main_ui()

        self.assertEqual(mock_st_global.session_state.current_project_id, "test_project")
        self.assertEqual(mock_st_global.session_state.current_dataset_id, "test_dataset")

        # Reset non-session_state mocks for the second run
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True, bq_source_path="test_project.test_dataset.test_table")

        sample_insights = pd.DataFrame({'fhrsid': [123, 456], 'gemini_insights': ['Insight for 123', 'Insight for 456']})
        self.mock_call_gemini.return_value = sample_insights
        self.mock_update_bq.return_value = True
        main_ui()

        self.mock_call_gemini.assert_called_once_with(project_id="test_project", dataset_id="test_dataset", gemini_prompt=ANY)
        self.assertEqual(self.mock_update_bq.call_count, 2)
        mock_st_global.success.assert_any_call("Successfully updated 2 rows with Gemini insights.")

    def test_missing_fhrsid_column_in_insights_df(self, mock_st_global):
        self._setup_initial_session_state(mock_st_global)

        # --- First run: Fetch restaurants ---
        self.mock_get_recent_restaurants.return_value = pd.DataFrame({'fhrsid': [789], 'BusinessName': ['Test Resto']})
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False, bq_source_path="proj.dset.table")
        main_ui()

        # Ensure session state is correctly set for the next phase
        self.assertEqual(mock_st_global.session_state.current_project_id, "proj")


        # --- Second run: Run Gemini Analysis ---
        # Reset mocks that would be called per run, but preserve session state
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True, bq_source_path="proj.dset.table")

        insights_missing_fhrsid = pd.DataFrame({'gemini_insights': ['Insight A']})
        self.mock_call_gemini.return_value = insights_missing_fhrsid

        main_ui()

        self.mock_call_gemini.assert_called_once() # Gemini should be called
        mock_st_global.error.assert_any_call("FHRSID column is missing in Gemini insights. Cannot update main table.")
        mock_st_global.stop.assert_called_once()
        self.mock_update_bq.assert_not_called()


    def _run_full_gemini_flow(self, mock_st_global,
                              fetch_bq_path="proj.dset.table",
                              mock_get_restaurants_df=pd.DataFrame({'fhrsid': [789], 'BusinessName': ['Test Resto']}),
                              gemini_bq_path=None,
                              mock_insights_df_to_return=None,
                              mock_update_bq_success=True,
                              expect_gemini_call=False, # Whether call_gemini_with_fhrs_data itself is expected
                              expect_bq_parsing_success=True, # Whether bq_source_table_input.split('.') is expected to succeed
                              expect_column_checks_success=True, # Whether fhrsid/gemini_insights columns are expected to be present
                              expect_update_bq_call_count=0,
                              expected_st_warning=None,
                              expected_st_error=None,
                              expected_st_success=None,
                              expect_st_stop=False
                             ):

        if gemini_bq_path is None:
            gemini_bq_path = fetch_bq_path

        self._setup_initial_session_state(mock_st_global)

        # --- First run: "Fetch Recent Restaurants" ---
        self.mock_get_recent_restaurants.return_value = mock_get_restaurants_df
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False, bq_source_path=fetch_bq_path)
        main_ui()

        # --- Configure for Second run (mocks are reset inside it) ---
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True, bq_source_path=gemini_bq_path)

        self.mock_call_gemini.return_value = mock_insights_df_to_return
        self.mock_update_bq.return_value = mock_update_bq_success

        main_ui()

        if expect_gemini_call: self.mock_call_gemini.assert_called_once()
        else: self.mock_call_gemini.assert_not_called() # This case might not be hit if button isn't clicked

        self.assertEqual(self.mock_update_bq.call_count, expect_update_bq_call_count)

        if expected_st_warning: mock_st_global.warning.assert_any_call(expected_st_warning)
        if expected_st_error: mock_st_global.error.assert_any_call(expected_st_error)
        if expected_st_success: mock_st_global.success.assert_any_call(expected_st_success)

        if expect_st_stop: mock_st_global.stop.assert_called_once()
        # If st.stop() is expected, other assertions about calls after st.stop might not be relevant
        # unless they happen before st.stop().


    def test_insights_df_empty(self, mock_st_global):
        self._run_full_gemini_flow(mock_st_global,
                                 mock_insights_df_to_return=pd.DataFrame(),
                                 expect_gemini_call=True,
                                 expect_update_bq_call_count=0,
                                 expected_st_warning="No insights were generated or returned, so the main table was not updated.")

    def test_insights_df_none(self, mock_st_global):
        self._run_full_gemini_flow(mock_st_global,
                                 mock_insights_df_to_return=None,
                                 expect_gemini_call=True,
                                 expect_update_bq_call_count=0,
                                 expected_st_warning="No insights were generated or returned, so the main table was not updated.")

    # test_missing_fhrsid_column_in_insights_df is now explicit, not using _run_full_gemini_flow

    def test_missing_gemini_insights_column_in_insights_df(self, mock_st_global):
        self._setup_initial_session_state(mock_st_global)
        self.mock_get_recent_restaurants.return_value = pd.DataFrame({'fhrsid': [789]})
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False)
        main_ui() # Fetch run

        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True)
        self.mock_call_gemini.return_value = pd.DataFrame({'fhrsid': [123]}) # Missing 'gemini_insights'
        main_ui() # Gemini run

        self.mock_call_gemini.assert_called_once()
        mock_st_global.error.assert_any_call("gemini_insights column is missing. Cannot update main table.")
        mock_st_global.stop.assert_called_once()
        self.mock_update_bq.assert_not_called()


    def test_invalid_bq_source_table_input_format_for_update(self, mock_st_global):
        self._setup_initial_session_state(mock_st_global)
        self.mock_get_recent_restaurants.return_value = pd.DataFrame({'fhrsid': [789]})
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False, bq_source_path="valid.path.ok")
        main_ui() # Fetch run

        invalid_path = "invalid.pathonly"
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True, bq_source_path=invalid_path)
        self.mock_call_gemini.return_value = pd.DataFrame({'fhrsid': [123], 'gemini_insights': ['Insight']})
        main_ui() # Gemini run

        self.mock_call_gemini.assert_called_once()
        # Corrected expected error message string representation
        actual_exception_message = "not enough values to unpack (expected 3, got 2)"
        expected_error_message = f"Invalid BigQuery table path for the main table: '{invalid_path}'. Error: {actual_exception_message}"

        mock_st_global.error.assert_any_call(expected_error_message)
        mock_st_global.stop.assert_called_once()
        self.mock_update_bq.assert_not_called()


    def test_update_rows_in_bigquery_fails(self, mock_st_global):
        self._setup_initial_session_state(mock_st_global)
        fetched_df = pd.DataFrame({'fhrsid': [789, 890], 'BusinessName': ['Test Resto', 'Resto 2']})
        self.mock_get_recent_restaurants.return_value = fetched_df
        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=True, gemini_analysis_button_click=False, bq_source_path="proj.dset.table")
        main_ui() # Fetch run

        self._configure_run_specific_mocks(mock_st_global, fetch_button_click=False, gemini_analysis_button_click=True, bq_source_path="proj.dset.table")
        insights_df = pd.DataFrame({'fhrsid': [789, 890], 'gemini_insights': ['Insight 1', 'Insight 2']})
        self.mock_call_gemini.return_value = insights_df
        self.mock_update_bq.return_value = False # BQ update fails

        main_ui() # Gemini run

        self.mock_call_gemini.assert_called_once()
        self.assertEqual(self.mock_update_bq.call_count, 2)
        mock_st_global.warning.assert_any_call("Failed to update insights for FHRSID 789. Check logs.")
        mock_st_global.warning.assert_any_call("Failed to update insights for FHRSID 890. Check logs.")
        mock_st_global.error.assert_any_call("Update summary: Successfully updated 0 rows. Failed to update 2 rows.")


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
        mock_execute_merge_query.assert_called_once_with(expected_query.strip(), 'proj')
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
