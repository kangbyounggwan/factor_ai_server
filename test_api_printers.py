"""
Test all Cura printer definitions using the actual API endpoint.

This script tests the upload-stl-and-slice API with different printer definitions
to check which printers support heated bed temperature extraction.
"""

import requests
import json
import time
from pathlib import Path
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:7000"
CURA_DEFINITIONS_DIR = Path(r"C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions")
OUTPUT_DIR = Path("./output")

# Test settings
TEST_CURA_SETTINGS = {
    "layer_height": "0.2",
    "line_width": "0.4",
    "infill_sparse_density": "15",
    "wall_line_count": "2",
    "top_layers": "4",
    "bottom_layers": "4",
    "speed_print": "50",
    "support_enable": "true",
    "support_angle": "50",
    "adhesion_type": "none",
    "material_diameter": "1.75",
    "material_flow": "100",
}


def find_test_file():
    """Find a test GLB or STL file in the output directory."""
    for file in OUTPUT_DIR.glob("*.glb"):
        return file
    for file in OUTPUT_DIR.glob("*.stl"):
        return file
    return None


def get_all_printer_definitions():
    """Get all printer definition files."""
    if not CURA_DEFINITIONS_DIR.exists():
        print(f"❌ Definitions directory not found: {CURA_DEFINITIONS_DIR}")
        return []

    defs = list(CURA_DEFINITIONS_DIR.glob("*.def.json"))
    print(f"📁 Found {len(defs)} printer definitions")
    return defs


def extract_printer_name(def_path):
    """Extract printer name from definition file path."""
    stem = def_path.stem  # Gets "creality_ender3.def"
    return stem.replace('.def', '')


