#!/usr/bin/env python3
"""
Test script to validate FHRSID deduplication functionality.
This script demonstrates how the system prevents duplicate FHRSIDs from being added to BigQuery.
"""

import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

# Import the functions we want to test
from data_processing import process_and_update_master_data
from bq_utils import sanitize_column_name

def create_mock_api_data(fhrsids: List[str]) -> Dict[str, Any]:
    """Create mock API data with specified FHRSIDs."""
    establishments = []
    for fhrsid in fhrsids:
        establishments.append({
            'FHRSID': fhrsid,
            'BusinessName': f'Test Restaurant {fhrsid}',
            'AddressLine1': f'{fhrsid} Test Street',
            'AddressLine2': 'Test Area',
            'AddressLine3': 'Test City',
            'PostCode': 'TE5T 123',
            'LocalAuthorityName': 'Test Authority',
            'RatingValue': '5',
            'NewRatingPending': 'false',
            'gemini_insights': None,
            'manual_review': None
        })
    
    return {
        'FHRSEstablishment': {
            'EstablishmentCollection': {
                'EstablishmentDetail': establishments
            }
        }
    }

def create_mock_master_data(fhrsids: List[str]) -> List[Dict[str, Any]]:
    """Create mock master data (simulating existing BigQuery data) with specified FHRSIDs."""
    master_data = []
    for fhrsid in fhrsids:
        master_data.append({
            'FHRSID': fhrsid,
            'BusinessName': f'Existing Restaurant {fhrsid}',
            'AddressLine1': f'{fhrsid} Existing Street',
            'PostCode': 'EX1ST 456',
            'LocalAuthorityName': 'Existing Authority',
            'RatingValue': '4',
            'NewRatingPending': 'false',
            'first_seen': '2024-01-01',
            'manual_review': 'not reviewed',
            'gemini_insights': None
        })
    
    return master_data

