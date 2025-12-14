import os
import logging
import asyncio
import subprocess
import json
from pathlib import Path
import time
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

    # Support (기본값: 비활성화, 트리 서포트 파라미터는 CuraEngine 기본값 사용)
    "support_enable": "false",
    # support_structure, support_tree_* 등은 명시하지 않으면 CuraEngine 기본값 사용
    # 트리 서포트 활성화 시 클라이언트에서 다음을 전송:
    #   "support_enable": "true",
    #   "support_structure": "tree"
    # 나머지 트리 서포트 파라미터 (기본값 사용 권장):
    #   support_tree_angle: 45 (기본값)
    #   support_tree_branch_diameter: 2.0 (기본값)
    #   support_tree_branch_diameter_angle: 5 (기본값)
    #   support_tree_tip_diameter: 0.8 (기본값)
    #   support_tree_branch_distance: 1.0 (기본값)
    #   support_tree_collision_resolution: 0.2 (기본값)

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

    # Temperature consistency (prevent temperature drop during print)
    "material_final_print_temperature": "200",  # Keep nozzle temp until end
    "material_initial_print_temperature": "200",  # Initial nozzle temp
    "material_print_temperature_layer_0": "205",  # First layer temp
    "cool_min_temperature": "200",  # CRITICAL: Prevent temp drop on small layers (default is 0!)
    "small_feature_max_length": "0",  # Disable small feature detection
    "small_feature_speed_factor": "100",  # No speed reduction for small features
    "small_feature_speed_factor_0_first_layer": "100",  # No reduction on first layer
    "cool_lift_head": "false",  # Don't lift head on cooling

    # Quality
    "optimize_wall_printing_order": "true",
    "fill_outline_gaps": "true",
    "filter_out_tiny_gaps": "false",
    "skin_monotonic": "false",
    "roofing_layer_count": "0",  # Number of top layers with roofing pattern
    "top_layers": "4",  # Number of top layers
    "bottom_layers": "4",  # Number of bottom layers

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


def get_default_printer_name() -> str:
    """
    Extract printer name from CURA_DEFINITION_JSON path.

    Returns:
        Printer name (e.g., "creality_ender3" from "creality_ender3.def.json")
        Falls back to "fdmprinter" if extraction fails.
    """
    if not CURA_DEFINITION_JSON:
        return "fdmprinter"

    try:
        # Extract filename without extension
        # e.g., "C:/...../creality_ender3.def.json" -> "creality_ender3"
        filename = Path(CURA_DEFINITION_JSON).stem  # Gets "creality_ender3.def"
        printer_name = filename.replace('.def', '')  # Gets "creality_ender3"
        logger.info("[Cura] Extracted default printer name: %s", printer_name)
        return printer_name
    except Exception as e:
        logger.warning("[Cura] Failed to extract printer name from definition: %s", e)
        return "fdmprinter"


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
    start_time = time.time()

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

            
            elapsed_time = time.time() - start_time
            logger.info("[Cura] Total slicing time: %.2f seconds (%.1f minutes)", elapsed_time, elapsed_time / 60.0)

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


