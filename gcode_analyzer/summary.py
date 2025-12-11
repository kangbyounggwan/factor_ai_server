from typing import List, Optional, Dict
from pydantic import BaseModel
from .models import GCodeLine, GCodeSummary


def build_layer_map(lines: List[GCodeLine]) -> Dict[int, int]:
    """
    라인 인덱스 → 레이어 번호 매핑 테이블 생성

    Args:
        lines: 파싱된 G-code 라인들

    Returns:
        {line_index: layer_number} 딕셔너리
    """
    layer_map = {}
    current_layer = 0

    for idx, line in enumerate(lines):
        if line.comment:
            comment = line.comment.strip()
            # Cura, PrusaSlicer 등 다양한 슬라이서 포맷 지원
            if comment.startswith("LAYER:"):
                try:
                    current_layer = int(comment.split("LAYER:")[1].strip())
                except ValueError:
                    pass
            elif comment.startswith(";LAYER:"):
                try:
                    current_layer = int(comment.split(";LAYER:")[1].strip())
                except ValueError:
                    pass
            elif "layer" in comment.lower():
                # "Layer 10" 같은 포맷
                import re
                match = re.search(r'layer\s*[:#]?\s*(\d+)', comment, re.IGNORECASE)
                if match:
                    current_layer = int(match.group(1))

        layer_map[idx] = current_layer

    return layer_map


def get_layer_for_line(layer_map: Dict[int, int], line_index: int) -> int:
    """
    라인 인덱스에 해당하는 레이어 번호 반환

    Args:
        layer_map: build_layer_map()으로 생성된 매핑
        line_index: 라인 번호

    Returns:
        레이어 번호 (매핑 없으면 0)
    """
    return layer_map.get(line_index, 0)


def summarize_gcode(lines: List[GCodeLine]) -> GCodeSummary:
    """Extract global summary information from parsed G-code lines."""
    
    # Initialize trackers
    total_layers = 0
    layer_heights = set()
    nozzle_temps = []
    bed_temps = []
    speeds = []
    retraction_count = 0
    filament_type = None
    estimated_time = None
    
    # Specific logic might depend on Slicer comments, but we try standard cmds first
    # Layer count often needs comment parsing (e.g. ;LAYER:10)
    
    for line in lines:
        # Track Temperatures
        if line.cmd in ["M104", "M109"]: # Set Extruder Temp
            if "S" in line.params:
                nozzle_temps.append(line.params["S"])
        elif line.cmd in ["M140", "M190"]: # Set Bed Temp
            if "S" in line.params:
                bed_temps.append(line.params["S"])
                
        # Track Speed (F)
        if line.cmd in ["G0", "G1"]:
            if "F" in line.params:
                speeds.append(line.params["F"])
            if "E" in line.params:
                # Simple retraction detection: E value decreasing? 
                # Note: standard G-code usually uses absolute E. 
                # If E decreases relative to previous, it's a retraction.
                # Since we parse line by line without state here, we need stateful tracking.
                # However, many slicers use G10/G11 or just G1 E-xxx (relative).
                # For G1 with absolute positioning (M82 default), we need to know previous E.
                # Let's simplify for now or assuming G10 (firmware retract) or check negative E if G91.
                # Without state, reliable retraction count is hard if absolute. 
                # We will defer precise retraction count to a stateful pass if needed, 
                # OR just assume standard slicer output where retractions might be commented or G1 E < prev.
                pass

        # Parse Comments for metadata
        if line.comment:
            c = line.comment.strip()
            if c.startswith("LAYER:"):
                total_layers += 1
            elif "Filament used" in c:
                # Filament used: 1.23m
                pass
            elif "TIME:" in c:
                # TIME:1234 (seconds)
                pass 
                
        # Layer height from Z moves (G0/G1 Z...)
        if line.cmd in ["G0", "G1"] and "Z" in line.params:
             layer_heights.add(line.params["Z"])

    # Calculate aggregations
    nozzle_min = min(nozzle_temps) if nozzle_temps else 0.0
    nozzle_max = max(nozzle_temps) if nozzle_temps else 0.0
    bed_min = min(bed_temps) if bed_temps else 0.0
    bed_max = max(bed_temps) if bed_temps else 0.0
    
    max_f = max(speeds) if speeds else 0.0
    avg_f = sum(speeds) / len(speeds) if speeds else 0.0
    
    # Estimate layer height (mode or min diff) - simplified
    # Real layer height is usually constant.
    # We can refine this later.
    estimated_layer_height = 0.2 # Default placeholder
    if len(layer_heights) > 1:
        sorted_z = sorted(list(layer_heights))
        # Find smallest positive difference
        diffs = [sorted_z[i+1] - sorted_z[i] for i in range(len(sorted_z)-1)]
        valid_diffs = [d for d in diffs if d > 0.01] # Filter noise
        if valid_diffs:
            estimated_layer_height = min(valid_diffs)

    # 필라멘트 타입 감지 시도
    detected_filament = None
    for line in lines[:500]:
        if line.comment:
            comment = line.comment.upper()
            for ftype in ["PLA", "ABS", "PETG", "TPU", "NYLON", "ASA"]:
                if ftype in comment:
                    detected_filament = ftype
                    break
            if detected_filament:
                break

    return GCodeSummary(
        total_layers=total_layers,
        layer_height=round(estimated_layer_height, 2),
        nozzle_temp_min=nozzle_min,
        nozzle_temp_max=nozzle_max,
        bed_temp_min=bed_min,
        bed_temp_max=bed_max,
        max_speed=max_f,
        avg_speed=avg_f,
        retraction_count=retraction_count,
        filament_type=detected_filament,  # 동적 감지
        estimated_print_time=None
    )
