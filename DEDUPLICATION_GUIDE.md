# FHRSID Deduplication System Documentation

## Overview
The system has been enhanced to ensure that only **new** restaurants (identified by unique FHRSIDs) are added to the BigQuery table. This prevents duplicate entries and ensures data integrity.

## Key Features

### 1. **Multi-Layer Deduplication**
The system implements deduplication at multiple levels:

#### a) **In-Memory Deduplication** (`data_processing.py`)
- Before any BigQuery operations, the system checks FHRSIDs against the existing master data loaded from BigQuery
- Filters out any FHRSIDs that already exist in the database
- Also handles duplicates within the same API batch

#### b) **BigQuery-Level Deduplication** (`bq_utils.py`)
- `get_existing_fhrsids()`: Queries BigQuery to get all existing FHRSIDs
- `append_new_restaurants_with_dedup()`: Double-checks against BigQuery before inserting
- Provides an additional safety layer to prevent race conditions

#### c) **MERGE Operation Support** (`bq_utils.py`)
- `batch_insert_new_restaurants_via_merge()`: Uses BigQuery MERGE for efficient batch operations
- Creates a temporary table and merges only non-matching records
- Most efficient for large-scale operations

### 2. **First Seen Date Assignment**
- Only new restaurants receive a `first_seen` date (set to the current date)
- Existing restaurants retain their original `first_seen` date
- This provides an audit trail of when each restaurant was first discovered

### 3. **Comprehensive Logging**
The system provides detailed logging at each step:
- Number of existing FHRSIDs found
- Number of new restaurants identified
- Number of duplicates filtered out
- Processing summaries after each operation

## How It Works

### Data Flow
1. **API Data Collection**: Fetch restaurant data from the Food Standards Agency API
2. **Load Master Data**: Retrieve existing records from BigQuery
3. **Identify New Records**: Compare API FHRSIDs against existing ones
4. **Filter Duplicates**: Remove any FHRSIDs that already exist
5. **Assign Metadata**: Add `first_seen` date to new records only
6. **Insert to BigQuery**: Add only the new records to the table

### Key Functions

#### `process_and_update_master_data()` (data_processing.py)
```python
# Processes API data and identifies new establishments
# Returns only restaurants with FHRSIDs not in master_data
```

#### `append_new_restaurants_with_dedup()` (bq_utils.py)
```python
# Double-checks against BigQuery before inserting
# Returns (success: bool, num_added: int)
```

#### `batch_insert_new_restaurants_via_merge()` (bq_utils.py)
```python
# Uses MERGE operation for efficient batch inserts
# Creates temp table and merges only new records
```

## Usage Example

```python
# The system automatically handles deduplication when fetching new data
# In st_app.py, the flow is:

# 1. Fetch API data
api_data = fetch_api_data(lon, lat, max_results, page)

# 2. Load existing data from BigQuery
master_data = load_master_data(project_id, dataset_id, table_id, load_all_data_from_bq)

# 3. Process and identify only new restaurants
new_restaurants = process_and_update_master_data(master_data, api_data)

# 4. Append only new restaurants to BigQuery
success, num_added = append_new_restaurants_with_dedup(
    df=new_restaurants_df,
    project_id=project_id,
    dataset_id=dataset_id,
    table_id=table_id,
    bq_schema=schema
)
```

## Testing

Run the test script to verify the deduplication system:

```bash
python3 test_deduplication.py
```

The test covers:
- All new FHRSIDs scenario
- All existing FHRSIDs (duplicates) scenario
- Mixed scenario (some new, some existing)
- Duplicates within API batch
- Empty API response handling
- Column name sanitization

## Benefits

1. **Data Integrity**: Prevents duplicate entries in BigQuery
2. **Efficiency**: Only processes and stores new data
3. **Cost Savings**: Reduces BigQuery storage and query costs
4. **Audit Trail**: Tracks when each restaurant was first discovered
5. **Scalability**: Handles large batches efficiently with MERGE operations
6. **Reliability**: Multiple layers of deduplication ensure no duplicates

## Configuration

No additional configuration is required. The system automatically:
- Detects existing FHRSIDs
- Filters duplicates
- Assigns metadata to new records only
- Handles all edge cases

## Error Handling

The system gracefully handles:
- Empty API responses
- BigQuery connection errors
- Malformed data
- Duplicate FHRSIDs in the same batch
- Race conditions (via BigQuery-level checks)

## Performance Considerations

- **Small Batches (<1000 records)**: Use `append_new_restaurants_with_dedup()`
- **Large Batches (>1000 records)**: Consider using `batch_insert_new_restaurants_via_merge()`
- **Real-time Updates**: The in-memory deduplication is sufficient for most use cases

## Monitoring

Monitor the system through:
- Streamlit UI messages showing filtered records
- Console logs with detailed processing information
- BigQuery audit logs for actual insertions

## Future Enhancements

Potential improvements could include:
- Caching of existing FHRSIDs for better performance
- Batch processing optimizations
- Parallel processing for multiple API calls
- Historical tracking of all changes (not just first_seen)