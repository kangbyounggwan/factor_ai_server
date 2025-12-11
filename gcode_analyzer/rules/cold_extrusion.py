from typing import List
from ..models import GCodeLine, TempEvent, Anomaly, AnomalyType

def check_cold_extrusion(lines: List[GCodeLine], temp_events: List[TempEvent]) -> List[Anomaly]:
    anomalies = []
    current_temp = 0.0
    
    # We need to replay the temperature state line by line, or just use events.
    # Mixing lines and events is tricky. 
    # Better: iterate lines, update temp state.
    
    # Pre-calculate temp at each line? Too expensive for large files?
    # Let's iterate lines and update temp as we go.
    
    # Initial state (assuming 0 or previous context)
    # Often start G-code has M104/M109.
    
    SAFE_TEMP = 170.0 # Min for PLA usually
    
    for line in lines:
        if line.cmd in ["M104", "M109"]:
            if "S" in line.params:
                current_temp = line.params["S"]
        
        # Check extrusion
        if line.cmd in ["G1", "G0"]: # G0 usually travel, but some use for extrusion
            if "E" in line.params:
                e_val = line.params["E"]
                # If E is increasing (need state for absolute E to know delta)
                # OR if relative extrusion (G91)
                # Simplified: If E param exists and temp is low.
                # NOTE: This might flag Retraction (E decreasing) too if we aren't careful.
                # Ignoring retraction for cold extrusion check might be safer or check delta.
                # Valid extrusion > 0. 
                # For this MVP, if E is present and temp < SAFE_TEMP, flag it. warning.
                # (Ignoring the "E0" reset command often used).
                
                if current_temp < SAFE_TEMP and e_val > 0:
                    # Exclude G92 E0 (Reset) - G92 is a different command.
                    # Exclude if it is likely a retraction? 
                    # Without prev_e, we can't be sure if it's extruding or retracting in absolute mode.
                    # But usually you don't move E motor AT ALL if cold.
                    
                    anomalies.append(Anomaly(
                        type=AnomalyType.COLD_EXTRUSION,
                        line_index=line.index,
                        severity="high",
                        message=f"차가운 노즐({current_temp}°C)에서 익스트루전 시도",
                        context={"temp": current_temp, "e_val": e_val}
                    ))
                    
    return anomalies
