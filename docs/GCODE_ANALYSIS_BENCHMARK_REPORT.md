# G-code 분석 벤치마킹 리포트

## 개요
4개의 G-code 파일을 분석하여 잘못된 에러(False Positive) 패턴을 식별하고 대처방안을 제시합니다.

## 테스트 파일 목록

| # | 파일명 | 슬라이서 | 라인 수 | 온도 이벤트 |
|---|--------|----------|---------|-------------|
| 1 | armoredtyrannosaurus (1).gcode | Cura 5.7.1 | 377,543 | 9 |
| 2 | 1765938755263_18_PLA_1h37m.gcode | OrcaSlicer 2.3.1-alpha (Klipper) | 448,072 | 4 |
| 3 | 1765896343738_gg_fixed_bed55_photo_applied.gcode | OrcaSlicer 2.3.1 | 193,613 | 6 |
| 4 | 1765801225883_hh.gcode | OrcaSlicer 2.3.1 | 194,435 | 5 |

---

## 발견된 False Positive 패턴

### 1. Klipper 매크로 미인식 (Critical - 심각)

**문제 파일**: `1765938755263_18_PLA_1h37m.gcode`

**현상**:
```gcode
M73 P0 R97
M106 S0
M106 P2 S0
;TYPE:Custom
M140 S0           ; ← 베드 온도 0으로 설정 (오탐!)
M104 S0           ; ← 노즐 온도 0으로 설정 (오탐!)
START_PRINT EXTRUDER_TEMP=225 BED_TEMP=60  ; ← Klipper 매크로
```

**오탐 원인**:
- `M140 S0` / `M104 S0`는 Klipper 매크로(`START_PRINT`) 호출 전에 온도를 초기화하는 패턴
- `START_PRINT` 매크로가 실제로 온도를 설정하지만, 분석기가 이를 인식하지 못함
- 결과적으로 "BODY 구간 온도 0" 및 "콜드 익스트루전" 오탐 발생

**탐지된 False Positive**:
- `[CRITICAL] temp_zero @ line 914-915`
- `[CRITICAL] missing_setup @ line 912`
- `[HIGH] cold_extrusion @ line 939`

---

### 2. 첫 압출 라인 오판 (High)

**문제 파일**: `armoredtyrannosaurus (1).gcode`

**현상**:
```gcode
; Line 30: G1 X0.1 Y200.0 Z0.3 F1500.0 E15 ; Draw the first line (프라임 라인)
```

**오탐 원인**:
- 프라임 라인(Prime Line)을 첫 실제 압출로 오인
- 실제로는 START 구간의 프라임 라인이며, 이미 온도 설정 완료 후 실행됨
- 라인 30에서 이미 `M109 S205` (온도 대기) 완료 상태

**탐지된 False Positive**:
- `[HIGH] cold_extrusion @ line 30`

---

### 3. 과도한 속도 경고 (Medium)

**문제 파일**: 모든 파일

**현상**:
- 최대 속도 150~500 mm/s에 대해 경고 발생
- 실제로는 정상적인 설정인 경우가 많음

**오탐 원인**:
- 300 mm/s 기준이 너무 보수적
- Travel 속도와 Print 속도를 구분하지 않음
- 고속 프린터(Bambu, Voron 등)의 정상 설정을 오탐

**탐지된 False Positive**:
- `[HIGH] excessive_speed` - 모든 파일에서 발생

---

### 4. BODY 내 온도 변경 과민 경고 (Low)

**문제 파일**: 모든 파일

**현상**:
- BODY 구간 내 1~4회의 온도 변경에도 경고 발생
- 실제로는 END 구간의 온도 끄기 명령이 BODY로 잘못 분류되는 경우

**오탐 원인**:
- END 구간 경계 감지가 부정확
- 정상적인 온도 변화(예: 브릿지용 온도 변경)도 경고 대상

**탐지된 False Positive**:
- `[LOW] excessive_body_temp` - 모든 파일에서 발생

---

## 대처방안

### Phase 1: Klipper 매크로 인식 (우선순위: Critical)

#### 1.1 Klipper 매크로 패턴 감지

**파일**: `gcode_analyzer/section_detector.py`

