"""
Test all Cura printer definitions to check bed temperature extraction.

This script tests slicing with all available Cura printer definitions
and reports which ones support heated bed (bed_temp extraction).
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from cura_processor import (
    convert_stl_to_gcode_with_printer_name,
    parse_gcode_metadata
)

# Configuration
CURA_DEFINITIONS_DIR = Path(r"C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions")
OUTPUT_DIR = Path("./output")
TEST_GLB_FILE = None  # Will use existing file from output directory

# Test settings
TEST_SETTINGS = {
    "layer_height": "0.2",
    "infill_sparse_density": "15",
    "wall_line_count": "2",
    "material_print_temperature": "200",
    "material_bed_temperature": "60",
}


def find_test_glb():
    """Find a GLB file in the output directory for testing."""
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
    # e.g., "ultimaker2.def.json" -> "ultimaker2"
    stem = def_path.stem  # Gets "ultimaker2.def"
    return stem.replace('.def', '')


async def test_printer_definition(printer_name, test_stl, output_dir):
    """
    Test a single printer definition.

    Returns:
        dict: Test result with printer_name, success, bed_temp, etc.
    """
    result = {
        "printer_name": printer_name,
        "success": False,
        "bed_temp": None,
        "nozzle_temp": None,
        "error": None,
        "gcode_file": None,
    }

    try:
        # Generate unique gcode filename
        gcode_filename = f"test_{printer_name}_{int(datetime.now().timestamp())}.gcode"
        gcode_path = output_dir / gcode_filename

        # Run slicing
        success = await convert_stl_to_gcode_with_printer_name(
            stl_path=str(test_stl.resolve()),
            gcode_path=str(gcode_path.resolve()),
            printer_name=printer_name,
            custom_settings=TEST_SETTINGS,
        )

        if not success or not gcode_path.exists():
            result["error"] = "Slicing failed"
            return result

        result["success"] = True
        result["gcode_file"] = str(gcode_path)

        # Parse metadata
        metadata = parse_gcode_metadata(str(gcode_path))
        result["bed_temp"] = metadata.get("bed_temp")
        result["nozzle_temp"] = metadata.get("nozzle_temp")

        # Clean up gcode file
        try:
            gcode_path.unlink()
        except:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


async def main():
    """Main test function."""
    print("="*80)
    print("🧪 Cura Printer Definitions Test")
    print("="*80)

    # Find test file
    test_file = find_test_glb()
    if not test_file:
        print("❌ No test file found in output directory")
        print("   Please upload a GLB or STL file first")
        return

    print(f"📦 Test file: {test_file.name}")

    # If GLB, convert to STL first
    test_stl = test_file
    if test_file.suffix.lower() in ['.glb', '.gltf']:
        import trimesh
        print(f"🔄 Converting {test_file.suffix} to STL...")
        mesh = trimesh.load(test_file)
        test_stl = OUTPUT_DIR / f"test_model_{int(datetime.now().timestamp())}.stl"
        mesh.export(test_stl, file_type='stl')
        print(f"✅ Converted to: {test_stl.name}")

    # Get all printer definitions
    all_defs = get_all_printer_definitions()
    if not all_defs:
        return

    # Ask user for test mode
    print()
    print("Test modes:")
    print("  1. Quick test (10 random printers)")
    print("  2. Common printers (Ender, Prusa, Ultimaker, etc.)")
    print("  3. Full test (all 670 printers - takes ~1 hour)")

    mode = input("\nSelect mode [1/2/3]: ").strip()

    printers_to_test = []

    if mode == "1":
        # Quick test: 10 random printers
        import random
        random.shuffle(all_defs)
        printers_to_test = [extract_printer_name(d) for d in all_defs[:10]]

    elif mode == "2":
        # Common printers
        common_names = [
            "creality_ender3", "creality_ender3pro", "creality_ender5",
            "creality_cr10", "creality_cr10s",
            "anycubic_i3_mega", "anycubic_4max",
            "prusa_i3", "prusa_mk3",
            "ultimaker2", "ultimaker3", "ultimaker_s5",
            "artillery_sidewinder_x1",
            "flsun_qq",
            "makerbot_replicator2",
        ]
        # Filter to only existing printers
        all_printer_names = {extract_printer_name(d) for d in all_defs}
        printers_to_test = [p for p in common_names if p in all_printer_names]

    elif mode == "3":
        # Full test
        printers_to_test = [extract_printer_name(d) for d in all_defs]
        confirm = input(f"⚠️  This will test {len(printers_to_test)} printers. Continue? [y/N]: ")
        if confirm.lower() != 'y':
            print("❌ Test cancelled")
            return
    else:
        print("❌ Invalid mode")
        return

    print()
    print(f"🚀 Testing {len(printers_to_test)} printers...")
    print("="*80)

    # Run tests
    results = []
    for i, printer_name in enumerate(printers_to_test, 1):
        print(f"[{i}/{len(printers_to_test)}] Testing: {printer_name}...", end=" ")

        result = await test_printer_definition(printer_name, test_stl, OUTPUT_DIR)
        results.append(result)

        if result["success"]:
            bed_status = f"Bed={result['bed_temp']}°C" if result['bed_temp'] else "No bed"
            print(f"✅ {bed_status}")
        else:
            print(f"❌ {result['error']}")

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
    print(f"✅ Successful: {len(successful)}")
    print(f"   - With bed temp: {len(with_bed_temp)}")
    print(f"   - Without bed temp: {len(without_bed_temp)}")
    print(f"❌ Failed: {len(failed)}")
    print()

    # Printers with bed temperature support
    if with_bed_temp:
        print("🔥 Printers WITH heated bed support:")
        for r in with_bed_temp[:20]:  # Show first 20
            print(f"   - {r['printer_name']}: {r['bed_temp']}°C")
        if len(with_bed_temp) > 20:
            print(f"   ... and {len(with_bed_temp) - 20} more")
        print()

    # Printers without bed temperature
    if without_bed_temp:
        print("❄️  Printers WITHOUT heated bed support:")
        for r in without_bed_temp[:20]:  # Show first 20
            print(f"   - {r['printer_name']}")
        if len(without_bed_temp) > 20:
            print(f"   ... and {len(without_bed_temp) - 20} more")
        print()

    # Failed printers
    if failed:
        print("❌ Failed printers:")
        for r in failed[:10]:
            print(f"   - {r['printer_name']}: {r['error']}")
        if len(failed) > 10:
            print(f"   ... and {len(failed) - 10} more")
        print()

    # Save detailed report to JSON
    report_file = OUTPUT_DIR / f"printer_test_report_{int(datetime.now().timestamp())}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "test_file": str(test_file),
            "total_tested": len(results),
            "successful": len(successful),
            "with_bed_temp": len(with_bed_temp),
            "without_bed_temp": len(without_bed_temp),
            "failed": len(failed),
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"📄 Detailed report saved to: {report_file.name}")

    # Clean up test STL if we created it
    if test_stl != test_file and test_stl.exists():
        try:
            test_stl.unlink()
            print(f"🗑️  Cleaned up temporary STL: {test_stl.name}")
        except:
            pass

    print()
    print("="*80)
    print("✅ Test completed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