def calculate_gcode_stats_from_content(gcode_path: str) -> Dict[str, any]:
    """
    G-code 본문을 직접 파싱하여 실제 출력 시간과 필라멘트 사용량 계산.

    CuraEngine이 TIME과 MATERIAL에 더미값을 넣는 경우를 대비하여
    G1 명령어를 직접 분석합니다.
    """
    from pathlib import Path

    stats = {
        'calculated_time_seconds': None,
        'calculated_filament_mm': None,
        'calculated_filament_m': None,
        'calculated_filament_g': None,
    }

    try:
        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            return stats

        total_time_seconds = 0.0
        max_e_value = 0.0
        current_feedrate = 0.0  # mm/min
        last_x, last_y, last_z = 0.0, 0.0, 0.0

        logger.info("[GCodeCalc] Calculating actual time and filament from G-code commands...")

        with open(gcode_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f):
                line = line.strip()

                # G1 이동 명령 파싱
                if line.startswith('G1 '):
                    import re

                    # Feedrate (F) 추출
                    f_match = re.search(r'F([\d.]+)', line)
                    if f_match:
                        current_feedrate = float(f_match.group(1))  # mm/min

                    # Extrusion (E) 추출 - 최대값 추적
                    e_match = re.search(r'E([\d.\-]+)', line)
                    if e_match:
                        e_value = float(e_match.group(1))
                        if e_value > max_e_value:
                            max_e_value = e_value

                    # 좌표 추출
                    x_match = re.search(r'X([\d.\-]+)', line)
                    y_match = re.search(r'Y([\d.\-]+)', line)
                    z_match = re.search(r'Z([\d.\-]+)', line)

                    x = float(x_match.group(1)) if x_match else last_x
                    y = float(y_match.group(1)) if y_match else last_y
                    z = float(z_match.group(1)) if z_match else last_z

                    # 이동 거리 계산
                    import math
                    distance = math.sqrt((x - last_x)**2 + (y - last_y)**2 + (z - last_z)**2)

                    # 시간 계산 (distance / feedrate)
                    if current_feedrate > 0 and distance > 0:
                        time_minutes = distance / current_feedrate
                        total_time_seconds += time_minutes * 60

                    last_x, last_y, last_z = x, y, z

        # 결과 저장
        if total_time_seconds > 0:
            stats['calculated_time_seconds'] = int(total_time_seconds)

        if max_e_value > 0:
            stats['calculated_filament_mm'] = round(max_e_value, 2)
            stats['calculated_filament_m'] = round(max_e_value / 1000.0, 2)

            # 무게 계산 (1.75mm 필라멘트, PLA 1.24 g/cm³)
            filament_radius_mm = 1.75 / 2.0
            volume_mm3 = max_e_value * 3.14159 * (filament_radius_mm ** 2)
            volume_cm3 = volume_mm3 / 1000.0
            weight_g = volume_cm3 * 1.24
            stats['calculated_filament_g'] = round(weight_g, 2)

        logger.info("[GCodeCalc] Calculated: time=%ds (%.1fmin), filament=%.2fm (%.2fg)",
                   stats.get('calculated_time_seconds', 0),
                   stats.get('calculated_time_seconds', 0) / 60.0,
                   stats.get('calculated_filament_m', 0),
                   stats.get('calculated_filament_g', 0))

    except Exception as e:
        logger.error("[GCodeCalc] Failed to calculate stats: %s", str(e))

    return stats