```python
# Klipper 매크로 패턴 정의
KLIPPER_MACROS = {
    "START_PRINT": {
        "params": ["EXTRUDER_TEMP", "BED_TEMP", "MATERIAL"],
        "action": "sets_temperature"
    },
    "END_PRINT": {
        "params": [],
        "action": "turns_off_heaters"
    },
    "PRINT_START": {  # Voron 등 다른 이름 변형
        "params": ["EXTRUDER", "BED"],
        "action": "sets_temperature"
    }
}

def detect_klipper_macro(line: GCodeLine) -> Optional[Dict]:
    """Klipper 매크로 감지"""
    if not line.raw:
        return None

    raw_upper = line.raw.upper().strip()
    for macro_name, macro_info in KLIPPER_MACROS.items():
        if raw_upper.startswith(macro_name):
            # 파라미터 추출
            params = {}
            for param in macro_info["params"]:
                match = re.search(rf'{param}=(\d+)', line.raw, re.IGNORECASE)
                if match:
                    params[param] = int(match.group(1))
            return {
                "macro": macro_name,
                "params": params,
                "action": macro_info["action"]
            }
    return None
```

#### 1.2 Rule Engine 수정

**파일**: `gcode_analyzer/rule_engine.py`

```python
def detect_critical_flags(...) -> List[str]:
    """치명적 플래그 감지 - Klipper 매크로 고려"""
    flags = []

    # Klipper 매크로 위치 찾기
    klipper_temp_set_lines = set()
    for line in lines:
        macro = detect_klipper_macro(line)
        if macro and macro["action"] == "sets_temperature":
            klipper_temp_set_lines.add(line.index)

    # BODY에서 노즐 온도 0 설정 체크 (Klipper 매크로 직전 제외)
    for event in temp_events:
        if event.cmd in ["M104", "M109"] and event.temp == 0:
            # Klipper 매크로 직전의 온도 0은 무시
            if any(event.line_index < macro_line <= event.line_index + 5
                   for macro_line in klipper_temp_set_lines):
                continue  # Klipper 패턴으로 판단, 무시

            section, _ = get_section_for_event(event.line_index, boundaries)
            if section == GCodeSection.BODY:
                flags.append(f"BODY_TEMP_ZERO:line_{event.line_index}")
```

---

### Phase 2: 프라임 라인 감지 개선 (우선순위: High)

#### 2.1 프라임 라인 패턴 인식

**파일**: `gcode_analyzer/section_detector.py`

```python
PRIME_LINE_PATTERNS = [
    # Cura 스타일
    r"Draw the first line",
    r"Draw the second line",
    # PrusaSlicer 스타일
    r"intro line",
    # 일반적인 주석
    r"prime",
    r"purge",
    r"wipe",
]

def is_prime_line(line: GCodeLine, lines: List[GCodeLine], window: int = 5) -> bool:
    """프라임 라인인지 확인"""
    # 1. 주석으로 확인
    if line.comment:
        for pattern in PRIME_LINE_PATTERNS:
            if re.search(pattern, line.comment, re.IGNORECASE):
                return True

    # 2. 위치로 확인 (START 구간 끝부분)
    # 3. 익스트루전 패턴으로 확인 (긴 직선 이동 + 높은 E값)
    return False
```

#### 2.2 첫 압출 라인 판정 개선

```python
def find_first_real_extrusion(lines: List[GCodeLine], boundaries: SectionBoundaries) -> int:
    """실제 첫 압출 라인 찾기 (프라임 라인 제외)"""
    for line in lines:
        # START 구간 건너뛰기
        if line.index <= boundaries.start_end:
            continue

        # 프라임 라인 건너뛰기
        if is_prime_line(line, lines):
            continue

        # 실제 압출 확인
        if line.cmd == "G1" and "E" in line.params and line.params.get("E", 0) > 0:
            return line.index

    return None
```

---

### Phase 3: 속도 분석 개선 (우선순위: Medium)

#### 3.1 프린터 타입별 속도 기준

```python
SPEED_LIMITS = {
    "standard": {  # Ender 3, Prusa MK3 등
        "max_print": 150,
        "max_travel": 200,
        "warning_threshold": 100
    },
    "high_speed": {  # Bambu, Voron, RatRig 등
        "max_print": 500,
        "max_travel": 700,
        "warning_threshold": 350
    }
}

def detect_printer_type(lines: List[GCodeLine]) -> str:
    """프린터 타입 감지"""
    for line in lines[:200]:
        if line.comment:
            comment_lower = line.comment.lower()
            if any(kw in comment_lower for kw in ["bambu", "voron", "ratrig", "klipper"]):
                return "high_speed"
            if any(kw in comment_lower for kw in ["ender", "prusa", "artillery"]):
                return "standard"
    return "standard"
```

