from pydantic import BaseModel, Field
from typing import Dict, Any
from .models import Anomaly, GCodeSummary

class LLMInput(BaseModel):
    global_summary: Dict[str, Any]
    anomaly: Dict[str, Any]  # serialized Anomaly
    snippet: str
    
    # simple estimated token count (4 chars ~= 1 token)
    def estimate_tokens(self) -> int:
        text = str(self.global_summary) + str(self.anomaly) + self.snippet
        return len(text) // 4