def test_deduplication_scenarios():
    """Test various deduplication scenarios."""
    
    print("=" * 80)
    print("Testing FHRSID Deduplication Functionality")
    print("=" * 80)
    
    # Scenario 1: All new FHRSIDs
    print("\n--- Scenario 1: All New FHRSIDs ---")
    existing_fhrsids = ['1001', '1002', '1003']
    new_api_fhrsids = ['2001', '2002', '2003']
    
    master_data = create_mock_master_data(existing_fhrsids)
    api_data = create_mock_api_data(new_api_fhrsids)
    
    print(f"Existing FHRSIDs in BigQuery: {existing_fhrsids}")
    print(f"FHRSIDs from API: {new_api_fhrsids}")
    
    new_restaurants = process_and_update_master_data(master_data, api_data)
    
    print(f"Result: {len(new_restaurants)} new restaurants will be added")
    print(f"New FHRSIDs to add: {[r['FHRSID'] for r in new_restaurants]}")
    
    # Verify all new FHRSIDs have first_seen date
    for restaurant in new_restaurants:
        assert 'first_seen' in restaurant, f"Missing first_seen for FHRSID {restaurant['FHRSID']}"
        assert restaurant['first_seen'] == datetime.now().strftime("%Y-%m-%d"), "Incorrect first_seen date"
    print("✓ All new restaurants have correct first_seen date")
    
    # Scenario 2: All existing FHRSIDs (duplicates)
    print("\n--- Scenario 2: All Existing FHRSIDs (Duplicates) ---")
    existing_fhrsids = ['1001', '1002', '1003']
    duplicate_api_fhrsids = ['1001', '1002', '1003']  # Same as existing
    
    master_data = create_mock_master_data(existing_fhrsids)
    api_data = create_mock_api_data(duplicate_api_fhrsids)
    
    print(f"Existing FHRSIDs in BigQuery: {existing_fhrsids}")
    print(f"FHRSIDs from API: {duplicate_api_fhrsids}")
    
    new_restaurants = process_and_update_master_data(master_data, api_data)
    
    print(f"Result: {len(new_restaurants)} new restaurants will be added")
    assert len(new_restaurants) == 0, "Should not add any duplicates"
    print("✓ No duplicate FHRSIDs were added")
    
    # Scenario 3: Mixed - some new, some existing
    print("\n--- Scenario 3: Mixed (Some New, Some Existing) ---")
    existing_fhrsids = ['1001', '1002', '1003']
    mixed_api_fhrsids = ['1002', '2001', '1003', '2002']  # 2 existing, 2 new
    
    master_data = create_mock_master_data(existing_fhrsids)
    api_data = create_mock_api_data(mixed_api_fhrsids)
    
    print(f"Existing FHRSIDs in BigQuery: {existing_fhrsids}")
    print(f"FHRSIDs from API: {mixed_api_fhrsids}")
    
    new_restaurants = process_and_update_master_data(master_data, api_data)
    
    print(f"Result: {len(new_restaurants)} new restaurants will be added")
    new_fhrsids = [r['FHRSID'] for r in new_restaurants]
    print(f"New FHRSIDs to add: {new_fhrsids}")
    
    # Verify only the new ones are added
    assert len(new_restaurants) == 2, "Should add exactly 2 new restaurants"
    assert '2001' in new_fhrsids, "Should include FHRSID 2001"
    assert '2002' in new_fhrsids, "Should include FHRSID 2002"
    assert '1002' not in new_fhrsids, "Should not include existing FHRSID 1002"
    assert '1003' not in new_fhrsids, "Should not include existing FHRSID 1003"
    print("✓ Only new FHRSIDs were added, existing ones were filtered out")
    
    # Scenario 4: Duplicates within API batch
    print("\n--- Scenario 4: Duplicates Within API Batch ---")
    existing_fhrsids = ['1001', '1002']
    api_with_duplicates = ['2001', '2002', '2001', '2003', '2002']  # 2001 and 2002 appear twice
    
    master_data = create_mock_master_data(existing_fhrsids)
    api_data = create_mock_api_data(api_with_duplicates)
    
    print(f"Existing FHRSIDs in BigQuery: {existing_fhrsids}")
    print(f"FHRSIDs from API (with duplicates): {api_with_duplicates}")
    
    new_restaurants = process_and_update_master_data(master_data, api_data)
    
    print(f"Result: {len(new_restaurants)} new restaurants will be added")
    new_fhrsids = [r['FHRSID'] for r in new_restaurants]
    print(f"New FHRSIDs to add: {new_fhrsids}")
    
    # Verify duplicates within batch are handled
    assert len(new_restaurants) == 3, "Should add exactly 3 unique new restaurants"
    assert new_fhrsids.count('2001') == 1, "FHRSID 2001 should appear only once"
    assert new_fhrsids.count('2002') == 1, "FHRSID 2002 should appear only once"
    assert new_fhrsids.count('2003') == 1, "FHRSID 2003 should appear only once"
    print("✓ Duplicates within API batch were properly deduplicated")
    
    # Scenario 5: Empty API response
    print("\n--- Scenario 5: Empty API Response ---")
    existing_fhrsids = ['1001', '1002', '1003']
    empty_api_fhrsids = []
    
    master_data = create_mock_master_data(existing_fhrsids)
    api_data = create_mock_api_data(empty_api_fhrsids)
    
    print(f"Existing FHRSIDs in BigQuery: {existing_fhrsids}")
    print(f"FHRSIDs from API: {empty_api_fhrsids}")
    
    new_restaurants = process_and_update_master_data(master_data, api_data)
    
    print(f"Result: {len(new_restaurants)} new restaurants will be added")
    assert len(new_restaurants) == 0, "Should not add any restaurants from empty API"
    print("✓ Empty API response handled correctly")
    
    print("\n" + "=" * 80)
    print("All deduplication tests passed successfully! ✓")
    print("=" * 80)
    
    print("\nSummary:")
    print("- The system correctly identifies and filters out existing FHRSIDs")
    print("- Only new FHRSIDs are added to the database")
    print("- Each new FHRSID gets a 'first_seen' date set to today")
    print("- Duplicates within the same API batch are properly handled")
    print("- The system prevents duplicate entries in BigQuery")

def test_column_sanitization():
    """Test that column names are properly sanitized for BigQuery."""
    print("\n" + "=" * 80)
    print("Testing Column Name Sanitization")
    print("=" * 80)
    
    test_cases = [
        ('FHRSID', 'fhrsid'),
        ('Geocode.Latitude', 'geocodelatitude'),
        ('Geocode.Longitude', 'geocodelongitude'),
        ('Scores.Hygiene', 'scoreshygiene'),
        ('NewRatingPending', 'newratingpending'),
        ('first_seen', 'first_seen'),
        ('manual_review', 'manual_review'),
        ('AddressLine1', 'addressline1'),
        ('BusinessName', 'businessname'),
        ('LocalAuthorityName', 'localauthorityname')
    ]
    
    print("\nColumn name sanitization tests:")
    for original, expected in test_cases:
        sanitized = sanitize_column_name(original)
        status = "✓" if sanitized == expected else "✗"
        print(f"  {status} '{original}' -> '{sanitized}' (expected: '{expected}')")
        assert sanitized == expected, f"Sanitization failed for '{original}'"
    
    print("\n✓ All column sanitization tests passed")

if __name__ == "__main__":
    # Suppress Streamlit messages during testing
    import sys
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # Run tests with output suppression for Streamlit messages
    with redirect_stderr(io.StringIO()):
        test_deduplication_scenarios()
        test_column_sanitization()
    
    print("\n🎉 All tests completed successfully!")
    print("\nThe deduplication system is working correctly:")
    print("  • Existing FHRSIDs are properly identified and filtered")
    print("  • Only new FHRSIDs are added to BigQuery")
    print("  • Each new record gets a 'first_seen' date")
    print("  • No duplicates are created in the database")