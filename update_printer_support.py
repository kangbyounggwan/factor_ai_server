"""
Update manufacturing_printers table with CuraEngine support status.

This script reads the API test results and updates the database
to reflect which printers are supported by CuraEngine.
"""

import os
import json
from pathlib import Path
from supabase import create_client, Client

# Supabase configuration
SUPABASE_URL = "https://ecmrkjwsjkthurwljhvp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"

# Test report file
TEST_REPORT = Path("./output/api_test_report_1761392020.json")


def load_test_results():
    """Load test results from JSON file."""
    with open(TEST_REPORT, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get('results', [])
    print(f" Loaded {len(results)} test results")

    # Create lookup dictionary: printer_name -> success status
    printer_status = {}
    for r in results:
        printer_name = r['printer_name']
        printer_status[printer_name] = {
            'success': r['success'],
            'bed_temp_support': r.get('bed_temp') is not None if r['success'] else False,
            'error': r.get('error')
        }

    return printer_status


def fetch_db_printers(supabase: Client):
    """Fetch all printers from manufacturing_printers table."""
    print("\n Fetching printers from database...")

    response = supabase.table('manufacturing_printers').select('*').execute()

    printers = response.data
    print(f" Found {len(printers)} printers in database\n")

    return printers


def match_printers(db_printers, test_results):
    """
    Match database printers with test results.

    Matching strategy:
    1. Exact match on display_name (lowercase, remove spaces/underscore/dash)
    2. Extract key parts (manufacturer + model) and match
    3. Fuzzy match on shortened names
    """
    matches = []
    unmatched_db = []

    # Normalize test result keys for easier matching
    test_keys_normalized = {}
    test_keys_parts = {}  # Store key parts for fuzzy matching

    for printer_name, status in test_results.items():
        # Normalize: lowercase, replace underscore/dash with space
        normalized = printer_name.lower().replace('_', ' ').replace('-', ' ')
        test_keys_normalized[normalized] = (printer_name, status)

        # Extract parts (e.g., "creality ender3" -> ["creality", "ender3"])
        parts = normalized.split()
        test_keys_parts[printer_name] = parts

    print(" Matching database printers with test results...")
    print("="*80)

    for db_printer in db_printers:
        db_id = db_printer.get('id')
        db_name = db_printer.get('display_name', '')
        db_normalized = db_name.lower().replace('_', ' ').replace('-', ' ')

        # Try exact match first
        found = False
        if db_normalized in test_keys_normalized:
            printer_name, status = test_keys_normalized[db_normalized]
            matches.append({
                'db_id': db_id,
                'db_name': db_name,
                'test_name': printer_name,
                'cura_engine_support': status['success'],
                'bed_temp_support': status['bed_temp_support'],
                'error': status['error']
            })
            found = True
            print(f" {db_name:40s} -> {printer_name:40s} (Support: {status['success']})")

        if not found:
            # Try partial matching
            for normalized_key, (printer_name, status) in test_keys_normalized.items():
                # Check if db_name is in test name or vice versa
                if (db_normalized in normalized_key or
                    normalized_key in db_normalized or
                    # Remove common prefixes and try again
                    db_normalized.replace('creality ', '') in normalized_key or
                    db_normalized.replace('ultimaker ', '') in normalized_key):

                    matches.append({
                        'db_id': db_id,
                        'db_name': db_name,
                        'test_name': printer_name,
                        'cura_engine_support': status['success'],
                        'bed_temp_support': status['bed_temp_support'],
                        'error': status['error']
                    })
                    found = True
                    print(f" {db_name:40s} -> {printer_name:40s} (Support: {status['success']}) [partial]")
                    break

        if not found:
            unmatched_db.append({
                'db_id': db_id,
                'db_name': db_name
            })
            print(f" {db_name:40s} -> No match found")

    print("="*80)
    print(f"\n Matching Summary:")
    print(f"   - Matched: {len(matches)}")
    print(f"   - Unmatched: {len(unmatched_db)}")

    return matches, unmatched_db


def generate_sql_updates(matches):
    """Generate SQL UPDATE statements."""
    print("\n Generating SQL UPDATE statements...\n")

    sql_statements = []

    for match in matches:
        db_id = match['db_id']
        support = 'true' if match['cura_engine_support'] else 'false'

        sql = f"UPDATE manufacturing_printers SET cura_engine_support = {support} WHERE id = '{db_id}';"
        sql_statements.append(sql)

    return sql_statements


def update_database(supabase: Client, matches):
    """Update database with CuraEngine support status."""
    print("\n Updating database...")
    print("="*80)

    success_count = 0
    error_count = 0

    for match in matches:
        db_id = match['db_id']
        db_name = match['db_name']
        support = match['cura_engine_support']

        try:
            response = supabase.table('manufacturing_printers').update({
                'cura_engine_support': support
            }).eq('id', db_id).execute()

            # Check if update was successful
            if response.data and len(response.data) > 0:
                status = "[OK]" if support else "[OK]"
                print(f"{status} Updated: {db_name:40s} (ID: {db_id}) -> {support}")
                success_count += 1
            else:
                print(f"[FAIL] No rows updated for {db_name} (ID: {db_id})")
                print(f"       Response: {response}")
                error_count += 1

        except Exception as e:
            print(f"[ERROR] updating {db_name}: {e}")
            error_count += 1

    print("="*80)
    print(f"\n Update Summary:")
    print(f"   - Successfully updated: {success_count}")
    print(f"   - Errors: {error_count}")

    return success_count, error_count


def export_sql_file(sql_statements, matches):
    """Export SQL statements to file for manual review."""
    output_file = Path("./output/update_printer_support.sql")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("-- Update manufacturing_printers table with CuraEngine support status\n")
        f.write(f"-- Generated from test results\n")
        f.write(f"-- Total updates: {len(sql_statements)}\n\n")

        # Group by support status
        supported = [m for m in matches if m['cura_engine_support']]
        unsupported = [m for m in matches if not m['cura_engine_support']]

        f.write(f"-- Supported printers: {len(supported)}\n")
        f.write("-- " + "="*70 + "\n\n")

        for match in supported:
            db_id = match['db_id']
            f.write(f"-- {match['db_name']} (test: {match['test_name']})\n")
            f.write(f"UPDATE manufacturing_printers SET cura_engine_support = true WHERE id = '{db_id}';\n\n")

        f.write(f"\n\n-- Unsupported printers: {len(unsupported)}\n")
        f.write("-- " + "="*70 + "\n\n")

        for match in unsupported:
            db_id = match['db_id']
            f.write(f"-- {match['db_name']} (test: {match['test_name']}) - Error: {match['error']}\n")
            f.write(f"UPDATE manufacturing_printers SET cura_engine_support = false WHERE id = '{db_id}';\n\n")

    print(f"\n SQL file exported to: {output_file}")
    return output_file


def main():
    """Main function."""
    print("="*80)
    print("[UPDATE] Printer CuraEngine Support Status")
    print("="*80)

    # 1. Load test results
    test_results = load_test_results()

    # 2. Connect to Supabase
    print("\n Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(" Connected to Supabase")

    # 3. Fetch database printers
    db_printers = fetch_db_printers(supabase)

    # 4. Match printers
    matches, unmatched = match_printers(db_printers, test_results)

    if not matches:
        print("\n No matches found. Cannot proceed with database update.")
        return

    # 5. Generate SQL statements
    sql_statements = generate_sql_updates(matches)

    # 6. Export SQL file
    sql_file = export_sql_file(sql_statements, matches)

    # 7. Ask user confirmation
    print("\n" + "="*80)
    print("  WARNING: This will update the database!")
    print(f"   - {len(matches)} printers will be updated")
    print(f"   - {len(unmatched)} printers have no test data")
    print()
    print(f" SQL file has been generated for review: {sql_file.name}")
    print("="*80)

    proceed = input("\nProceed with database update? [y/N]: ").strip().lower()

    if proceed == 'y':
        success, errors = update_database(supabase, matches)

        print("\n" + "="*80)
        print(" DATABASE UPDATE COMPLETED!")
        print("="*80)
        print(f"   - Updated: {success} printers")
        print(f"   - Errors: {errors}")
        print(f"   - Unmatched: {len(unmatched)}")

        # Show unmatched printers
        if unmatched:
            print("\n  Unmatched printers (not tested):")
            for p in unmatched[:20]:
                print(f"   - {p['db_name']}")
            if len(unmatched) > 20:
                print(f"   ... and {len(unmatched) - 20} more")
    else:
        print("\n Database update cancelled.")
        print(f" You can manually run the SQL file: {sql_file}")


if __name__ == "__main__":
    main()
