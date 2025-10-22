import os
import logging
import asyncio
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple, Dict

logger = logging.getLogger("uvicorn.error")

# Environment variables
CURAENGINE_PATH = os.getenv("CURAENGINE_PATH", "").strip()
CURA_DEFINITION_JSON = os.getenv("CURA_DEFINITION_JSON", "").strip()
CURA_TIMEOUT = int(os.getenv("CURA_TIMEOUT", "300"))  # 5 minutes default
CURA_VERBOSE = os.getenv("CURA_VERBOSE", "true").lower() == "true"

OUTPUT_DIR_RAW = os.getenv("OUTPUT_DIR", "./output").strip()
OUTPUT_DIR = Path(OUTPUT_DIR_RAW)

logger.info(
    "[CuraCfg] path=%s definition=%s timeout=%ds verbose=%s",
    CURAENGINE_PATH or "(not configured)",
    CURA_DEFINITION_JSON or "(not configured)",
    CURA_TIMEOUT,
    CURA_VERBOSE,
)


# Default slicing settings for 3D printing (PLA on Ender3 Pro)
DEFAULT_CURA_SETTINGS = {
    # Basic print settings
    "layer_height": "0.2",
    "wall_line_count": "3",
    "wall_thickness": "1.2",
    "top_thickness": "0.8",
    "bottom_thickness": "0.8",
    "top_layers": "4",
    "bottom_layers": "4",

    # Infill
    "infill_sparse_density": "20",
    "infill_pattern": "grid",
    "infill_overlap": "30",

    # Speed (mm/s)
    "speed_print": "50",
    "speed_infill": "60",
    "speed_wall": "40",
    "speed_wall_0": "30",  # Outer wall
    "speed_wall_x": "40",  # Inner walls
    "speed_topbottom": "40",
    "speed_travel": "150",
    "speed_layer_0": "20",  # First layer

    # Temperature (°C)
    "material_print_temperature": "200",
    "material_bed_temperature": "60",
    "material_print_temperature_layer_0": "205",
    "material_bed_temperature_layer_0": "60",

    # Support
    "support_enable": "false",
    "support_type": "buildplate",
    "support_angle": "50",
    "support_infill_rate": "20",
    "support_z_distance": "0.2",

    # Adhesion
    "adhesion_type": "skirt",
    "skirt_line_count": "3",
    "skirt_gap": "3",
    "brim_width": "8",

    # Retraction
    "retraction_enable": "true",
    "retraction_amount": "5",
    "retraction_speed": "45",
    "retraction_retract_speed": "45",
    "retraction_prime_speed": "45",

    # Cooling
    "cool_fan_enabled": "true",
    "cool_fan_speed": "100",
    "cool_fan_speed_0": "0",  # First layer
    "cool_min_layer_time": "10",
    "cool_min_speed": "10",

    # Quality
    "optimize_wall_printing_order": "true",
    "fill_outline_gaps": "true",
    "filter_out_tiny_gaps": "false",
    "skin_monotonic": "false",

    # Machine settings (fallback if not in definition)
    "machine_center_is_zero": "false",
    "machine_width": "220",
    "machine_depth": "220",
    "machine_height": "250",
    "machine_nozzle_size": "0.4",
    "line_width": "0.4",
}


def is_curaengine_available() -> bool:
    """Check if CuraEngine is available and configured."""
    if not CURAENGINE_PATH:
        logger.warning("[Cura] CURAENGINE_PATH not configured")
        return False
    if not Path(CURAENGINE_PATH).exists():
        logger.warning("[Cura] CuraEngine not found at: %s", CURAENGINE_PATH)
        return False
    if not CURA_DEFINITION_JSON:
        logger.warning("[Cura] CURA_DEFINITION_JSON not configured")
        return False
    if not Path(CURA_DEFINITION_JSON).exists():
        logger.warning("[Cura] Printer definition not found at: %s", CURA_DEFINITION_JSON)
        return False
    return True


