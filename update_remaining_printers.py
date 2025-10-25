"""
Update remaining printers with null cura_engine_support using filename matching.
"""

import json
from pathlib import Path
from supabase import create_client, Client

# Supabase configuration
SUPABASE_URL = "https://ecmrkjwsjkthurwljhvp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"

# Test report file
TEST_REPORT = Path("./output/api_test_report_1761392020.json")


def main():
    print("="*80)
    print("[UPDATE] Remaining Printers via Filename Matching")
    print("="*80)

    # 1. Load test results
    print("\n Loading test results...")
    with open(TEST_REPORT, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Create lookup: filename -> test result
    test_lookup = {}
    for result in data['results']:
        printer_name = result['printer_name']
        # Convert printer_name to filename (e.g., "creality_ender3" -> "creality_ender3.def.json")
        filename = f"{printer_name}.def.json"
        test_lookup[filename] = {
            'printer_name': printer_name,
            'success': result['success'],
            'bed_temp_support': result.get('bed_temp') is not None if result['success'] else False,
            'error': result.get('error')
        }

    print(f"   Loaded {len(test_lookup)} test results")

    # 2. Connect to Supabase
    print("\n Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("   Connected")

    # 3. Get printers with null cura_engine_support
    print("\n Fetching printers with null cura_engine_support...")
    response = supabase.table('manufacturing_printers').select(
        'id, display_name, filename'
    ).is_('cura_engine_support', 'null').execute()

    null_printers = response.data
    print(f"   Found {len(null_printers)} printers\n")

    # 4. Match by filename
    print("="*80)
    print(" Matching by filename...")
    print("="*80)

    matches = []
    unmatched = []

    for printer in null_printers:
        db_id = printer['id']
        db_name = printer['display_name']
        filename = printer.get('filename')

        if not filename:
            print(f"[NO FILENAME] {db_name}")
            unmatched.append(printer)
            continue

        if filename in test_lookup:
            test_info = test_lookup[filename]
            matches.append({
                'db_id': db_id,
                'db_name': db_name,
                'filename': filename,
                'test_name': test_info['printer_name'],
                'cura_engine_support': test_info['success'],
                'bed_temp_support': test_info['bed_temp_support'],
                'error': test_info['error']
            })
            status = "[OK]" if test_info['success'] else "[FAIL]"
            print(f"{status} {db_name:50s} -> {test_info['printer_name']:40s} (Support: {test_info['success']})")
        else:
            print(f"[NO MATCH] {db_name:50s} (filename: {filename})")
            unmatched.append(printer)

    print("="*80)
    print(f"\n Matching Summary:")
    print(f"   - Matched: {len(matches)}")
    print(f"   - Unmatched: {len(unmatched)}")

    if not matches:
        print("\n No matches found. Exiting.")
        return

    # 5. Generate SQL
    print("\n Generating SQL statements...")
    sql_file = Path("./output/update_remaining_printers.sql")

    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write("-- Update remaining printers with null cura_engine_support\n")
        f.write(f"-- Matched by filename\n")
        f.write(f"-- Total updates: {len(matches)}\n\n")

        supported = [m for m in matches if m['cura_engine_support']]
        unsupported = [m for m in matches if not m['cura_engine_support']]

        f.write(f"-- Supported printers: {len(supported)}\n")
        f.write("-- " + "="*70 + "\n\n")

        for match in supported:
            f.write(f"-- {match['db_name']} (filename: {match['filename']})\n")
            f.write(f"UPDATE manufacturing_printers SET cura_engine_support = true WHERE id = '{match['db_id']}';\n\n")

        f.write(f"\n\n-- Unsupported printers: {len(unsupported)}\n")
        f.write("-- " + "="*70 + "\n\n")

        for match in unsupported:
            f.write(f"-- {match['db_name']} (filename: {match['filename']}) - Error: {match['error']}\n")
            f.write(f"UPDATE manufacturing_printers SET cura_engine_support = false WHERE id = '{match['db_id']}';\n\n")

    print(f"   SQL file saved: {sql_file}")

    # 6. Summary
    print("\n" + "="*80)
    print(" SUMMARY")
    print("="*80)
    print(f"Total null printers: {len(null_printers)}")
    print(f"  - Matched by filename: {len(matches)}")
    print(f"    - Supported: {len(supported)}")
    print(f"    - Unsupported: {len(unsupported)}")
    print(f"  - No match found: {len(unmatched)}")

    if unmatched:
        print(f"\n Unmatched printers (first 20):")
        for p in unmatched[:20]:
            print(f"   - {p['display_name']:50s} (filename: {p.get('filename', 'N/A')})")
        if len(unmatched) > 20:
            print(f"   ... and {len(unmatched) - 20} more")

    print(f"\n SQL file ready: {sql_file}")
    print("\n Execute this file in Supabase SQL Editor to update the database.")
    print("="*80)


if __name__ == "__main__":
    main()
