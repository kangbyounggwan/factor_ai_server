from langchain_core.prompts import ChatPromptTemplate

EXPLAIN_PROMPT = ChatPromptTemplate.from_template("""
[Context]
- This G-code is for an FDM 3D printer.
- Below is a snippet of the G-code around an anomaly detected by the rule engine.
- The detected anomaly is described in JSON format.

[Global Summary]
{global_summary}

[Anomaly Detected]
{anomaly_json}

[G-code Snippet]
```gcode
{snippet}
```

[Request]
1. Explain what problem this pattern might cause in the actual print.
2. Rate the severity (low/medium/high).
3. Provide a one-line summary of the issue.

**IMPORTANT: Keep responses concise!**

Return ONLY JSON:
{{
  "severity": "low|medium|high",
  "summary": "One sentence summary (max 300 chars)",
  "explanation": "Brief explanation of impact (max 200 chars)"
}}
""")
