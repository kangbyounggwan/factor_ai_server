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

## 이슈 유형별 판단 기준 (중요!)
- **cold_extrusion**: 노즐 온도가 필라멘트 최소 온도 미만인 상태에서 E(압출) 명령 실행
- **early_temp_off**: 스니펫에 실제로 `M104 S0` 또는 `M109 S0` (온도 0°C 설정) 명령이 있고, 그 이후에 압출(E) 명령이 있는 경우만 해당. 단순 이동(G1 X Y) 명령만 있으면 이슈 아님!
- **rapid_temp_change**: 짧은 시간 내 50°C 이상 급격한 온도 변경
- **missing_warmup**: 온도 설정(M104) 후 대기(M109) 없이 바로 압출 시작
- **missing_bed_temp**: 베드 온도 설정(M140/M190)이 없거나 0°C인 상태에서 출력 시작. 베드 접착 불량 위험
- **bed_temp_off_early**: 출력 완료 전 베드 온도가 꺼짐(M140 S0). 출력물 뒤틀림 위험

## 분석 요청 (반드시 준수!)
⚠️ **절대 규칙**: 스니펫에 실제로 존재하는 명령어만 기반으로 판단하세요!

1. **early_temp_off 판단**: 스니펫에서 "M104 S0" 또는 "M109 S0" 문자열을 직접 찾으세요. 없으면 early_temp_off가 아님!
2. **bed_temp_off_early 판단**: 스니펫에서 "M140 S0" 문자열을 직접 찾으세요. 없으면 bed_temp_off_early가 아님!
3. **has_issue: false** 조건: 위 명령어들이 스니펫에 없으면 문제 없음
4. 파일 끝부분이라고 "온도가 꺼질 것이다"라고 추측하지 마세요
5. G1 이동 명령(E 없음)만 있는 스니펫은 온도 이슈 아님

## 응답 형식 (JSON)
**중요: 각 필드는 반드시 지정된 글자 수 이내로 작성하세요. 핵심만 간결하게!**

{{
  "has_issue": true 또는 false,
  "issue_type": "cold_extrusion|early_temp_off|rapid_temp_change|missing_warmup|missing_bed_temp|bed_temp_off_early|other|none",
  "severity": "low|medium|high|none",
  "description": "문제 핵심 요약 (50자 이내, 예: '압출 시작 전 노즐 온도 미달')",
  "impact": "설비/출력 영향 (50자 이내, 예: '노즐 막힘, 레이어 접착 불량')",
  "suggestion": "수정 방법 (50자 이내, 예: 'M109 S200 대기 명령 추가')",
  "affected_lines": [수정이 필요한 라인 번호 리스트],
}}

JSON만 응답해주세요:
""")
