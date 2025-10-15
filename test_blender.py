"""
Test Blender processing directly
"""
import asyncio
import os
import sys
from pathlib import Path

# Set environment variables
os.environ['BLENDER_PATH'] = r'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
os.environ['OUTPUT_DIR'] = r'.\output'

from blender_processor import process_model_with_blender


async def test_blender():
    """Test Blender processing with an existing GLB file."""

    # Use an existing GLB file
    test_glb = Path(r"output\model_0199e7e8-0117-74f9-9e9e-78cdbed56176.glb")

    if not test_glb.exists():
        print(f"ERROR: Test file not found: {test_glb}")
        print(f"   Absolute path: {test_glb.absolute()}")
        return

    print("=" * 60)
    print("Testing Blender Processing")
    print("=" * 60)
    print(f"Input GLB: {test_glb}")
    print(f"   Size: {test_glb.stat().st_size / 1024:.2f} KB")
    print()

    try:
        print("Starting Blender processing...")
        result = await process_model_with_blender(str(test_glb), "test_run")

        print("\n" + "=" * 60)
        print("SUCCESS: Blender Processing Successful!")
        print("=" * 60)
        print(f"Cleaned GLB: {result['cleaned_glb_path']}")
        print(f"STL File: {result['stl_path']}")

        # Check file sizes
        cleaned_glb = Path(result['cleaned_glb_path'])
        stl_file = Path(result['stl_path'])

        if cleaned_glb.exists():
            print(f"   Cleaned GLB size: {cleaned_glb.stat().st_size / 1024 / 1024:.2f} MB")

        if stl_file.exists():
            print(f"   STL size: {stl_file.stat().st_size / 1024 / 1024:.2f} MB")

        print("\nAll files created successfully!")

    except Exception as e:
        print("\n" + "=" * 60)
        print("ERROR: Blender Processing Failed!")
        print("=" * 60)
        print(f"Error: {e}")

        # Try to find and display log
        log_file = Path("output/blender_log_cleaned_test_run.txt")
        if log_file.exists():
            print(f"\nLog file found: {log_file}")
            print("\n--- Last 30 lines of log ---")
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                for line in lines[-30:]:
                    print(line.rstrip())
        else:
            print(f"\nWARNING: Log file not found: {log_file}")

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_blender())
