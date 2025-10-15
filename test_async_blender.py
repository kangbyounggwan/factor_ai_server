"""
Test Blender processing using the exact async flow from the API.
This simulates what happens when modelling_api.py calls Blender.
"""
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (same as main.py does)
load_dotenv()

from blender_processor import process_model_with_blender

# Setup logging to see everything
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger("uvicorn.error")


async def test_async_blender():
    """Test Blender processing with the exact async pattern used in the API."""
    print("=" * 60)
    print("Testing Async Blender Processing (API simulation)")
    print("=" * 60)

    # Use the same GLB file that worked in manual test
    test_glb = Path(r"output\model_0199e7e8-0117-74f9-9e9e-78cdbed56176.glb")

    if not test_glb.exists():
        print(f"ERROR: Test GLB file not found: {test_glb}")
        return

    print(f"\nInput GLB: {test_glb}")
    print(f"   Size: {test_glb.stat().st_size / 1024:.2f} KB")
    print("\nStarting async Blender processing...")
    print("(This uses the exact same code path as the API)")
    print("-" * 60)

    try:
        # Call the same function that modelling_api.py calls
        result = await process_model_with_blender(str(test_glb), "test_async_run")

        print("\n" + "=" * 60)
        print("SUCCESS: Async Blender Processing Completed!")
        print("=" * 60)

        cleaned_glb = Path(result["cleaned_glb_path"])
        stl_file = Path(result["stl_path"])

        if cleaned_glb.exists():
            print(f"Cleaned GLB: {cleaned_glb}")
            print(f"   Size: {cleaned_glb.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("ERROR: Cleaned GLB not found!")

        if stl_file.exists():
            print(f"STL File: {stl_file}")
            print(f"   Size: {stl_file.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("ERROR: STL not found!")

        print("\nAll files created successfully!")

    except Exception as e:
        print("\n" + "=" * 60)
        print("FAILED: Async Blender Processing Error")
        print("=" * 60)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("\nFull traceback:")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_async_blender())
