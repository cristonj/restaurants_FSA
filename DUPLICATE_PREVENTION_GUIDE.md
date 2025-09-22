# BigQuery Duplicate Prevention Guide

## Current Implementation Status ✅

**The system already implements the duplicate prevention logic you requested!** Here's how it works:

### 1. Data Collection Flow

```
API Data Collection → Load Existing BigQuery Data → Compare FHRSIDs → Add Only New Records
```

### 2. Duplicate Prevention Logic (Already Implemented)

#### Step 1: Load Existing Data (`data_processing.py`, lines 93-109)
```python
existing_fhrsid_set = set()
for est in master_data:
    if isinstance(est, dict):
        # Check for both 'FHRSID' and 'fhrsid' keys
        if 'FHRSID' in est and est['FHRSID'] is not None:
            fhrsid_val = est['FHRSID']
        elif 'fhrsid' in est and est['fhrsid'] is not None:
            fhrsid_val = est['fhrsid']
        
        # Canonicalize and add to existing set
        canonical_fhrsid = str(int(fhrsid_val))  # Normalize format
        existing_fhrsid_set.add(canonical_fhrsid)
```

#### Step 2: Check Against Existing FHRSIDs (`data_processing.py`, line 127)
```python
if canonical_api_fhrsid not in existing_fhrsid_set:
    # Only process if FHRSID doesn't exist in BigQuery
```

#### Step 3: Assign first_seen Date Only to New Records (`data_processing.py`, line 130)
```python
api_establishment['first_seen'] = today_date  # Only for new records
api_establishment['manual_review'] = "not reviewed"
```

#### Step 4: Append Only New Records (`st_app.py`, lines 398-415)
```python
# process_and_update_master_data returns ONLY new restaurants
new_restaurants = process_and_update_master_data(master_restaurant_data, combined_api_data)

# Append only the new records
_append_new_data_to_bigquery(new_restaurants, project_id, dataset_id, table_id)
```

### 3. Additional Safeguards

The system also handles:
- **Duplicate FHRSIDs within the same API batch** (lines 113, 129, 149 in `data_processing.py`)
- **Canonical FHRSID formatting** to ensure consistent comparison (e.g., "123" vs 123)
- **Both 'FHRSID' and 'fhrsid' field names** for compatibility

## How It Works in Practice

1. **First Run (Empty BigQuery table)**:
   - API returns 100 restaurants with FHRSIDs: [1, 2, 3, ..., 100]
   - BigQuery is empty, so `existing_fhrsid_set` = {}
   - All 100 records are new → All get `first_seen` date → All are added to BigQuery

2. **Second Run (BigQuery has 100 records)**:
   - API returns 120 restaurants with FHRSIDs: [1, 2, 3, ..., 100, 101, 102, ..., 120]
   - BigQuery has [1, 2, 3, ..., 100], so `existing_fhrsid_set` = {1, 2, ..., 100}
   - Only FHRSIDs [101, 102, ..., 120] are new
   - Only these 20 records get `first_seen` date and are added to BigQuery

3. **Third Run (BigQuery has 120 records)**:
   - API returns same 120 restaurants
   - All FHRSIDs already exist in BigQuery
   - No new records are added

## Optional Enhancement: Database-Level Duplicate Prevention

While the current implementation works correctly, you can add an extra layer of protection using BigQuery's MERGE statement instead of APPEND. This ensures duplicate prevention at the database level.

### Benefits of MERGE Approach:
- **Database-level guarantee**: Even if application logic fails, BigQuery won't insert duplicates
- **Atomic operation**: All-or-nothing transaction
- **Better visibility**: BigQuery reports exact number of records inserted vs skipped

### How to Enable MERGE (Optional):

1. **Add the new merge utilities**:
   ```python
   from bq_utils_merge import merge_new_restaurants_to_bigquery
   ```

2. **Replace the append call in `st_app.py`** (line 415):
   ```python
   # Instead of:
   _append_new_data_to_bigquery(new_restaurants, project_id_append, dataset_id_append, table_id_append)
   
   # Use:
   _append_new_data_to_bigquery_with_merge(new_restaurants, project_id_append, dataset_id_append, table_id_append)
   ```

### MERGE SQL Example:
```sql
MERGE `project.dataset.restaurants` AS target
USING `project.dataset.restaurants_temp` AS source
ON target.fhrsid = source.fhrsid
WHEN NOT MATCHED THEN
    INSERT (fhrsid, businessname, first_seen, ...)
    VALUES (source.fhrsid, source.businessname, source.first_seen, ...)
```

## Testing the Duplicate Prevention

To verify the system is working correctly:

1. **Run initial data fetch**:
   - Note the number of records added
   - Check BigQuery for the records with their `first_seen` dates

2. **Run the same fetch again immediately**:
   - Should report "0 new restaurants found" or similar
   - BigQuery table should have the same number of records
   - No duplicate FHRSIDs should exist

3. **Query to check for duplicates**:
   ```sql
   SELECT fhrsid, COUNT(*) as count
   FROM `project.dataset.restaurants`
   GROUP BY fhrsid
   HAVING count > 1
   ```
   This should return no results if duplicate prevention is working.

## Summary

✅ **Current Status**: The application already implements complete duplicate prevention:
- Only FHRSIDs not in BigQuery get added
- Only new records get `first_seen` dates
- The system uses APPEND to add only new rows

🔧 **Optional Enhancement**: Use MERGE for database-level duplicate prevention (code provided in `bq_utils_merge.py` and `enhanced_st_app_section.py`)

📊 **Result**: No duplicate FHRSIDs will exist in your BigQuery table, and each restaurant will have the correct `first_seen` date from when it was first discovered.