def parse_gcode_metadata(gcode_path: str) -> Dict[str, any]:
    """
    G-code 파일에서 메타데이터를 추출합니다.

    Cura가 생성한 G-code 파일의 주석에서 다음 정보를 추출:
    - 출력 시간 (print_time_seconds, print_time_formatted)
    - 필라멘트 사용량 (filament_used_m, filament_weight_g, filament_cost)
    - 레이어 정보 (layer_count, layer_height)
    - 모델 크기 (bounding_box: minx, maxx, miny, maxy, minz, maxz)
    - 온도 설정 (nozzle_temp, bed_temp)
    - 프린터 정보 (printer_name)

    Args:
        gcode_path: G-code 파일 경로

    Returns:
        딕셔너리 형태의 메타데이터
    """
    import re
    from pathlib import Path

    metadata = {
        "print_time_seconds": None,
        "print_time_formatted": None,
        "filament_used_m": None,
        "filament_weight_g": None,
        "filament_cost": None,
        "layer_count": None,
        "layer_height": None,
        "bounding_box": {},
        "nozzle_temp": None,
        "bed_temp": None,
        "printer_name": None,
    }

    try:
        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            logger.warning("[GCodeMeta] File not found: %s", gcode_path)
            return metadata

        # G-code 파일을 스트리밍 방식으로 읽기
        # 필요한 정보를 모두 찾으면 조기 종료하여 성능 향상
        lines_read = 0

        with open(gcode_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                lines_read += 1
                line = line.strip()

                # 모든 주요 메타데이터를 찾았는지 체크 (조기 종료 조건)
                # 헤더 정보(TIME, MATERIAL 등)는 처음 부분에 있고,
                # 온도 정보(M104, M140)는 중간~후반부에 있으므로
                # 모든 정보를 찾은 후에만 종료
                if (lines_read > 100 and  # 최소 100줄은 읽기
                    metadata.get('nozzle_temp') is not None and
                    metadata.get('bed_temp') is not None and
                    metadata.get('print_time_seconds') is not None and
                    metadata.get('layer_count') is not None):
                    # 모든 주요 정보를 찾았으면 더 읽을 필요 없음
                    logger.info("[GCodeMeta] All metadata found at line %d, stopping scan", lines_read)
                    break

                # 출력 시간 (초)
                if line.startswith(';TIME:'):
                    match = re.search(r';TIME:(\d+)', line)
                    if match:
                        seconds = int(match.group(1))
                        metadata['print_time_seconds'] = seconds

                        # 포맷된 시간 계산 (예: "1h 30m")
                        hours = seconds // 3600
                        minutes = (seconds % 3600) // 60
                        if hours > 0:
                            metadata['print_time_formatted'] = f"{hours}h {minutes}m"
                        else:
                            metadata['print_time_formatted'] = f"{minutes}m"

                # 필라멘트 사용량 (미터) - 여러 형식 지원
                elif ';Filament used' in line.lower():
                    # Format 1: ";Filament used: 1.23m"
                    match = re.search(r'([\d.]+)\s*m\b', line, re.IGNORECASE)
                    if match:
                        metadata['filament_used_m'] = float(match.group(1))
                    # Format 2: ";Filament used: [1.23]"
                    match = re.search(r'\[([\d.]+)\]', line)
                    if match and metadata['filament_used_m'] is None:
                        metadata['filament_used_m'] = float(match.group(1))

                # 필라멘트 무게 (그램) - 여러 형식 지원
                elif ';Filament weight' in line.lower() or ';Filament mass' in line.lower():
                    # Format 1: "weight = 3.64g" or "3.64g"
                    match = re.search(r'([\d.]+)\s*g\b', line, re.IGNORECASE)
                    if match:
                        metadata['filament_weight_g'] = float(match.group(1))
                    # Format 2: "[3.64]"
                    match = re.search(r'\[([\d.]+)\]', line)
                    if match and metadata['filament_weight_g'] is None:
                        metadata['filament_weight_g'] = float(match.group(1))

                # 필라멘트 비용
                elif ';Filament cost' in line.lower():
                    match = re.search(r'([\d.]+)', line)
                    if match:
                        metadata['filament_cost'] = float(match.group(1))

                # MATERIAL (Cura 5.x 형식 - mm³ 또는 cm³)
                elif line.startswith(';MATERIAL:') or line.startswith(';MATERIAL2:'):
                    match = re.search(r';MATERIAL2?:([\d.]+)', line)
                    if match:
                        volume_mm3 = float(match.group(1))
                        # mm³를 미터로 변환 (필라멘트 직경 1.75mm 가정)
                        # Volume = π * r² * length
                        # length = Volume / (π * r²)
                        # r = 1.75/2 = 0.875mm
                        filament_radius_mm = 1.75 / 2.0
                        area_mm2 = 3.14159 * (filament_radius_mm ** 2)
                        length_mm = volume_mm3 / area_mm2
                        length_m = length_mm / 1000.0

                        if metadata['filament_used_m'] is None:
                            metadata['filament_used_m'] = round(length_m, 2)

                        # 무게 계산 (PLA 밀도: 1.24 g/cm³)
                        if metadata['filament_weight_g'] is None:
                            volume_cm3 = volume_mm3 / 1000.0
                            weight_g = volume_cm3 * 1.24  # PLA 밀도
                            metadata['filament_weight_g'] = round(weight_g, 2)

                # 레이어 수
                elif line.startswith(';LAYER_COUNT:'):
                    match = re.search(r';LAYER_COUNT:(\d+)', line)
                    if match:
                        metadata['layer_count'] = int(match.group(1))

                # 레이어 높이 - 여러 형식 지원
                elif ';Layer height' in line.lower() or ';LAYER_HEIGHT' in line:
                    # Format 1: ";Layer height: 0.2"
                    match = re.search(r'height[:\s]+([\d.]+)', line, re.IGNORECASE)
                    if match:
                        metadata['layer_height'] = float(match.group(1))
                    # Format 2: ";LAYER_HEIGHT:0.2"
                    match = re.search(r'LAYER_HEIGHT:([\d.]+)', line)
                    if match and metadata['layer_height'] is None:
                        metadata['layer_height'] = float(match.group(1))

                # Bounding Box (과학적 표기법 지원: 2.14748e+06)
                elif line.startswith(';MINX:'):
                    match = re.search(r';MINX:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        # 더미값 체크 (1e6 이상은 무효)
                        if abs(value) < 1e6:
                            metadata['bounding_box']['min_x'] = value
                elif line.startswith(';MAXX:'):
                    match = re.search(r';MAXX:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        if abs(value) < 1e6:
                            metadata['bounding_box']['max_x'] = value
                elif line.startswith(';MINY:'):
                    match = re.search(r';MINY:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        if abs(value) < 1e6:
                            metadata['bounding_box']['min_y'] = value
                elif line.startswith(';MAXY:'):
                    match = re.search(r';MAXY:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        if abs(value) < 1e6:
                            metadata['bounding_box']['max_y'] = value
                elif line.startswith(';MINZ:'):
                    match = re.search(r';MINZ:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        if abs(value) < 1e6:
                            metadata['bounding_box']['min_z'] = value
                elif line.startswith(';MAXZ:'):
                    match = re.search(r';MAXZ:([\d.\-+eE]+)', line)
                    if match:
                        value = float(match.group(1))
                        if abs(value) < 1e6:
                            metadata['bounding_box']['max_z'] = value

                # 온도 설정 - 노즐 (주석 또는 G-code 명령어에서)
                elif ';Material print temperature:' in line.lower():
                    match = re.search(r'(\d+)', line)
                    if match and metadata['nozzle_temp'] is None:
                        metadata['nozzle_temp'] = int(match.group(1))

                # 온도 설정 - 베드 (주석에서)
                elif ';Material bed temperature:' in line.lower():
                    match = re.search(r'(\d+)', line)
                    if match and metadata['bed_temp'] is None:
                        metadata['bed_temp'] = int(match.group(1))

                # 프린터 이름
                elif line.startswith(';Printer name:') or line.startswith(';FLAVOR:'):
                    if 'Printer name:' in line:
                        match = re.search(r';Printer name:\s*(.+)', line)
                        if match:
                            metadata['printer_name'] = match.group(1).strip()

                # M104/M109: 노즐 온도 설정 (예: M104 S200)
                elif (line.startswith('M104 ') or line.startswith('M109 ')) and metadata['nozzle_temp'] is None:
                    match = re.search(r'S([\d.]+)', line)
                    if match:
                        temp = int(float(match.group(1)))
                        if temp > 0:  # S0은 무시 (끄기 명령)
                            metadata['nozzle_temp'] = temp

                # M140/M190: 베드 온도 설정 (예: M140 S60)
                elif (line.startswith('M140 ') or line.startswith('M190 ')) and metadata['bed_temp'] is None:
                    match = re.search(r'S([\d.]+)', line)
                    if match:
                        temp = int(float(match.group(1)))
                        if temp > 0:  # S0은 무시
                            metadata['bed_temp'] = temp

        # 모델 크기 계산 (bounding box가 있으면)
        bbox = metadata['bounding_box']
        has_valid_bbox = False

        # Bounding box 유효성 체크
        # 1. 모든 값이 존재하는지
        # 2. min < max 인지
        # 3. size가 양수인지
        if (bbox.get('min_x') is not None and bbox.get('max_x') is not None and
            bbox.get('min_y') is not None and bbox.get('max_y') is not None and
            bbox.get('min_z') is not None and bbox.get('max_z') is not None):

            size_x = bbox['max_x'] - bbox['min_x']
            size_y = bbox['max_y'] - bbox['min_y']
            size_z = bbox['max_z'] - bbox['min_z']

            # Size가 모두 양수인지 확인
            if size_x > 0 and size_y > 0 and size_z > 0:
                metadata['bounding_box']['size_x'] = size_x
                metadata['bounding_box']['size_y'] = size_y
                metadata['bounding_box']['size_z'] = size_z
                has_valid_bbox = True
                logger.info("[GCodeMeta] Valid bounding box from G-code: %.2f x %.2f x %.2f mm",
                           size_x, size_y, size_z)
            else:
                logger.warning("[GCodeMeta] Invalid bounding box: negative size detected (X=%.2f, Y=%.2f, Z=%.2f)",
                             size_x, size_y, size_z)
                metadata['bounding_box'] = {}

        if not has_valid_bbox:
            logger.warning("[GCodeMeta] Invalid bounding box detected (dummy values) - will try to extract from STL")

            # STL 파일에서 직접 크기 읽기
            stl_path = str(gcode_file).replace('.gcode', '.stl')
            if os.path.exists(stl_path):
                try:
                    import trimesh
                    logger.info("[GCodeMeta] Reading bounding box from STL: %s", stl_path)
                    stl_mesh = trimesh.load(stl_path, file_type='stl')
                    stl_bounds = stl_mesh.bounds

                    metadata['bounding_box'] = {
                        'min_x': round(stl_bounds[0, 0], 2),
                        'max_x': round(stl_bounds[1, 0], 2),
                        'min_y': round(stl_bounds[0, 1], 2),
                        'max_y': round(stl_bounds[1, 1], 2),
                        'min_z': round(stl_bounds[0, 2], 2),
                        'max_z': round(stl_bounds[1, 2], 2),
                        'size_x': round(stl_bounds[1, 0] - stl_bounds[0, 0], 2),
                        'size_y': round(stl_bounds[1, 1] - stl_bounds[0, 1], 2),
                        'size_z': round(stl_bounds[1, 2] - stl_bounds[0, 2], 2),
                    }
                    has_valid_bbox = True
                    logger.info("[GCodeMeta] ✅ Extracted bounding box from STL successfully")
                except Exception as e:
                    logger.warning("[GCodeMeta] Failed to extract bounding box from STL: %s", e)
                    metadata['bounding_box'] = {}
            else:
                logger.warning("[GCodeMeta] STL file not found for bounding box extraction: %s", stl_path)
                metadata['bounding_box'] = {}

        # 더미값 체크 및 실제 계산 수행
        # TIME:6666 또는 MATERIAL:6666 같은 더미값 감지
        is_dummy_time = (metadata.get('print_time_seconds') == 6666)
        is_dummy_material = (metadata.get('filament_used_m') is None or
                            metadata.get('filament_used_m') == 0 or
                            metadata.get('filament_used_m') > 1000)  # 1km 이상은 비정상

        if is_dummy_time or is_dummy_material:
            logger.warning("[GCodeMeta] Detected dummy/invalid values - calculating from G-code content...")
            calculated_stats = calculate_gcode_stats_from_content(str(gcode_file))

            # 더미값인 경우 계산값으로 대체
            if is_dummy_time and calculated_stats.get('calculated_time_seconds'):
                metadata['print_time_seconds'] = calculated_stats['calculated_time_seconds']
                seconds = metadata['print_time_seconds']
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                if hours > 0:
                    metadata['print_time_formatted'] = f"{hours}h {minutes}m"
                else:
                    metadata['print_time_formatted'] = f"{minutes}m"

            if is_dummy_material:
                if calculated_stats.get('calculated_filament_m'):
                    metadata['filament_used_m'] = calculated_stats['calculated_filament_m']
                if calculated_stats.get('calculated_filament_g'):
                    metadata['filament_weight_g'] = calculated_stats['calculated_filament_g']

        # 로그 출력
        logger.info("[GCodeMeta] Parsed metadata from: %s", gcode_file.name)
        logger.info("[GCodeMeta]   Print time: %s (%s seconds)",
                   metadata.get('print_time_formatted', 'N/A'),
                   metadata.get('print_time_seconds', 'N/A'))
        logger.info("[GCodeMeta]   Filament: %.2f m, %.2f g",
                   metadata.get('filament_used_m') or 0,
                   metadata.get('filament_weight_g') or 0)
        logger.info("[GCodeMeta]   Layers: %s (height: %s mm)",
                   metadata.get('layer_count', 'N/A'),
                   metadata.get('layer_height', 'N/A'))
        logger.info("[GCodeMeta]   Temperature: Nozzle=%s°C, Bed=%s°C",
                   metadata.get('nozzle_temp', 'N/A'),
                   metadata.get('bed_temp', 'N/A'))

        return metadata

    except Exception as e:
        logger.error("[GCodeMeta] Failed to parse metadata: %s", str(e))
        import traceback
        traceback.print_exc()
        return metadata


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


async def convert_stl_to_gcode_with_printer_name(
    stl_path: str,
    gcode_path: str,
    printer_name: str,
    custom_settings: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Convert STL to G-code using printer name from Cura definitions directory.

    Args:
        stl_path: Path to input STL file
        gcode_path: Path to output G-code file
        printer_name: Printer def file name (e.g., 'creality_ender3pro')
        custom_settings: Optional dict of Cura setting overrides

    Returns:
        bool: True if slicing succeeded, False otherwise
    """
    # Cura definitions directory
    # CURAENGINE_PATH = C:\Program Files\UltiMaker Cura 5.7.1\CuraEngine.exe
    # definitions_dir = C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions
    curaengine_path = Path(os.getenv("CURAENGINE_PATH", ""))
    cura_root = curaengine_path.parent  # C:\Program Files\UltiMaker Cura 5.7.1
    definitions_dir = cura_root / "share" / "cura" / "resources" / "definitions"

    # Find printer def file (remove .def if already in printer_name)
    if printer_name.endswith(".def"):
        printer_name = printer_name[:-4]  # Remove '.def'

    printer_def_path = definitions_dir / f"{printer_name}.def.json"

    if not printer_def_path.exists():
        logger.error("[Cura] Printer definition not found: %s", printer_def_path)
        return False

    logger.info("[Cura] Using printer definition: %s", printer_name)
    logger.info("[Cura] Def file path: %s", printer_def_path)

    # Temporarily override CURA_DEFINITION_JSON
    global CURA_DEFINITION_JSON
    original_def = CURA_DEFINITION_JSON
    CURA_DEFINITION_JSON = str(printer_def_path)

    try:
        # Use convert_stl_to_gcode which will use the overridden def path
        result = await convert_stl_to_gcode(
            stl_path=stl_path,
            gcode_path=gcode_path,
            custom_settings=custom_settings,
        )
        return result
    finally:
        # Restore original definition
        CURA_DEFINITION_JSON = original_def


async def convert_stl_to_gcode_with_definition(
    stl_path: str,
    gcode_path: str,
    printer_definition: Dict[str, any],
    custom_settings: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Convert STL to G-code using printer definition JSON sent by client.

    이 함수는 현재 복잡한 프린터 정의 상속 문제로 인해 항상 실패합니다.
    대신 main.py의 fallback 로직이 작동하여 fdmprinter + bed size로 재시도합니다.

    Args:
        stl_path: Absolute path to input STL file
        gcode_path: Absolute path to output G-code file
        printer_definition: Complete printer definition JSON (dict from .def.json file)
        custom_settings: Optional user settings to override defaults

    Returns:
        bool: Success status
    """
    logger.warning("[Cura] convert_stl_to_gcode_with_definition() called - will raise exception for fallback")
    logger.info("[Cura] Printer definition keys: %s", list(printer_definition.keys()))

    # 이 함수는 의도적으로 실패하여 fallback이 작동하도록 함
    raise RuntimeError("Custom printer definition not supported - use fallback to fdmprinter + bed size")

    # Write printer definition to temporary file in Cura definitions directory
    # This allows CuraEngine to resolve inheritance
    import tempfile
    import json
    import shutil

    # Get Cura definitions directory
    curaengine_path = Path(os.getenv("CURAENGINE_PATH", ""))
    cura_root = curaengine_path.parent
    definitions_dir = cura_root / "share" / "cura" / "resources" / "definitions"

    if not definitions_dir.exists():
        raise RuntimeError(f"Cura definitions directory not found: {definitions_dir}")

    # Create temp file in definitions directory so inheritance works
    temp_def_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.def.json',
        delete=False,
        dir=definitions_dir,  # 중요: definitions 디렉토리에 생성
        prefix='temp_client_'
    )

    try:
        # 전략: fdmprinter를 base로 사용하고 클라이언트 overrides 적용
        # CuraEngine은 상속을 지원하므로 클라이언트 정의가 fdmprinter를 상속하도록 함

        # 클라이언트가 overrides만 보낸 경우 -> 완전한 정의로 변환
        client_overrides = {}

        if 'overrides' in printer_definition:
            logger.info("[Cura] Client provided %d overrides", len(printer_definition['overrides']))
            client_overrides = printer_definition['overrides']

        # 클라이언트가 settings를 보낸 경우도 overrides로 처리
        if 'settings' in printer_definition and printer_definition['settings']:
            logger.info("[Cura] Client provided %d settings", len(printer_definition['settings']))
            # settings를 overrides 형식으로 변환
            for key, value in printer_definition['settings'].items():
                if isinstance(value, dict) and 'default_value' in value:
                    client_overrides[key] = value
                else:
                    # 값만 제공된 경우 default_value 형식으로 변환
                    client_overrides[key] = {'default_value': value}

        # fdmprinter를 상속하는 새 정의 생성
        custom_definition = {
            "version": 2,
            "name": printer_definition.get('name', 'Custom Printer'),
            "inherits": "fdmprinter",  # CuraEngine이 같은 디렉토리에서 fdmprinter 찾음
            "metadata": {
                "visible": True,
                "type": "machine"
            },
            "overrides": client_overrides
        }

        # 메타데이터 병합
        if 'metadata' in printer_definition:
            custom_definition['metadata'].update(printer_definition['metadata'])

        logger.info("[Cura] Created definition inheriting from fdmprinter with %d overrides",
                   len(client_overrides))

        # Write definition JSON
        json.dump(custom_definition, temp_def_file, indent=2)
        temp_def_file.close()
        definition_path = temp_def_file.name

        logger.info("[Cura] Created temporary printer definition in Cura directory: %s", definition_path)

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