def merge_settings(custom_settings: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Merge custom settings with default settings.

    Args:
        custom_settings: User-provided settings to override defaults

    Returns:
        Merged settings dictionary
    """
    merged = DEFAULT_CURA_SETTINGS.copy()

    if custom_settings:
        # Validate and merge custom settings
        for key, value in custom_settings.items():
            # Convert all values to strings (CuraEngine requirement)
            merged[key] = str(value)
            logger.info("[Cura] Custom setting: %s=%s", key, value)

    return merged


async def run_curaengine_process(
    stl_path: Path,
    gcode_path: Path,
    settings: Dict[str, str],
) -> Tuple[bool, str]:
    """
    Run CuraEngine to slice STL to G-code.

    Args:
        stl_path: Path to input STL file
        gcode_path: Path to output G-code file
        settings: Dictionary of Cura settings

    Returns:
        Tuple[success: bool, log_output: str]
    """
    logger.info("[Cura] ===== Starting CuraEngine Slicing =====")
    logger.info("[Cura] Input STL: %s (exists: %s)", stl_path, stl_path.exists())
    logger.info("[Cura] Output G-code: %s", gcode_path)
    logger.info("[Cura] Printer definition: %s", CURA_DEFINITION_JSON)
    logger.info("[Cura] Settings count: %d", len(settings))

    if not is_curaengine_available():
        logger.error("[Cura] CuraEngine not available")
        return False, "CuraEngine not configured or not found"

    if not stl_path.exists():
        logger.error("[Cura] STL file not found: %s", stl_path)
        return False, f"STL file not found: {stl_path}"

    # Prepare log file
    log_path = OUTPUT_DIR / f"cura_log_{gcode_path.stem}.txt"
    logger.info("[Cura] Log will be saved to: %s", log_path)

    # Build CuraEngine command
    cmd = [
        str(CURAENGINE_PATH),
        "slice",
    ]

    # Add verbose flag if enabled
    if CURA_VERBOSE:
        cmd.append("-v")

    # Add printer definition
    cmd.extend(["-j", str(Path(CURA_DEFINITION_JSON).absolute())])

    # Add output file
    cmd.extend(["-o", str(gcode_path.absolute())])

    # Add extruder (extruder 0)
    cmd.append("-e0")

    # Add all settings as -s key=value pairs
    for key, value in settings.items():
        cmd.extend(["-s", f"{key}={value}"])

    # Add input STL file (must be last)
    cmd.extend(["-l", str(stl_path.absolute())])

    logger.info("[Cura] Command length: %d arguments", len(cmd))
    if CURA_VERBOSE:
        logger.info("[Cura] Full command: %s", " ".join(cmd))

    # Run CuraEngine process
    try:
        logger.info("[Cura] Starting subprocess with timeout=%ds...", CURA_TIMEOUT)

        # Use sync subprocess for Windows compatibility
        loop = asyncio.get_event_loop()

        def run_subprocess():
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                stdout, _ = process.communicate(timeout=CURA_TIMEOUT)
                return process.returncode, stdout
            except subprocess.TimeoutExpired:
                process.kill()
                return -1, b"Process timed out"

        returncode, stdout = await loop.run_in_executor(None, run_subprocess)

        logger.info("[Cura] Process completed with return code: %d", returncode)
        logger.info("[Cura] Stdout size: %d bytes", len(stdout))

        log_output = stdout.decode("utf-8", errors="ignore")
        logger.info("[Cura] Decoded output size: %d characters", len(log_output))

        # Save log
        try:
            log_path.write_text(log_output, encoding="utf-8", errors="ignore")
            logger.info("[Cura] Log saved successfully: %s", log_path)
        except Exception as e:
            logger.error("[Cura] Failed to save log: %s", str(e))

        # Check for timeout
        if returncode == -1:
            logger.error("[Cura] Process timed out after %ds", CURA_TIMEOUT)
            return False, "Slicing timeout"

        # CuraEngine may return non-zero even on success (due to warnings)
        # Check if G-code file was actually created
        logger.info("[Cura] Checking output file: %s", gcode_path)
        logger.info("[Cura] Output exists: %s", gcode_path.exists())

        if gcode_path.exists():
            file_size = gcode_path.stat().st_size
            logger.info("[Cura] Output size: %d bytes (%.2f KB)", file_size, file_size / 1024)

            if file_size == 0:
                logger.error("[Cura] G-code file is empty")
                return False, "Generated G-code file is empty"

            # Parse slicing statistics from log
            stats = parse_slicing_stats(log_output)
            logger.info("[Cura] Slicing stats: %s", stats)

            logger.info("[Cura] ===== Slicing Successful =====")
            return True, log_output
        else:
            logger.error("[Cura] G-code file not generated")
            # Extract error messages from log
            error_lines = [line for line in log_output.split('\n') if '[error]' in line.lower()]
            error_summary = '\n'.join(error_lines[-10:]) if error_lines else log_output[-500:]
            logger.error("[Cura] Error summary:\n%s", error_summary)
            return False, error_summary

    except asyncio.CancelledError:
        logger.error("[Cura] Process was cancelled")
        raise
    except Exception as e:
        logger.error("[Cura] Exception during subprocess execution")
        logger.error("[Cura] Exception type: %s", type(e).__name__)
        logger.error("[Cura] Exception message: %s", str(e))
        import traceback
        error_msg = f"CuraEngine execution error: {str(e)}\n{traceback.format_exc()}"
        logger.error("[Cura] Full traceback:\n%s", traceback.format_exc())
        return False, error_msg


def parse_slicing_stats(log_output: str) -> Dict[str, any]:
    """
    Parse useful statistics from CuraEngine log output.

    Args:
        log_output: Full log output from CuraEngine

    Returns:
        Dictionary with statistics (layer_count, print_time, etc.)
    """
    import re
    stats = {}

    try:
        lines = log_output.split('\n')

        for line in lines:
            # Parse layer count
            if 'Processing insets for layer' in line:
                match = re.search(r'layer \d+ of (\d+)', line)
                if match:
                    stats['layer_count'] = int(match.group(1))

            # Parse progress messages
            if '[info] Progress:' in line and 'accomplished in' in line:
                # Extract timing information
                if 'slice accomplished' in line:
                    match = re.search(r'in ([\d.]+)s', line)
                    if match:
                        stats['slice_time'] = float(match.group(1))
                elif 'export accomplished' in line:
                    match = re.search(r'in ([\d.]+)s', line)
                    if match:
                        stats['export_time'] = float(match.group(1))
    except Exception as e:
        logger.warning("[Cura] Failed to parse statistics: %s", str(e))

    return stats


async def convert_stl_to_gcode(
    stl_path: str,
    gcode_path: str,
    custom_settings: Optional[Dict[str, str]] = None,
    printer_definition_path: Optional[str] = None,
) -> bool:
    """
    Convert STL file to G-code using CuraEngine.

    Args:
        stl_path: Absolute path to input STL file
        gcode_path: Absolute path to output G-code file
        custom_settings: Optional dictionary of custom Cura settings
        printer_definition_path: Optional path to printer definition JSON
                                (if None, uses CURA_DEFINITION_JSON from env)

    Returns:
        bool: Success status
    """
    if not is_curaengine_available():
        raise RuntimeError("CuraEngine is not configured or not available")

    stl_file = Path(stl_path)
    gcode_file = Path(gcode_path)

    if not stl_file.exists():
        raise RuntimeError(f"Input STL file not found: {stl_path}")

    # Merge settings
    settings = merge_settings(custom_settings)

    # Override printer definition if provided
    global CURA_DEFINITION_JSON
    if printer_definition_path:
        if not Path(printer_definition_path).exists():
            raise RuntimeError(f"Printer definition not found: {printer_definition_path}")
        # Temporarily override
        original_def = CURA_DEFINITION_JSON
        CURA_DEFINITION_JSON = printer_definition_path
        logger.info("[Cura] Using custom printer definition: %s", printer_definition_path)

    try:
        # Run slicing
        logger.info("[Cura] Starting slicing: %s -> %s", stl_path, gcode_path)
        success, log_output = await run_curaengine_process(
            stl_file,
            gcode_file,
            settings,
        )

        if not success:
            raise RuntimeError(f"Slicing failed: {log_output[:500]}")

        logger.info("[Cura] Slicing completed successfully")
        return True

    finally:
        # Restore original definition if it was overridden
        if printer_definition_path:
            CURA_DEFINITION_JSON = original_def


async def convert_stl_to_gcode_with_definition(
    stl_path: str,
    gcode_path: str,
    printer_definition: Dict[str, any],
    custom_settings: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Convert STL to G-code using printer definition JSON sent by client.

    Args:
        stl_path: Absolute path to input STL file
        gcode_path: Absolute path to output G-code file
        printer_definition: Complete printer definition JSON (dict from .def.json file)
        custom_settings: Optional user settings to override defaults

    Returns:
        bool: Success status
    """
    if not CURAENGINE_PATH or not Path(CURAENGINE_PATH).exists():
        raise RuntimeError("CuraEngine not found")

    stl_file = Path(stl_path)
    gcode_file = Path(gcode_path)

    if not stl_file.exists():
        raise RuntimeError(f"Input STL file not found: {stl_path}")

    # Write printer definition to temporary file
    import tempfile
    import json

    temp_def_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.def.json',
        delete=False,
        dir=OUTPUT_DIR
    )

    try:
        # Write definition JSON
        json.dump(printer_definition, temp_def_file, indent=2)
        temp_def_file.close()
        definition_path = temp_def_file.name

        logger.info("[Cura] Created temporary printer definition: %s", definition_path)

        # Merge settings
        settings = merge_settings(custom_settings)

        # Temporarily override CURA_DEFINITION_JSON
        global CURA_DEFINITION_JSON
        original_def = CURA_DEFINITION_JSON
        CURA_DEFINITION_JSON = definition_path

        try:
            # Run slicing
            logger.info("[Cura] Starting slicing with client definition")
            success, log_output = await run_curaengine_process(
                stl_file,
                gcode_file,
                settings,
            )

            if not success:
                raise RuntimeError(f"Slicing failed: {log_output[:500]}")

            logger.info("[Cura] Slicing completed successfully")
            return True

        finally:
            # Restore original definition
            CURA_DEFINITION_JSON = original_def

    finally:
        # Clean up temp file
        try:
            Path(definition_path).unlink()
            logger.info("[Cura] Cleaned up temp definition file")
        except Exception as e:
            logger.warning("[Cura] Failed to cleanup temp file: %s", e)


