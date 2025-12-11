from typing import List, Optional
from pydantic import BaseModel
from .models import GCodeLine, TempEvent

def extract_temp_events(lines: List[GCodeLine]) -> List[TempEvent]:
    """
    Extract all temperature setting commands.
    M104/M109 for nozzle, M140/M190 for bed.
    """
    events = []
    for line in lines:
        if line.cmd in ["M104", "M109", "M140", "M190"]:
            if "S" in line.params:
                events.append(TempEvent(
                    line_index=line.index,
                    temp=line.params["S"],
                    cmd=line.cmd
                ))
    return events
