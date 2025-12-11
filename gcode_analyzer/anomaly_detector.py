from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from .models import GCodeLine, TempEvent, Anomaly, AnomalyType
from .rules.cold_extrusion import check_cold_extrusion
from .rules.early_temp_off import check_early_temp_off

def detect_anomalies(
    lines: List[GCodeLine],
    temp_events: List[TempEvent]
) -> List[Anomaly]:
    """Run all anomaly detection rules."""
    anomalies = []
    
    # Run individual rules
    anomalies.extend(check_cold_extrusion(lines, temp_events))
    anomalies.extend(check_early_temp_off(lines, temp_events))
    
    return sorted(anomalies, key=lambda x: x.line_index)
