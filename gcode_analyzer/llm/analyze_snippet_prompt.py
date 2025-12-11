"""
LLM 기반 스니펫 분석
규칙 엔진 없이 LLM이 직접 문제를 판단
"""
from langchain_core.prompts import ChatPromptTemplate

ANALYZE_SNIPPET_PROMPT = ChatPromptTemplate.from_template("""
당신은 3D 프린팅 전문가입니다. 아래 G-code 스니펫을 분석하여 문제가 있는지 판단해주세요.

## G-code 기본 정보
- 총 레이어: {total_layers}
- 레이어 높이: {layer_height}mm
- 노즐 온도 범위: {nozzle_temp_min}°C ~ {nozzle_temp_max}°C
- 베드 온도 범위: {bed_temp_min}°C ~ {bed_temp_max}°C

## 필라멘트 정보
{filament_info}
{comprehensive_info}
## 분석 대상 이벤트
- 라인 번호: {event_line_index}
- 명령어: {event_cmd}
- 설정 온도: {event_temp}°C
- 이벤트 이후 남은 라인 수: {lines_after_event}

## G-code 스니펫 (이벤트 전후 {window}줄)
```gcode
{snippet_text}
```

## 분석 요청
1. 이 G-code 스니펫에 문제가 있습니까?
2. 문제가 있다면 구체적으로 무엇입니까?
3. 이 문제가 실제 3D 프린팅에 어떤 영향을 미칩니까?
4. 수정이 필요하다면 어떻게 수정해야 합니까?

## 응답 형식 (JSON)
**중요: 각 필드는 반드시 지정된 글자 수 이내로 작성하세요. 핵심만 간결하게!**

{{
  "has_issue": true 또는 false,
  "issue_type": "cold_extrusion|early_temp_off|rapid_temp_change|missing_warmup|other|none",
  "severity": "low|medium|high|none",
  "description": "문제 핵심 요약 (50자 이내, 예: '압출 시작 전 노즐 온도 미달')",
  "impact": "설비/출력 영향 (50자 이내, 예: '노즐 막힘, 레이어 접착 불량')",
  "suggestion": "수정 방법 (50자 이내, 예: 'M109 S200 대기 명령 추가')",
  "affected_lines": [수정이 필요한 라인 번호 리스트],
}}

JSON만 응답해주세요:
""")