#### 3.2 Travel vs Print 속도 구분

```python
def analyze_speed_distribution(lines: List[GCodeLine]) -> Dict:
    """속도 분포 분석 - Travel과 Print 구분"""
    travel_speeds = []
    print_speeds = []

    for line in lines:
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            speed = line.params["F"] / 60  # mm/s로 변환

            if line.cmd == "G0" or "E" not in line.params:
                travel_speeds.append(speed)
            else:
                print_speeds.append(speed)

    return {
        "travel": {"max": max(travel_speeds), "avg": sum(travel_speeds)/len(travel_speeds)},
        "print": {"max": max(print_speeds), "avg": sum(print_speeds)/len(print_speeds)}
    }
```

---

### Phase 4: END 구간 경계 개선 (우선순위: Medium)

#### 4.1 END 구간 패턴 강화

```python
END_MARKERS = [
    r"END_PRINT",  # Klipper
    r"PRINT_END",
    r"End of Gcode",
    r"end code",
    r";End",
    r"M84",  # 모터 비활성화
    r"Present print",
]

def detect_end_section_start(lines: List[GCodeLine]) -> int:
    """END 구간 시작점 감지 개선"""
    # 1. 마지막 레이어 이후 찾기
    last_layer_change = 0
    for i, line in enumerate(lines):
        if ";LAYER:" in (line.comment or ""):
            last_layer_change = i

    # 2. END 마커로 확인
    for i in range(last_layer_change, len(lines)):
        for marker in END_MARKERS:
            if re.search(marker, lines[i].raw or "", re.IGNORECASE):
                return i

    # 3. 온도 끄기 명령으로 추정
    for i in range(len(lines) - 1, max(0, len(lines) - 100), -1):
        if lines[i].cmd in ["M104", "M140"] and lines[i].params.get("S", 1) == 0:
            return i

    return len(lines) - 50  # 기본값
```

---

### Phase 5: LLM 프롬프트 개선 (우선순위: Low)

#### 5.1 온도 분석 프롬프트 수정

```python
TEMPERATURE_ANALYSIS_PROMPT = """...

## 정상으로 판단해야 하는 패턴 (이슈로 보고하지 마세요!)
- **Klipper 매크로 전 온도 초기화**: `M104 S0` / `M140 S0` 직후 `START_PRINT` 또는 `PRINT_START` 매크로가 있으면 정상
- **프라임 라인 압출**: START 구간 끝의 "Draw the first line" 등 주석이 있는 압출은 이미 온도 설정 완료 상태
- **H 파라미터가 있는 M109 S0**: Bambu/Orca 벤더 확장
- **END 구간의 온도 0 설정**: 출력 완료 후 정상

## 주의
- `START_PRINT EXTRUDER_TEMP=225 BED_TEMP=60` 형태의 Klipper 매크로는 실제로 온도를 설정합니다
- 매크로 직전의 `M104 S0` / `M140 S0`는 **정상 패턴**입니다

..."""
```

---

## 구현 우선순위

| 순위 | 작업 | 영향도 | 복잡도 | 예상 공수 |
|------|------|--------|--------|-----------|
| 1 | Klipper 매크로 인식 | Critical | Medium | 2-3시간 |
| 2 | 프라임 라인 감지 | High | Low | 1-2시간 |
| 3 | 프린터 타입별 속도 기준 | Medium | Medium | 2시간 |
| 4 | END 구간 경계 개선 | Medium | Low | 1시간 |
| 5 | LLM 프롬프트 개선 | Low | Low | 30분 |

---

## 결론

### 현재 정확도 추정
- **파일 1 (Cura)**: 60% (프라임 라인 오탐, 속도 경고 과민)
- **파일 2 (Klipper)**: 20% (Klipper 매크로 미인식으로 대부분 오탐)
- **파일 3 (OrcaSlicer)**: 90% (경미한 오탐만 존재)
- **파일 4 (OrcaSlicer)**: 90% (경미한 오탐만 존재)

### 개선 후 예상 정확도
Phase 1~5 구현 완료 시:
- **모든 파일 95%+ 정확도** 달성 예상

### 즉시 적용 가능한 개선
1. LLM 프롬프트에 Klipper 매크로 설명 추가
2. 프라임 라인 주석 패턴 인식
3. 속도 경고 임계값 조정 (300 → 500 mm/s)
