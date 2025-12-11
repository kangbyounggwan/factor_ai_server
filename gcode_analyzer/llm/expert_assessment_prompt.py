"""
Expert Assessment Prompt - The "Answer Sheet" Generator
"""
from langchain_core.prompts import ChatPromptTemplate

EXPERT_ASSESSMENT_PROMPT = ChatPromptTemplate.from_template("""
당신은 3D 프린팅 품질 관리 전문가입니다.
제공된 G-code 분석 데이터와 감지된 이슈 후보들을 검토하여, 최종적인 "품질 평가 정답지(Expert Assessment)"를 작성해주세요.

이 정답지는 사용자에게 제공될 유일한 분석 결과이므로, 중복 없이 명확하고 통찰력 있는 정보를 담아야 합니다.

## 1. 입력 데이터
### 기본 통계 (Python 분석)
{summary_info}

### 감지된 이슈 후보 (1차 필터링됨)
{issues_json}

## 2. 평가 기준
1. **일관성**: 전체 품질 점수와 발견된 이슈의 심각도가 일치해야 합니다. (심각한 이슈가 있는데 점수가 높으면 안 됨)
2. **중복 제거**: "프린팅 개요"와 "상세 분석"에서 같은 말을 반복하지 마세요. 개요는 전체적인 숲을, 상세 분석은 나무를 다룹니다.
3. **명확성**: 사용자가 바로 이해하고 조치할 수 있는 구체적인 조언을 제공하세요.
4. **정확성**: 이슈 라인 번호(`line`)는 입력된 `issues_json`의 `line` 값을 그대로 사용해야 합니다. 절대 변경하지 마세요.

## 3. 작성할 내용 (Answer Sheet)
**중요: 각 텍스트 필드는 지정된 글자 수 이내로 간결하게 작성하세요!**

다음 항목들을 모두 포함하여 JSON으로 응답해주세요.

### 점수 기준 (반드시 준수!)
| 등급 | 점수 범위 | 기준 |
|------|----------|------|
| S | 90~100 | 이슈 없음. 바로 출력 가능. |
| A | 75~89  | 경미한 이슈만 있음 (severity: low/medium). 출력 가능. |
| B | 60~74  | 경고 다수 또는 심각(high) 이슈 1개. 수정 권장. |
| C | 40~59  | 심각(high) 이슈 2~3개. 수정 필수. |
| F | 0~39   | 심각 이슈 4개 이상 또는 출력 실패 예상. 재슬라이싱 권장. |

**점수 계산 공식 (참고):**
- 기본 점수: 100점
- severity: high → -15점, medium → -7점, low → -3점
- 동일 유형 이슈 반복 시 추가 감점 최소화

1. **quality_score**: 위 기준에 따른 점수.
2. **quality_grade**: 위 기준에 따른 등급.
3. **print_characteristics**:
    - complexity: 출력물의 복잡도 (High/Medium/Low)
    - difficulty: 출력 난이도 (Advanced/Intermediate/Beginner)
    - tags: 이 G-code의 특징을 나타내는 태그 3~5개 (예: "Support Heavy", "High Retraction", "Temperature Variation")
4. **summary_text**: 전체 총평 (300자 이내). 핵심만 간결하게.
5. **check_points**: 각 항목별 상태 평가 (temperature, speed, retraction 등).
    - status: "ok", "warning", "error"
    - comment: 한 줄 평가 (30자 이내, 예: "노즐 온도 안정적", "리트랙션 과도, 막힘 위험")
6. **critical_issues**: 실제 문제가 된다고 판단되는 이슈 목록.
    - 입력된 `issues_json`을 검토하여 진짜 문제만 선별합니다.
    - `line`: 입력된 `line` 값을 그대로 사용.
    - `title`: 문제 제목 (30자 이내)
    - `description`: 문제 설명 (50자 이내)
    - `fix_proposal`: 수정 방법 (50자 이내, 예: "M109 S210 추가")
7. **overall_recommendations**: 제안 사항 3~5가지 (각 50자 이내).

## 응답 형식 (JSON)
{{
  "quality_score": 85,
  "quality_grade": "B",
  "print_characteristics": {{
    "complexity": "Medium",
    "difficulty": "Intermediate",
    "tags": ["Low Speed", "Stable Temp"]
  }},
  "summary_text": "PLA 소재 중간 난이도 출력. 온도 안정적이나 리트랙션 과다.",
  "check_points": {{
    "temperature": {{"status": "ok", "comment": "노즐 210도 안정 유지"}},
    "speed": {{"status": "warning", "comment": "이동속도 과다, 진동 우려"}},
    "retraction": {{"status": "ok", "comment": "적정 리트랙션 설정"}}
  }},
  "critical_issues": [
    {{
      "id": "ISSUE-1",
      "line": 12345,
      "type": "cold_extrusion",
      "severity": "high",
      "title": "저온 압출 감지",
      "description": "180도에서 압출 시작, PLA 최소 온도 미달",
      "fix_proposal": "M109 S200 대기 명령 추가"
    }}
  ],
  "overall_recommendations": [
    "노즐 온도 200도 이상 유지 권장",
    "첫 레이어 속도 30mm/s로 감속"
  ]
}}

JSON만 응답해주세요:
""")
