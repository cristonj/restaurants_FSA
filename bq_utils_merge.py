"""
Enhanced BigQuery utilities with MERGE capability for duplicate prevention.
This module provides an alternative approach using MERGE statements to ensure
no duplicate FHRSIDs are inserted at the database level.
"""

import streamlit as st
import pandas as pd
from google.cloud import bigquery
from typing import List, Dict, Any
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def merge_new_restaurants_to_bigquery(
    new_restaurants_df: pd.DataFrame,
    project_id: str,
    dataset_id: str,
    table_id: str,
    bq_schema: List[bigquery.SchemaField]
) -> bool:
    """
    Merges new restaurant data into BigQuery table using MERGE statement.
    This ensures that only FHRSIDs that don't exist in the target table are inserted.
    
    Args:
        new_restaurants_df: DataFrame containing new restaurant data with sanitized column names
        project_id: The Google Cloud project ID
        dataset_id: The BigQuery dataset ID
        table_id: The BigQuery table ID
        bq_schema: List of BigQuery schema fields
        
    Returns:
        True if merge was successful, False otherwise
    """
    if new_restaurants_df.empty:
        st.info("No new restaurants to merge into BigQuery.")
        return True
    
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    temp_table_id = f"{table_id}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_table_ref = f"{project_id}.{dataset_id}.{temp_table_id}"
    
    try:
        # Step 1: Create a temporary table with the new data
        st.info(f"Creating temporary table {temp_table_id} with {len(new_restaurants_df)} new records...")
        
        job_config = bigquery.LoadJobConfig(
            schema=bq_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            column_name_character_map="V2",
        )
        
        job = client.load_table_from_dataframe(
            new_restaurants_df, 
            temp_table_ref, 
            job_config=job_config
        )
        job.result()  # Wait for the job to complete
        
        # Step 2: Execute MERGE statement
        # Build column list for INSERT
        column_names = [field.name for field in bq_schema if field.name in new_restaurants_df.columns]
        columns_str = ", ".join([f"`{col}`" for col in column_names])
        source_columns_str = ", ".join([f"source.`{col}`" for col in column_names])
        
        merge_query = f"""
        MERGE `{table_ref}` AS target
        USING `{temp_table_ref}` AS source
        ON target.fhrsid = source.fhrsid
        WHEN NOT MATCHED THEN
            INSERT ({columns_str})
            VALUES ({source_columns_str})
        """
        
        st.info("Executing MERGE to insert only new FHRSIDs...")
        logging.info(f"MERGE query:\n{merge_query}")
        
        merge_job = client.query(merge_query)
        merge_result = merge_job.result()
        
        # Get number of rows inserted
        num_inserted = merge_job.num_dml_affected_rows
        if num_inserted is not None:
            st.success(f"Successfully merged data: {num_inserted} new records inserted into {table_ref}")
            logging.info(f"MERGE completed: {num_inserted} rows inserted")
        else:
            st.success(f"MERGE completed successfully for {table_ref}")
            logging.info("MERGE completed (row count not available)")
        
        # Step 3: Clean up temporary table
        client.delete_table(temp_table_ref, not_found_ok=True)
        logging.info(f"Temporary table {temp_table_ref} deleted")
        
        return True
        
    except Exception as e:
        st.error(f"Error during MERGE operation: {e}")
        logging.error(f"MERGE operation failed: {e}")
        
        # Try to clean up temp table even if merge failed
        try:
            client.delete_table(temp_table_ref, not_found_ok=True)
        except:
            pass
            
        return False


def upsert_restaurants_to_bigquery(
    restaurants_df: pd.DataFrame,
    project_id: str,
    dataset_id: str,
    table_id: str,
    bq_schema: List[bigquery.SchemaField],
    update_columns: List[str] = None
) -> bool:
    """
    Performs an UPSERT operation (UPDATE existing, INSERT new) on BigQuery table.
    This is useful if you want to update certain fields for existing FHRSIDs
    while inserting new ones.
    
    Args:
        restaurants_df: DataFrame containing restaurant data with sanitized column names
        project_id: The Google Cloud project ID
        dataset_id: The BigQuery dataset ID
        table_id: The BigQuery table ID
        bq_schema: List of BigQuery schema fields
        update_columns: List of column names to update for existing records.
                       If None, only inserts new records (no updates).
        
    Returns:
        True if upsert was successful, False otherwise
    """
    if restaurants_df.empty:
        st.info("No restaurants to upsert into BigQuery.")
        return True
    
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    temp_table_id = f"{table_id}_upsert_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_table_ref = f"{project_id}.{dataset_id}.{temp_table_id}"
    
    try:
        # Step 1: Create a temporary table with the data
        st.info(f"Creating temporary table for upsert with {len(restaurants_df)} records...")
        
        job_config = bigquery.LoadJobConfig(
            schema=bq_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            column_name_character_map="V2",
        )
        
        job = client.load_table_from_dataframe(
            restaurants_df, 
            temp_table_ref, 
            job_config=job_config
        )
        job.result()
        
        # Step 2: Build and execute MERGE statement
        column_names = [field.name for field in bq_schema if field.name in restaurants_df.columns]
        
        # Build UPDATE clause if update_columns specified
        if update_columns:
            update_set_clause = ", ".join([
                f"target.`{col}` = source.`{col}`" 
                for col in update_columns 
                if col in column_names and col != 'fhrsid'  # Don't update the key
            ])
            when_matched_clause = f"""
            WHEN MATCHED THEN
                UPDATE SET {update_set_clause}
            """ if update_set_clause else ""
        else:
            when_matched_clause = ""
        
        # Build INSERT clause
        insert_columns = ", ".join([f"`{col}`" for col in column_names])
        insert_values = ", ".join([f"source.`{col}`" for col in column_names])
        
        merge_query = f"""
        MERGE `{table_ref}` AS target
        USING `{temp_table_ref}` AS source
        ON target.fhrsid = source.fhrsid
        {when_matched_clause}
        WHEN NOT MATCHED THEN
            INSERT ({insert_columns})
            VALUES ({insert_values})
        """
        
        st.info("Executing UPSERT operation...")
        logging.info(f"UPSERT query:\n{merge_query}")
        
        merge_job = client.query(merge_query)
        merge_result = merge_job.result()
        
        num_affected = merge_job.num_dml_affected_rows
        if num_affected is not None:
            st.success(f"Successfully upserted data: {num_affected} records affected in {table_ref}")
            logging.info(f"UPSERT completed: {num_affected} rows affected")
        else:
            st.success(f"UPSERT completed successfully for {table_ref}")
            logging.info("UPSERT completed (row count not available)")
        
        # Step 3: Clean up temporary table
        client.delete_table(temp_table_ref, not_found_ok=True)
        logging.info(f"Temporary table {temp_table_ref} deleted")
        
        return True
        
    except Exception as e:
        st.error(f"Error during UPSERT operation: {e}")
        logging.error(f"UPSERT operation failed: {e}")
        
        # Try to clean up temp table
        try:
            client.delete_table(temp_table_ref, not_found_ok=True)
        except:
            pass
            
        return False