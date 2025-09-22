"""
Enhanced section for st_app.py that uses MERGE instead of APPEND
to ensure duplicate prevention at the database level.

This can replace the _append_new_data_to_bigquery function in st_app.py
"""

from typing import List, Dict, Any
import streamlit as st
import pandas as pd
from google.cloud import bigquery
from bq_utils import sanitize_column_name
from bq_utils_merge import merge_new_restaurants_to_bigquery


def _append_new_data_to_bigquery_with_merge(new_restaurants: List[Dict[str, Any]], project_id: str, dataset_id: str, table_id: str):
    """
    Enhanced version that uses MERGE to ensure no duplicate FHRSIDs are inserted.
    This provides database-level guarantee against duplicates, even if the 
    in-memory duplicate check somehow misses a record.
    
    Args:
        new_restaurants: List of new restaurant dictionaries to add
        project_id: The Google Cloud project ID
        dataset_id: The BigQuery dataset ID
        table_id: The BigQuery table ID
    """
    if not new_restaurants:
        st.info("No new restaurants found to add to BigQuery.")
        return
    
    st.info(f"Preparing {len(new_restaurants)} new records for BigQuery merge...")
    df_new_restaurants = pd.json_normalize(new_restaurants)
    
    # Define comprehensive schema for merge operation
    bq_schema_for_merge = [
        bigquery.SchemaField(sanitize_column_name('FHRSID'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('LocalAuthorityBusinessID'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('BusinessName'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('BusinessType'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('BusinessTypeID'), 'INTEGER'),
        bigquery.SchemaField(sanitize_column_name('AddressLine1'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('AddressLine2'), 'STRING', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('AddressLine3'), 'STRING', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('AddressLine4'), 'STRING', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('PostCode'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('RatingValue'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('RatingKey'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('LocalAuthorityCode'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('LocalAuthorityName'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('LocalAuthorityWebSite'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('LocalAuthorityEmailAddress'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('Scores.Hygiene'), 'INTEGER', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('Scores.Structural'), 'INTEGER', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('Scores.ConfidenceInManagement'), 'INTEGER', mode='NULLABLE'),
        bigquery.SchemaField(sanitize_column_name('SchemeType'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('Geocode.Longitude'), 'FLOAT'),
        bigquery.SchemaField(sanitize_column_name('Geocode.Latitude'), 'FLOAT'),
        bigquery.SchemaField(sanitize_column_name('NewRatingPending'), 'BOOLEAN'),
        bigquery.SchemaField(sanitize_column_name('first_seen'), 'DATE'),
        bigquery.SchemaField(sanitize_column_name('manual_review'), 'STRING'),
        bigquery.SchemaField(sanitize_column_name('gemini_insights'), 'STRING', mode='NULLABLE')
    ]
    
    # Sanitize DataFrame column names
    sanitized_df_columns = {}
    for orig_col in df_new_restaurants.columns:
        sanitized = sanitize_column_name(orig_col)
        sanitized_df_columns[orig_col] = sanitized
    
    df_new_restaurants.columns = df_new_restaurants.columns.map(sanitized_df_columns)
    
    # Convert data types as needed
    
    # Convert first_seen to date
    s_first_seen = sanitize_column_name('first_seen')
    if s_first_seen in df_new_restaurants.columns:
        df_new_restaurants[s_first_seen] = pd.to_datetime(df_new_restaurants[s_first_seen], errors='coerce')
    
    # Convert score columns to integers
    score_cols_original = ['Scores.Hygiene', 'Scores.Structural', 'Scores.ConfidenceInManagement']
    for orig_col_name in score_cols_original:
        s_col_name = sanitize_column_name(orig_col_name)
        if s_col_name in df_new_restaurants.columns:
            df_new_restaurants[s_col_name] = pd.to_numeric(df_new_restaurants[s_col_name], errors='coerce').astype('Int64')
    
    # Ensure FHRSID is string
    s_fhrsid = sanitize_column_name('FHRSID')
    if s_fhrsid in df_new_restaurants.columns:
        df_new_restaurants[s_fhrsid] = df_new_restaurants[s_fhrsid].astype(str)
    
    # Convert BusinessTypeID to integer
    s_business_type_id = sanitize_column_name('BusinessTypeID')
    if s_business_type_id in df_new_restaurants.columns:
        df_new_restaurants[s_business_type_id] = pd.to_numeric(df_new_restaurants[s_business_type_id], errors='coerce').astype('Int64')
    
    # Convert geocode columns to float
    s_lon = sanitize_column_name('Geocode.Longitude')
    if s_lon in df_new_restaurants.columns:
        df_new_restaurants[s_lon] = pd.to_numeric(df_new_restaurants[s_lon], errors='coerce')
    
    s_lat = sanitize_column_name('Geocode.Latitude')
    if s_lat in df_new_restaurants.columns:
        df_new_restaurants[s_lat] = pd.to_numeric(df_new_restaurants[s_lat], errors='coerce')
    
    # Convert NewRatingPending to boolean
    s_new_rating = sanitize_column_name('NewRatingPending')
    if s_new_rating in df_new_restaurants.columns:
        mapping = {'true': True, 'false': False, 'TRUE': True, 'FALSE': False}
        df_new_restaurants[s_new_rating] = df_new_restaurants[s_new_rating].astype(str).str.lower().map(mapping)
        df_new_restaurants[s_new_rating] = df_new_restaurants[s_new_rating].astype('boolean')
    
    # Select only columns that exist in both DataFrame and schema
    cols_to_keep = [field.name for field in bq_schema_for_merge if field.name in df_new_restaurants.columns]
    df_for_bq = df_new_restaurants[cols_to_keep]
    
    # Filter schema to match DataFrame columns
    final_bq_schema = [field for field in bq_schema_for_merge if field.name in df_for_bq.columns]
    
    if df_for_bq.empty:
        st.warning("After processing, the DataFrame for new restaurants is empty. Skipping BigQuery merge.")
        return
    
    # Use MERGE instead of APPEND
    success = merge_new_restaurants_to_bigquery(
        new_restaurants_df=df_for_bq,
        project_id=project_id,
        dataset_id=dataset_id,
        table_id=table_id,
        bq_schema=final_bq_schema
    )
    
    if success:
        st.success(f"Successfully merged new records to BigQuery table {project_id}.{dataset_id}.{table_id}. Duplicates were automatically skipped.")
    else:
        st.error(f"Failed to merge new records to BigQuery table {project_id}.{dataset_id}.{table_id}.")


# Usage in handle_fetch_data_action:
# Replace the call to _append_new_data_to_bigquery with:
# _append_new_data_to_bigquery_with_merge(new_restaurants, project_id_append, dataset_id_append, table_id_append)