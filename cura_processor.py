import os
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("uvicorn.error")

# Environment variables for CuraEngine
CURAENGINE_PATH = os.getenv(
    "CURAENGINE_PATH",
    r"C:\Program Files\UltiMaker Cura 5.7.1\CuraEngine.exe"
).strip()

CURA_DEFINITION_JSON = os.getenv(
    "CURA_DEFINITION_JSON",
    r"C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\creality_ender3pro.def.json"
).strip()

# Default Cura settings
DEFAULT_CURA_SETTINGS = {
    "layer_height": "0.2",
    "line_width": "0.4",
    "wall_thickness": "0.8",
    "infill_sparse_density": "20",
    "support_enable": "false",
}


def is_curaengine_available() -> bool:
    """Check if CuraEngine is available and configured."""
    if not CURAENGINE_PATH:
        return False
    return Path(CURAENGINE_PATH).exists()


def run_curaengine(
    stl_path: Path,
    gcode_out: Path,
    curaengine_path: Optional[Path] = None,
    definition_json: Optional[Path] = None,
    extra_settings: Optional[Dict[str, str]] = None,
    verbose: bool = True,
) -> Path:
    """
    Run CuraEngine CLI to convert STL to G-code.

    Args:
        stl_path: Input STL file path
        gcode_out: Output G-code file path
        curaengine_path: CuraEngine.exe path (default from env)
        definition_json: Printer definition .def.json path (default from env)
        extra_settings: Additional settings dict like {"layer_height": "0.2"}
        verbose: Enable verbose output

    Returns:
        Path to the generated G-code file

    Raises:
        FileNotFoundError: If CuraEngine, definition, or STL not found
        RuntimeError: If CuraEngine execution fails
    """
    # Use defaults from environment if not provided
    curaengine = Path(curaengine_path) if curaengine_path else Path(CURAENGINE_PATH)
    definition = Path(definition_json) if definition_json else Path(CURA_DEFINITION_JSON)
    stl = Path(stl_path)
    gcode = Path(gcode_out)

    # Validate paths
    if not curaengine.exists():
        raise FileNotFoundError(f"CuraEngine not found: {curaengine}")
    if not definition.exists():
        raise FileNotFoundError(f"Definition JSON not found: {definition}")
    if not stl.exists():
        raise FileNotFoundError(f"STL not found: {stl}")

    # Create output directory
    gcode.parent.mkdir(parents=True, exist_ok=True)

    # Build command
    cmd = [
        str(curaengine),
        "slice",
    ]

    if verbose:
        cmd.append("-v")

    cmd.extend([
        "-j", str(definition),
        "-l", str(stl),
        "-o", str(gcode),
    ])

    # Add settings
    settings = DEFAULT_CURA_SETTINGS.copy()
    if extra_settings:
        settings.update(extra_settings)

    for k, v in settings.items():
        cmd.extend(["-s", f"{k}={v}"])

    logger.info("[CuraEngine] Running: %s", " ".join(cmd))

    # Execute CuraEngine
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"CuraEngine execution failed. Check path: {curaengine}"
        )

    # Log output
    if proc.stdout:
        logger.info("[CuraEngine] stdout: %s", proc.stdout)
    if proc.stderr:
        logger.warning("[CuraEngine] stderr: %s", proc.stderr)

    # Check return code
    if proc.returncode != 0:
        raise RuntimeError(f"CuraEngine failed with code {proc.returncode}")

    # Verify output file
    if not gcode.exists() or gcode.stat().st_size == 0:
        raise RuntimeError("G-code file not generated or empty")

    file_size_kb = gcode.stat().st_size / 1024
    logger.info("[CuraEngine] ✅ G-code saved: %s (%.2f KB)", gcode, file_size_kb)

    return gcode


async def convert_stl_to_gcode(
    stl_path: Path,
    gcode_path: Path,
    custom_settings: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Convert STL to G-code using CuraEngine (async wrapper).

    Args:
        stl_path: Path to input STL file
        gcode_path: Path to output G-code file
        custom_settings: Optional custom Cura settings

    Returns:
        bool: Success status
    """
    try:
        if not is_curaengine_available():
            logger.error("[CuraEngine] Not configured or not found")
            return False

        logger.info("[CuraEngine] Converting STL to G-code...")
        run_curaengine(
            stl_path=stl_path,
            gcode_out=gcode_path,
            extra_settings=custom_settings,
            verbose=True,
        )
        return True

    except Exception as e:
        logger.error("[CuraEngine] Conversion failed: %s", str(e))
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test execution
    logging.basicConfig(level=logging.INFO)

    test_stl = Path(r"C:\curaCLI\models\test.stl")
    test_gcode = Path(r"C:\curaCLI\models\test.gcode")

    if test_stl.exists():
        try:
            result = run_curaengine(
                stl_path=test_stl,
                gcode_out=test_gcode,
                extra_settings={
                    "layer_height": "0.2",
                    "infill_sparse_density": "20",
                    "roofing_layer_count": "1",
                },
                verbose=True,
            )
            print(f"✅ Success! G-code saved to: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print(f"❌ Test STL not found: {test_stl}")
