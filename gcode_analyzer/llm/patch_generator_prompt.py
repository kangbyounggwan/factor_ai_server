"""
Patch Generator Prompt - LLM-based G-code patch generation
"""
from langchain_core.prompts import ChatPromptTemplate

PATCH_GENERATOR_PROMPT = ChatPromptTemplate.from_template("""
당신은 3D 프린터 G-code 전문가입니다.
발견된 이슈에 대해 실제 적용 가능한 G-code 패치를 생성해주세요.

## 입력 정보

### 이슈 정보
{issue_json}

### 원본 G-code 스니펫 (앞뒤 5줄 포함)
```gcode
{snippet_before}
>>> {target_line_number}: {target_line} <<<  [수정 대상]
{snippet_after}
```

### 필라멘트 정보
- 타입: {filament_type}
- 권장 노즐 온도: {filament_nozzle_temp}
- 권장 베드 온도: {filament_bed_temp}

### 슬라이서 정보
- 슬라이서: {slicer_info}

## 패치 생성 규칙

### 1. 액션 타입
- modify: 기존 라인을 수정 (가장 일반적)
- add_before: 대상 라인 앞에 새 라인 추가
- add_after: 대상 라인 뒤에 새 라인 추가
- delete: 대상 라인 삭제
- no_action: 수정 불필요 (H 파라미터 등 벤더 확장)

### 2. 이슈 유형별 패치 패턴

#### 온도 관련 (cold_extrusion, early_temp_off)
- M104 S0 -> M104 S200 또는 삭제
- M109 S0 -> M109 S200
- 온도 대기 누락 -> M109 S200 추가

#### 속도 관련 (excessive_speed)
- 과도한 F값 -> 적정 F값으로 수정
- 첫 레이어: F1200~F1800 권장
- 일반 출력: F1800~F3600 권장

#### 리트랙션 관련 (excessive_retraction)
- 과도한 E음수값 -> 적정값 (보통 1~5mm)

### 3. 제조사 커스텀 코드 (H 파라미터) 처리
- M109 S25 H140 형태는 Bambu/Orca 확장
- H 값이 실제 온도이므로, S 값만 보고 판단하지 마세요
- H 파라미터가 있는 라인은 action: no_action

### 4. 안전 규칙
- 기존 주석(;로 시작)은 유지
- 좌표(X, Y, Z, E)는 변경하지 않음 (온도/속도만 수정)
- 기존 G-code 문법을 정확히 따름

## 응답 형식 (JSON)

patch_id, issue_id, line_number, action, can_auto_apply,
original_code (line, context_before, context_after),
patched_code (line, context_before, context_after),
explanation, risk_level, additional_lines

### 필드 설명
- can_auto_apply: 자동 적용 가능 여부 (false면 사용자 확인 필요)
- context_before/after: 앞뒤 5줄 (원본 그대로)
- risk_level: low (안전), medium (주의), high (위험)
- additional_lines: add_before/add_after일 때 추가할 라인들

### 예시: 온도 수정
patch_id: PATCH-001, issue_id: ISSUE-1, line_number: 589,
action: modify, can_auto_apply: true,
original_code.line: M104 S0,
patched_code.line: M104 S200,
explanation: 콜드 익스트루전 방지를 위해 노즐 온도를 PLA 권장 온도(200도)로 수정,
risk_level: low

JSON만 응답해주세요:
""")


BATCH_PATCH_GENERATOR_PROMPT = ChatPromptTemplate.from_template("""
당신은 3D 프린터 G-code 전문가입니다.
여러 이슈에 대해 실제 적용 가능한 G-code 패치를 일괄 생성해주세요.

## 입력 정보

### 이슈 목록
{issues_json}

### G-code 스니펫 (이슈별 앞뒤 5줄)
{snippets_json}

### 필라멘트 정보
- 타입: {filament_type}
- 권장 노즐 온도: {filament_nozzle_temp}
- 권장 베드 온도: {filament_bed_temp}

### 슬라이서 정보
- 슬라이서: {slicer_info}

## 패치 생성 규칙

### 액션 타입
- modify: 기존 라인 수정
- add_before: 대상 라인 앞에 추가
- add_after: 대상 라인 뒤에 추가
- delete: 라인 삭제
- no_action: 수정 불필요 (H 파라미터 등)

### 안전 규칙
- H 파라미터가 있는 온도 명령은 no_action
- 좌표(X, Y, Z, E)는 변경 금지
- 기존 주석 유지

## 응답 형식

patches 배열에 각 패치를 포함:
- patch_id, issue_id, line_number
- action, can_auto_apply
- original_line, patched_line
- context_before (5줄), context_after (5줄)
- patched_context_before (5줄), patched_context_after (5줄)
- explanation, risk_level

summary에 통계:
- total_patches, auto_applicable, needs_review

JSON만 응답해주세요:
""")
