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

## ⚠️ 중요: 이슈 생성 금지!
**`critical_issues`는 반드시 `issues_json`에 제공된 이슈만 포함해야 합니다.**
- `issues_json`이 빈 배열(`[]`)이면 → `critical_issues`도 빈 배열(`[]`)이어야 함
- `summary_info`만 보고 새로운 이슈를 만들어내지 마세요!
- 라인 번호를 직접 추측하거나 발명하지 마세요!
- 입력된 이슈가 없으면 → 품질 점수는 90~100점 (S등급)

**예시:**
- `issues_json: []` → `critical_issues: []`, `quality_score: 95`, `quality_grade: "S"`
- `summary_info`의 통계만으로 이슈를 추론하지 마세요. 1차 분석에서 이미 필터링되었습니다.

## ⚠️ 치명적 이슈 자동 분류 (반드시 준수!)
다음 조건에 해당하면 무조건 severity: "critical" 또는 "high"로 분류하고, 점수를 F (0~39)로 부여하세요:

| 이슈 유형 | 조건 | 심각도 | 이유 |
|----------|------|--------|------|
| **온도 0°C 설정** | M104/M109 S0 또는 노즐온도=0에서 압출 | **critical** | 콜드 익스트루전 → 노즐 막힘, 모터 손상 |
| **압출 전 온도 미달** | 150°C 미만에서 G1 E+ 실행 | **high** | 필라멘트 미용융 상태 압출 시도 |
| **베드 온도 0°C** | M140/M190 S0 (BODY 구간) | **high** | 첫 레이어 접착 실패 |
| **급격한 온도 하락** | 출력 중 100°C 이상 급락 | **high** | 레이어 접착 불량 |

**예시:**
- `M109 S0` 또는 `노즐 온도 0°C로 압출` 발견 → 점수 F (20점 이하), severity: critical
- 이런 이슈는 "경미한 문제"나 "수정 가능한 이슈"로 표현하지 마세요. **"치명적", "출력 불가", "하드웨어 손상 위험"**으로 명시하세요.

## 🔧 제조사 커스텀 코드 (H 파라미터) 처리 - 중요!
**Bambu Lab, OrcaSlicer 등 일부 슬라이서는 제조사 확장 파라미터(H코드)를 사용합니다.**

| 명령어 예시 | S값 의미 | H값 의미 | 심각도 판정 |
|------------|---------|---------|-----------|
| `M109 S25 H140` | 대기 시간(초) 또는 기타 | **실제 온도 (140°C)** | S0도 정상, **warning** |
| `M104 H210` | 없음 | **실제 온도 (210°C)** | 정상, 이슈 아님 |
| `M109 S0` (H 없음) | **온도 0°C** | 없음 | **critical** |

**판정 규칙:**
1. `vendor_extension: true` 또는 `h_value` 컨텍스트가 있으면 → **warning (주의)** 또는 무시
2. H 파라미터 값이 정상 온도 범위(150°C~300°C)면 → 문제 없음으로 판단
3. H 파라미터 없이 S0만 있으면 → **critical (치명적)**

**예시:**
- `M109 S0 H220` 발견 → H=220°C가 실제 온도이므로 정상. severity: **warning** (확인 권장) 또는 이슈 제외
- `M109 S0` (H 없음) 발견 → 진짜 온도 0°C. severity: **critical**

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
| F | 0~39   | **치명적(critical) 이슈 1개 이상** 또는 심각 이슈 4개 이상. 출력 금지, 재슬라이싱 필수. |

**점수 계산 공식 (참고):**
- 기본 점수: 100점
- severity: **critical → 즉시 F등급 (최대 30점)**, high → -20점, medium → -7점, low → -3점
- **온도 0°C 이슈는 무조건 critical로 분류**
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
