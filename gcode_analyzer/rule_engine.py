"""
G-code 분석 룰 엔진 (최적화 버전)
기본 체크만 수행 - 실제 문제 탐지는 LLM이 담당

역할:
1. 필수 설정 존재 여부 체크 (온도, 베드 등)
2. 데이터 추출 및 정리 (LLM 전달용)
3. 명백한 구조적 오류만 감지

문제 탐지는 LLM(Flash Lite)이 직접 수행
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .models import GCodeLine, TempEvent, Anomaly, AnomalyType
from .section_detector import SectionBoundaries, GCodeSection, get_section_for_event


# ============================================================
# 결과 타입 정의
# ============================================================
@dataclass
class BasicCheckResult:
    """기본 체크 결과"""
    check_name: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedData:
    """LLM 분석용 추출 데이터"""
    # 온도 관련
    has_nozzle_temp: bool = False
    has_bed_temp: bool = False
    nozzle_temps: List[Dict[str, Any]] = field(default_factory=list)
    bed_temps: List[Dict[str, Any]] = field(default_factory=list)
    temp_changes_in_body: List[Dict[str, Any]] = field(default_factory=list)

    # 속도 관련
    has_feed_rate: bool = False
    speed_stats: Dict[str, Any] = field(default_factory=dict)

    # 익스트루전 관련
    first_extrusion_line: Optional[int] = None
    last_extrusion_line: Optional[int] = None
    extrusion_before_temp_wait: bool = False

    # 구간 정보
    section_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleEngineOutput:
    """룰 엔진 최종 출력"""
    basic_checks: List[BasicCheckResult]
    extracted_data: ExtractedData
    critical_flags: List[str]  # 즉시 F등급 플래그


# ============================================================
# 기본 체크 함수들
# ============================================================
def check_nozzle_temp_exists(
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> BasicCheckResult:
    """노즐 온도 설정 존재 여부"""
    nozzle_temps = [e for e in temp_events if e.cmd in ["M104", "M109"] and e.temp > 0]

    # START 구간에서 설정되었는지
    start_nozzle = [e for e in nozzle_temps
                    if get_section_for_event(e.line_index, boundaries)[0] == GCodeSection.START]

    if not nozzle_temps:
        return BasicCheckResult(
            check_name="nozzle_temp_exists",
            passed=False,
            message="노즐 온도 설정 없음",
            details={"count": 0}
        )

    if not start_nozzle:
        return BasicCheckResult(
            check_name="nozzle_temp_exists",
            passed=True,
            message="노즐 온도 설정 있음 (START 외 구간)",
            details={
                "count": len(nozzle_temps),
                "warning": "START 구간에 온도 설정 권장"
            }
        )

    return BasicCheckResult(
        check_name="nozzle_temp_exists",
        passed=True,
        message="노즐 온도 정상 설정",
        details={"count": len(nozzle_temps), "first_temp": start_nozzle[0].temp}
    )


def check_bed_temp_exists(
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> BasicCheckResult:
    """베드 온도 설정 존재 여부"""
    bed_temps = [e for e in temp_events if e.cmd in ["M140", "M190"] and e.temp > 0]

    if not bed_temps:
        return BasicCheckResult(
            check_name="bed_temp_exists",
            passed=False,
            message="베드 온도 설정 없음 (첫 레이어 접착 실패 위험)",
            details={"count": 0}
        )

    return BasicCheckResult(
        check_name="bed_temp_exists",
        passed=True,
        message="베드 온도 정상 설정",
        details={"count": len(bed_temps), "first_temp": bed_temps[0].temp}
    )


def check_temp_wait_before_extrusion(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> BasicCheckResult:
    """압출 전 온도 대기(M109) 존재 여부"""
    # M109 위치 찾기
    m109_lines = set()
    for e in temp_events:
        if e.cmd == "M109" and e.temp > 0:
            m109_lines.add(e.line_index)

    # 첫 압출 라인 찾기
    first_extrusion = None
    for line in lines:
        if line.cmd == "G1" and "E" in line.params and line.params.get("E", 0) > 0:
            first_extrusion = line.index
            break

    if first_extrusion is None:
        return BasicCheckResult(
            check_name="temp_wait_before_extrusion",
            passed=True,
            message="압출 명령 없음",
            details={}
        )

    # 첫 압출 전에 M109가 있는지
    has_wait = any(m109 < first_extrusion for m109 in m109_lines)

    if not has_wait:
        return BasicCheckResult(
            check_name="temp_wait_before_extrusion",
            passed=False,
            message="온도 대기(M109) 없이 압출 시작",
            details={
                "first_extrusion_line": first_extrusion,
                "has_m109": len(m109_lines) > 0
            }
        )

    return BasicCheckResult(
        check_name="temp_wait_before_extrusion",
        passed=True,
        message="온도 대기 후 압출 시작",
        details={"first_extrusion_line": first_extrusion}
    )


def check_feed_rate_exists(
    lines: List[GCodeLine]
) -> BasicCheckResult:
    """이동 속도(F) 설정 존재 여부"""
    f_values = []
    for line in lines:
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            f_values.append(line.params["F"])

    if not f_values:
        return BasicCheckResult(
            check_name="feed_rate_exists",
            passed=False,
            message="이동 속도(F) 설정 없음",
            details={"count": 0}
        )

    return BasicCheckResult(
        check_name="feed_rate_exists",
        passed=True,
        message="이동 속도 정상 설정",
        details={
            "count": len(f_values),
            "min": min(f_values),
            "max": max(f_values),
            "avg": sum(f_values) / len(f_values)
        }
    )


# ============================================================
# 데이터 추출 함수
# ============================================================
def extract_data_for_llm(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> ExtractedData:
    """LLM 분석을 위한 데이터 추출"""
    data = ExtractedData()

    # 구간 정보
    data.section_info = {
        "start_end": boundaries.start_end,
        "body_end": boundaries.body_end,
        "total_lines": boundaries.total_lines,
        "body_length": boundaries.body_end - boundaries.start_end
    }

    # 온도 이벤트 분류
    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)
        event_data = {
            "line": event.line_index,
            "cmd": event.cmd,
            "temp": event.temp,
            "section": section.value
        }

        if event.cmd in ["M104", "M109"]:
            data.nozzle_temps.append(event_data)
            if event.temp > 0:
                data.has_nozzle_temp = True
        elif event.cmd in ["M140", "M190"]:
            data.bed_temps.append(event_data)
            if event.temp > 0:
                data.has_bed_temp = True

        # BODY에서의 온도 변화 추적
        if section == GCodeSection.BODY:
            data.temp_changes_in_body.append(event_data)

    # 속도 통계
    f_values = []
    print_speeds = []  # E가 있는 G1
    travel_speeds = []  # E가 없는 G0/G1
    current_f = 0.0

    for line in lines:
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            current_f = line.params["F"]
            f_values.append(current_f)

        section, _ = get_section_for_event(line.index, boundaries)
        if section == GCodeSection.BODY and current_f > 0:
            if line.cmd == "G1" and "E" in line.params and line.params.get("E", 0) > 0:
                print_speeds.append(current_f)
            elif line.cmd in ["G0", "G1"] and "E" not in line.params:
                travel_speeds.append(current_f)

    if f_values:
        data.has_feed_rate = True
        data.speed_stats = {
            "min_mms": round(min(f_values) / 60, 1),
            "max_mms": round(max(f_values) / 60, 1),
            "avg_mms": round(sum(f_values) / len(f_values) / 60, 1),
            "print_avg_mms": round(sum(print_speeds) / len(print_speeds) / 60, 1) if print_speeds else 0,
            "travel_avg_mms": round(sum(travel_speeds) / len(travel_speeds) / 60, 1) if travel_speeds else 0,
            "count": len(f_values)
        }

    # 익스트루전 정보
    for line in lines:
        if line.cmd == "G1" and "E" in line.params and line.params.get("E", 0) > 0:
            if data.first_extrusion_line is None:
                data.first_extrusion_line = line.index
            data.last_extrusion_line = line.index

    # 온도 대기 전 압출 체크
    m109_lines = [e.line_index for e in temp_events if e.cmd == "M109" and e.temp > 0]
    if data.first_extrusion_line and m109_lines:
        first_m109 = min(m109_lines) if m109_lines else float('inf')
        data.extrusion_before_temp_wait = data.first_extrusion_line < first_m109

    return data


def detect_critical_flags(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[str]:
    """
    즉시 F등급 판정이 필요한 치명적 플래그 감지
    (명백한 하드웨어 손상 위험만)
    """
    flags = []

    # 1. BODY에서 노즐 온도 0 설정 (H 파라미터 없이)
    for event in temp_events:
        if event.cmd in ["M104", "M109"] and event.temp == 0:
            section, _ = get_section_for_event(event.line_index, boundaries)
            if section == GCodeSection.BODY:
                # 원본 라인에서 H 파라미터 확인
                for line in lines:
                    if line.index == event.line_index:
                        if "H" not in line.raw.upper():
                            flags.append(f"BODY_TEMP_ZERO:line_{event.line_index}")
                        break

    # 2. 온도 0에서 익스트루전 (명백한 콜드 익스트루전)
    current_temp = 0.0
    for line in lines:
        if line.cmd in ["M104", "M109"] and "S" in line.params:
            current_temp = line.params["S"]

        if line.cmd == "G1" and "E" in line.params:
            e_val = line.params.get("E", 0)
            section, _ = get_section_for_event(line.index, boundaries)
            if section == GCodeSection.BODY and e_val > 0 and current_temp == 0:
                flags.append(f"COLD_EXTRUSION_ZERO:line_{line.index}")
                break  # 하나만 감지

    return flags


# ============================================================
# 메인 실행 함수
# ============================================================
def run_basic_checks(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> RuleEngineOutput:
    """
    기본 체크 실행 및 LLM용 데이터 추출

    Returns:
        RuleEngineOutput: 기본 체크 결과 + 추출 데이터 + 치명적 플래그
    """
    # 기본 체크들
    checks = [
        check_nozzle_temp_exists(temp_events, boundaries),
        check_bed_temp_exists(temp_events, boundaries),
        check_temp_wait_before_extrusion(lines, temp_events, boundaries),
        check_feed_rate_exists(lines),
    ]

    # LLM용 데이터 추출
    extracted = extract_data_for_llm(lines, temp_events, boundaries)

    # 치명적 플래그 감지
    critical_flags = detect_critical_flags(lines, temp_events, boundaries)

    return RuleEngineOutput(
        basic_checks=checks,
        extracted_data=extracted,
        critical_flags=critical_flags
    )


# ============================================================
# 하위 호환성 유지 (기존 코드와 호환)
# ============================================================
@dataclass
class RuleResult:
    """단일 규칙 실행 결과 (하위 호환용)"""
    rule_name: str
    triggered: bool
    anomaly: Anomaly | None = None
    confidence: float = 1.0
    needs_llm_review: bool = False


def run_all_rules(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    하위 호환용 - 기본 체크를 RuleResult 형태로 반환
    실제 문제 탐지는 LLM이 수행
    """
    output = run_basic_checks(lines, temp_events, boundaries)
    results = []

    # 기본 체크 실패 → RuleResult로 변환
    for check in output.basic_checks:
        if not check.passed:
            anomaly_type = AnomalyType.COLD_EXTRUSION
            severity = "high"

            if "bed" in check.check_name:
                anomaly_type = AnomalyType.MISSING_BED_TEMP
                severity = "medium"
            elif "temp_wait" in check.check_name:
                anomaly_type = AnomalyType.MISSING_TEMP_WAIT
                severity = "high"
            elif "nozzle" in check.check_name:
                anomaly_type = AnomalyType.COLD_EXTRUSION
                severity = "high"

            results.append(RuleResult(
                rule_name=check.check_name,
                triggered=True,
                anomaly=Anomaly(
                    type=anomaly_type,
                    line_index=check.details.get("first_extrusion_line", 1),
                    severity=severity,
                    message=check.message,
                    context=check.details
                ),
                confidence=0.9,
                needs_llm_review=True  # LLM이 최종 판단
            ))

    # 치명적 플래그 → RuleResult로 변환
    for flag in output.critical_flags:
        flag_type, line_info = flag.split(":")
        line_num = int(line_info.replace("line_", ""))

        results.append(RuleResult(
            rule_name=flag_type.lower(),
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.COLD_EXTRUSION,
                line_index=line_num,
                severity="critical",
                message=f"치명적 문제: {flag_type}",
                context={"flag": flag}
            ),
            confidence=0.99,
            needs_llm_review=False  # 명백한 문제
        ))

    return results


def get_triggered_anomalies(results: List[RuleResult]) -> List[Anomaly]:
    """트리거된 규칙에서 Anomaly만 추출"""
    return [r.anomaly for r in results if r.triggered and r.anomaly]


def get_llm_review_needed(results: List[RuleResult]) -> List[RuleResult]:
    """LLM 검토가 필요한 결과만 필터링"""
    return [r for r in results if r.triggered and r.needs_llm_review]


def get_rule_summary(results: List[RuleResult]) -> Dict[str, Any]:
    """규칙 실행 요약"""
    triggered = [r for r in results if r.triggered]
    by_rule = {}
    for r in triggered:
        by_rule[r.rule_name] = by_rule.get(r.rule_name, 0) + 1

    return {
        "total_rules_run": 4,  # 기본 체크 4개
        "total_triggered": len(triggered),
        "by_rule": by_rule,
        "needs_llm_review": len(get_llm_review_needed(results))
    }