def test_printer_via_api(test_file, printer_name, debug=False):
    """
    Test a single printer by uploading file to API.

    Args:
        test_file: Path to GLB/STL file
        printer_name: Name of printer to test
        debug: If True, print full response

    Returns:
        dict: Test result with printer_name, success, bed_temp, etc.
    """
    result = {
        "printer_name": printer_name,
        "success": False,
        "bed_temp": None,
        "nozzle_temp": None,
        "error": None,
        "response_time": None,
    }

    try:
        start_time = time.time()

        # Prepare request
        url = f"{API_BASE_URL}/v1/process/upload-stl-and-slice"

        with open(test_file, 'rb') as f:
            files = {
                'file': (test_file.name, f, 'application/octet-stream')
            }

            data = {
                'printer_name': printer_name,
                'cura_settings_json': json.dumps(TEST_CURA_SETTINGS)
            }

            # Send request
            response = requests.post(url, files=files, data=data, timeout=120)

        elapsed = time.time() - start_time
        result["response_time"] = round(elapsed, 2)

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
            return result

        # Parse response
        resp_data = response.json()

        if debug:
            print(f"\n[DEBUG] Response for {printer_name}:")
            print(json.dumps(resp_data, indent=2))

        # Check for error in response
        if resp_data.get("status") == "error":
            error_msg = resp_data.get("error") or resp_data.get("message") or "Unknown error"
            result["error"] = error_msg[:100]
            return result

        # Success - extract metadata from data.gcode_metadata
        if resp_data.get("status") == "ok" and "data" in resp_data:
            metadata = resp_data["data"].get("gcode_metadata", {})

            result["success"] = True
            result["bed_temp"] = metadata.get("bed_temp")
            result["nozzle_temp"] = metadata.get("nozzle_temp")
        else:
            result["error"] = "Unexpected response format"

    except requests.exceptions.Timeout:
        result["error"] = "Request timeout (>120s)"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection failed - is server running?"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    """Main test function."""
    print("="*80)
    print("🧪 Cura Printer Definitions API Test")
    print("="*80)

    # Check if server is running
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        print(f"✅ Server is running at {API_BASE_URL}")
    except:
        print(f"❌ Server is not running at {API_BASE_URL}")
        print("   Please start the server first: uvicorn main:app --reload --host 0.0.0.0 --port 7000")
        return

    # Find test file
    test_file = find_test_file()
    if not test_file:
        print("❌ No test file found in output directory")
        print("   Please upload a GLB or STL file first")
        return

    print(f"📦 Test file: {test_file.name} ({test_file.stat().st_size / 1024:.1f} KB)")

    # Get all printer definitions
    all_defs = get_all_printer_definitions()
    if not all_defs:
        return

    # Ask user for test mode
    print()
    print("Test modes:")
    print("  1. Quick test (10 printers)")
    print("  2. Common printers (Ender, Prusa, Ultimaker, etc.)")
    print("  3. Full test (all 670 printers - may take 2+ hours)")

    mode = input("\nSelect mode [1/2/3]: ").strip()

    printers_to_test = []

    if mode == "1":
        # Quick test: specific known printers
        quick_printers = [
            "creality_ender3",
            "creality_ender3pro",
            "ultimaker2",
            "ultimaker3",
            "prusa_i3",
            "anycubic_i3_mega",
            "creality_cr10",
            "fdmprinter",
            "artillery_sidewinder_x1",
            "flsun_qq",
        ]
        all_printer_names = {extract_printer_name(d) for d in all_defs}
        printers_to_test = [p for p in quick_printers if p in all_printer_names]

    elif mode == "2":
        # Common printers
        common_names = [
            "creality_ender3", "creality_ender3pro", "creality_ender5",
            "creality_cr10", "creality_cr10s", "creality_cr10spro",
            "anycubic_i3_mega", "anycubic_4max", "anycubic_chiron",
            "prusa_i3", "prusa_mk3", "prusa_mk3s",
            "ultimaker2", "ultimaker2plus", "ultimaker3",
            "ultimaker_s3", "ultimaker_s5",
            "artillery_sidewinder_x1", "artillery_genius",
            "flsun_qq", "flsun_qqs",
            "makerbot_replicator2",
            "anet_a8", "anet_et4",
            "tevo_tornado",
            "fdmprinter",
        ]
        all_printer_names = {extract_printer_name(d) for d in all_defs}
        printers_to_test = [p for p in common_names if p in all_printer_names]

    elif mode == "3":
        # Full test
        printers_to_test = [extract_printer_name(d) for d in all_defs]
        confirm = input(f"⚠️  This will test {len(printers_to_test)} printers (2+ hours). Continue? [y/N]: ")
        if confirm.lower() != 'y':
            print("❌ Test cancelled")
            return
    else:
        print("❌ Invalid mode")
        return

    print()
    print(f"🚀 Testing {len(printers_to_test)} printers via API...")
    print("="*80)

    # Run tests
    results = []
    debug_mode = (mode == "1")  # Enable debug for quick test

    for i, printer_name in enumerate(printers_to_test, 1):
        print(f"[{i}/{len(printers_to_test)}] {printer_name:40s} ", end="", flush=True)

        result = test_printer_via_api(test_file, printer_name, debug=(debug_mode and i <= 2))
        results.append(result)

        if result["success"]:
            bed = f"Bed={result['bed_temp']}°C" if result['bed_temp'] else "No bed"
            nozzle = f"Nozzle={result['nozzle_temp']}°C" if result['nozzle_temp'] else ""
            time_str = f"({result['response_time']}s)"
            print(f"✅ {bed:12s} {nozzle:15s} {time_str}")
        else:
            error_msg = result['error'][:40] if result['error'] else "Unknown error"
            print(f"❌ {error_msg}")

        # Small delay to avoid overwhelming the server
        time.sleep(0.5)

    # Generate report
    print()
    print("="*80)
    print("📊 TEST RESULTS")
    print("="*80)

    successful = [r for r in results if r["success"]]
    with_bed_temp = [r for r in results if r["success"] and r["bed_temp"] is not None]
    without_bed_temp = [r for r in results if r["success"] and r["bed_temp"] is None]
    failed = [r for r in results if not r["success"]]

    print(f"Total tested: {len(results)}")
    print(f"✅ Successful: {len(successful)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"   - With bed temp: {len(with_bed_temp)}")
    print(f"   - Without bed temp: {len(without_bed_temp)}")
    print(f"❌ Failed: {len(failed)} ({len(failed)/len(results)*100:.1f}%)")

    if successful:
        avg_time = sum(r["response_time"] for r in successful) / len(successful)
        print(f"⏱️  Average response time: {avg_time:.1f}s")
    print()

    # Printers with bed temperature support
    if with_bed_temp:
        print("🔥 Printers WITH heated bed support:")
        for r in sorted(with_bed_temp, key=lambda x: x["printer_name"])[:30]:
            print(f"   - {r['printer_name']:40s} Bed={r['bed_temp']}°C")
        if len(with_bed_temp) > 30:
            print(f"   ... and {len(with_bed_temp) - 30} more")
        print()

    # Printers without bed temperature
    if without_bed_temp:
        print("❄️  Printers WITHOUT heated bed support:")
        for r in sorted(without_bed_temp, key=lambda x: x["printer_name"])[:30]:
            print(f"   - {r['printer_name']}")
        if len(without_bed_temp) > 30:
            print(f"   ... and {len(without_bed_temp) - 30} more")
        print()

    # Failed printers
    if failed:
        print("❌ Failed printers (first 20):")
        for r in sorted(failed, key=lambda x: x["printer_name"])[:20]:
            print(f"   - {r['printer_name']:40s} {r['error'][:50]}")
        if len(failed) > 20:
            print(f"   ... and {len(failed) - 20} more")
        print()

    # Save detailed report to JSON
    report_file = OUTPUT_DIR / f"api_test_report_{int(datetime.now().timestamp())}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "test_file": str(test_file),
            "api_url": API_BASE_URL,
            "total_tested": len(results),
            "successful": len(successful),
            "with_bed_temp": len(with_bed_temp),
            "without_bed_temp": len(without_bed_temp),
            "failed": len(failed),
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"📄 Detailed report saved to: {report_file.name}")
    print()
    print("="*80)
    print("✅ Test completed!")
    print("="*80)


if __name__ == "__main__":
    main()
