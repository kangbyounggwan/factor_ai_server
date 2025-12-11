from typing import List
from ..models import GCodeLine, TempEvent, Anomaly, AnomalyType

def check_early_temp_off(lines: List[GCodeLine], temp_events: List[TempEvent]) -> List[Anomaly]:
    
    anomalies = []
    
    # Logic: M104 S0 should be near the end.
    # If M104 S0 appears, and there is still A LOT of extrusion after it, that's bad.
    
    total_lines = len(lines)
    if total_lines == 0:
        return []

    # Find where temp is set to 0
    temp_off_indices = []
    for line in lines:
        if line.cmd == "M104" and line.params.get("S") == 0:
            temp_off_indices.append(line.index)
            
    if not temp_off_indices:
        return []
        
    # Check if there is significant printing AFTER the FIRST temp off?
    # Or just check if temp off is NOT in the end script.
    
    # Simple heuristic: If M104 S0 is found, AND there are G1 E commands (extrusion) AFTER it.
    
    for off_idx in temp_off_indices:
        # Search for extrusion after this index
        extrusion_found = False
        first_extrusion_line = None
        
        # Look ahead
        # Using index as 1-based, list is 0-based. line.index is 1-based.
        # lines list index = line.index - 1
        
        start_search = off_idx # This is the index in the list for the NEXT line (since off_idx is 1-based, so lines[off_idx-1] is the cmd, lines[off_idx] is next)
        
        for i in range(start_search, len(lines)):
            line = lines[i]
            if line.cmd in ["G1", "G0"] and "E" in line.params:
                # Need to check if it's actual extrusion (E > prev E)
                # For MVP, assuming any E move is suspicious if temp is 0.
                extrusion_found = True
                first_extrusion_line = line
                break
        
        if extrusion_found:
             anomalies.append(Anomaly(
                type=AnomalyType.EARLY_TEMP_OFF,
                line_index=off_idx,
                severity="medium",
                message="출력이 남았는데 온도가 0으로 설정되었습니다.",
                context={"next_extrusion_line": first_extrusion_line.index}
            ))
            
    return anomalies
