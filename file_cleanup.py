"""
Local File Cleanup Helper

Automatically removes local files after successful Supabase upload
"""
import os
import logging
from typing import List, Optional

logger = logging.getLogger("uvicorn.error")


def cleanup_local_files(*file_paths: Optional[str], force: bool = False) -> int:
    """
    Delete local files safely

    Args:
        *file_paths: Variable number of file paths to delete
        force: If True, don't log warnings for missing files

    Returns:
        int: Number of files successfully deleted
    """
    deleted_count = 0

    for file_path in file_paths:
        if not file_path:
            continue

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[Cleanup] Deleted local file: {os.path.basename(file_path)}")
                deleted_count += 1
            elif not force:
                logger.warning(f"[Cleanup] File not found (already deleted?): {file_path}")

        except Exception as e:
            logger.error(f"[Cleanup] Failed to delete {file_path}: {e}")

    return deleted_count


def cleanup_model_files(
    glb_path: Optional[str] = None,
    stl_path: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    source_image_path: Optional[str] = None
) -> dict:
    """
    Cleanup all files related to a generated model

    Args:
        glb_path: Path to GLB file
        stl_path: Path to STL file
        thumbnail_path: Path to thumbnail image
        source_image_path: Path to source image (for image-to-3d)

    Returns:
        dict: Cleanup results with counts
    """
    files_to_delete = []

    if glb_path:
        files_to_delete.append(glb_path)

    if stl_path:
        files_to_delete.append(stl_path)

    if thumbnail_path:
        files_to_delete.append(thumbnail_path)

    if source_image_path:
        files_to_delete.append(source_image_path)

    deleted_count = cleanup_local_files(*files_to_delete)

    result = {
        "total_files": len([f for f in files_to_delete if f]),
        "deleted_count": deleted_count,
        "files": {
            "glb": "deleted" if glb_path and not os.path.exists(glb_path) else "kept",
            "stl": "deleted" if stl_path and not os.path.exists(stl_path) else "kept",
            "thumbnail": "deleted" if thumbnail_path and not os.path.exists(thumbnail_path) else "kept",
            "source": "deleted" if source_image_path and not os.path.exists(source_image_path) else "kept",
        }
    }

    logger.info(f"[Cleanup] Model files cleanup: {deleted_count}/{result['total_files']} files deleted")

    return result


def cleanup_old_files(directory: str, max_age_hours: int = 24) -> int:
    """
    Cleanup files older than specified age in a directory

    Args:
        directory: Directory path to scan
        max_age_hours: Maximum age in hours

    Returns:
        int: Number of files deleted
    """
    import time

    if not os.path.exists(directory):
        logger.warning(f"[Cleanup] Directory not found: {directory}")
        return 0

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0

    try:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)

            if not os.path.isfile(file_path):
                continue

            file_age = current_time - os.path.getmtime(file_path)

            if file_age > max_age_seconds:
                try:
                    os.remove(file_path)
                    logger.info(f"[Cleanup] Deleted old file: {filename} (age: {file_age / 3600:.1f}h)")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"[Cleanup] Failed to delete {filename}: {e}")

    except Exception as e:
        logger.error(f"[Cleanup] Error scanning directory {directory}: {e}")

    logger.info(f"[Cleanup] Deleted {deleted_count} old files from {directory}")
    return deleted_count


if __name__ == "__main__":
    # Test cleanup functions
    import tempfile

    print("Testing file cleanup...")

    # Create temp files
    with tempfile.NamedTemporaryFile(delete=False, suffix=".glb") as f:
        test_glb = f.name
        f.write(b"test glb content")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as f:
        test_stl = f.name
        f.write(b"test stl content")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
        test_thumb = f.name
        f.write(b"test thumbnail")

    print(f"Created test files:")
    print(f"  GLB: {test_glb}")
    print(f"  STL: {test_stl}")
    print(f"  Thumbnail: {test_thumb}")

    # Test cleanup
    result = cleanup_model_files(
        glb_path=test_glb,
        stl_path=test_stl,
        thumbnail_path=test_thumb
    )

    print(f"\nCleanup result: {result}")

    # Verify deletion
    exists = [
        os.path.exists(test_glb),
        os.path.exists(test_stl),
        os.path.exists(test_thumb)
    ]

    if any(exists):
        print("❌ Some files were not deleted")
    else:
        print("✅ All files deleted successfully")
