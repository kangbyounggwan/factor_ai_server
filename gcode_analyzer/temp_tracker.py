from typing import List, Optional, Dict, Any
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


def extract_temp_changes(temp_events: List[TempEvent]) -> Dict[str, Any]:
    """
    온도 변화 전체 추출 (노즐/베드 분리)

    Returns:
        {
            "nozzle": [
                {"line": 10, "temp": 210, "cmd": "M104", "change": None},  # 첫 설정
                {"line": 500, "temp": 200, "cmd": "M104", "change": -10},  # 변경
                {"line": 1000, "temp": 0, "cmd": "M104", "change": -200},  # 끄기
            ],
            "bed": [...],
            "summary": {
                "nozzle_changes": 2,
                "bed_changes": 1,
                "nozzle_range": {"min": 0, "max": 210},
                "bed_range": {"min": 0, "max": 60}
            }
        }
    """
    nozzle_events = []
    bed_events = []

    prev_nozzle = None
    prev_bed = None

    for event in temp_events:
        if event.cmd in ["M104", "M109"]:
            # 노즐 온도
            change = None
            if prev_nozzle is not None:
                change = event.temp - prev_nozzle

            nozzle_events.append({
                "line": event.line_index,
                "temp": event.temp,
                "cmd": event.cmd,
                "change": change
            })
            prev_nozzle = event.temp

        elif event.cmd in ["M140", "M190"]:
            # 베드 온도
            change = None
            if prev_bed is not None:
                change = event.temp - prev_bed

            bed_events.append({
                "line": event.line_index,
                "temp": event.temp,
                "cmd": event.cmd,
                "change": change
            })
            prev_bed = event.temp

    # 변화 횟수 계산 (첫 설정 제외)
    nozzle_changes = len([e for e in nozzle_events if e["change"] is not None])
    bed_changes = len([e for e in bed_events if e["change"] is not None])

    # 온도 범위
    nozzle_temps = [e["temp"] for e in nozzle_events] if nozzle_events else [0]
    bed_temps = [e["temp"] for e in bed_events] if bed_events else [0]

    return {
        "nozzle": nozzle_events,
        "bed": bed_events,
        "summary": {
            "nozzle_changes": nozzle_changes,
            "bed_changes": bed_changes,
            "nozzle_range": {"min": min(nozzle_temps), "max": max(nozzle_temps)},
            "bed_range": {"min": min(bed_temps), "max": max(bed_temps)}
        }
    }
