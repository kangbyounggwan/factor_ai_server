import json
from .client import get_llm_client
from .explain_prompt import EXPLAIN_PROMPT
from ..models import Anomaly
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

class ExplanationResult(BaseModel):
    severity: str = Field(description="Severity of the issue")
    summary: str = Field(description="One line summary")
    explanation: str = Field(description="Detailed explanation")

async def llm_explain_anomaly(
    anomaly: Anomaly,
    snippet: str,
    global_summary: dict
) -> dict:
    """
    Use Gemini to explain the anomaly.
    Returns: Dict with keys 'severity', 'summary', 'explanation'.
    """
    llm = get_llm_client()
    chain = EXPLAIN_PROMPT | llm | JsonOutputParser(pydantic_object=ExplanationResult)
    
    try:
        result = await chain.ainvoke({
            "global_summary": json.dumps(global_summary, indent=2),
            "anomaly_json": json.dumps(anomaly.dict(), indent=2),
            "snippet": snippet
        })
        return result
    except Exception as e:
        return {
            "severity": "unknown",
            "summary": "Error during LLM analysis",
            "explanation": str(e)
        }