async def convert_stl_to_gcode_with_db_profile(
    stl_path: str,
    gcode_path: str,
    printer_profile: Dict[str, any],
    custom_settings: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Convert STL to G-code using printer profile from database.

    This function is designed to work when printer definitions are stored in DB
    instead of using local .def.json files.

    Args:
        stl_path: Absolute path to input STL file
        gcode_path: Absolute path to output G-code file
        printer_profile: Dictionary containing printer profile from DB with keys:
            - 'definition_json': Path to printer definition file OR JSON string
            - 'settings': Optional default settings for this printer
        custom_settings: Optional user settings to override printer defaults

    Returns:
        bool: Success status
    """
    # Extract definition path/content from profile
    definition = printer_profile.get('definition_json')
    printer_default_settings = printer_profile.get('settings', {})

    if not definition:
        raise RuntimeError("Printer profile missing 'definition_json'")

    # Handle if definition is a JSON string (stored in DB)
    definition_path = None
    if isinstance(definition, str) and definition.endswith('.json'):
        # It's a file path
        definition_path = definition
    elif isinstance(definition, (str, dict)):
        # It's JSON content - need to write to temp file
        import tempfile
        temp_def = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.def.json',
            delete=False,
            dir=OUTPUT_DIR
        )
        if isinstance(definition, str):
            temp_def.write(definition)
        else:
            json.dump(definition, temp_def)
        temp_def.close()
        definition_path = temp_def.name
        logger.info("[Cura] Created temporary definition file: %s", definition_path)

    # Merge settings: defaults < printer defaults < custom settings
    merged_settings = DEFAULT_CURA_SETTINGS.copy()
    if printer_default_settings:
        merged_settings.update(printer_default_settings)
    if custom_settings:
        merged_settings.update(custom_settings)

    try:
        return await convert_stl_to_gcode(
            stl_path=stl_path,
            gcode_path=gcode_path,
            custom_settings=merged_settings,
            printer_definition_path=definition_path,
        )
    finally:
        # Clean up temp file if created
        if definition_path and 'temp' in definition_path:
            try:
                Path(definition_path).unlink()
                logger.info("[Cura] Cleaned up temp definition file")
            except Exception as e:
                logger.warning("[Cura] Failed to cleanup temp file: %s", e)
