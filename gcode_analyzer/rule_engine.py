"""
G-code 분석 룰 엔진
확장 가능한 규칙 기반 이상 탐지 시스템

사용법:
1. 새 규칙 함수 작성 (rules/ 디렉토리)
2. RULES 리스트에 추가
3. 자동으로 분석에 포함됨
"""
from typing import List, Callable, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re

from .models import GCodeLine, TempEvent, Anomaly, AnomalyType
from .section_detector import SectionBoundaries, GCodeSection, get_section_for_event


# ============================================================
# 벤더 확장 코드 감지 (H코드 등)
# ============================================================
def _detect_vendor_h_param(raw_line: str) -> Optional[Dict[str, Any]]:
    """
    Bambu/Orca 등 벤더 확장 H 파라미터 감지

    예시:
    - M109 S25 H140 → H=140 (실제 온도), S=25 (대기 시간 또는 다른 의미)
    - M104 H210 → H=210 (실제 온도)

    Returns:
        {"H": 온도값, "vendor": "bambu"} 또는 None
    """
    if not raw_line:
        return None

    # H 파라미터 감지 (온도 관련 명령에서)
    h_match = re.search(r'\bH(\d+(?:\.\d+)?)', raw_line, re.IGNORECASE)
    if h_match:
        h_value = float(h_match.group(1))
        return {
            "H": h_value,
            "vendor": "bambu",
            "note": "제조사 커스텀 코드 - H 파라미터가 실제 온도값일 수 있음"
        }

    return None


def _is_vendor_extended_temp_cmd(line: GCodeLine) -> Optional[Dict[str, Any]]:
    """
    온도 명령에서 벤더 확장이 있는지 확인

    Bambu/Orca에서:
    - M109 S25 H140: S는 대기 시간, H가 실제 온도
    - 이 경우 S값을 온도로 해석하면 안 됨

    Returns:
        벤더 확장 정보 또는 None
    """
    if line.cmd not in ["M104", "M109", "M140", "M190"]:
        return None

    return _detect_vendor_h_param(line.raw)

# ============================================================
# 룰 정의 타입
# ============================================================
@dataclass
class RuleResult:
    """단일 규칙 실행 결과"""
    rule_name: str
    triggered: bool
    anomaly: Anomaly | None = None
    confidence: float = 1.0  # 0.0 ~ 1.0
    needs_llm_review: bool = False  # LLM 추가 검토 필요 여부

RuleFunction = Callable[
    [List[GCodeLine], List[TempEvent], SectionBoundaries],
    List[RuleResult]
]

# ============================================================
# 개별 규칙 함수들
# ============================================================

def rule_early_temp_off(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 출력 중간(BODY)에서 온도가 0으로 설정됨

    주의: Bambu/Orca 등에서 H 파라미터가 있으면 S값이 온도가 아닐 수 있음
    - M109 S25 H140 → S=대기시간, H=실제 온도
    """
    results = []

    # 라인 인덱스로 원본 라인 찾기 위한 맵 생성
    line_map = {line.index: line for line in lines}

    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)

        # BODY에서 온도 0 설정
        if section == GCodeSection.BODY and event.temp == 0:
            # 원본 라인에서 벤더 확장(H 파라미터) 확인
            original_line = line_map.get(event.line_index)
            vendor_ext = None
            if original_line:
                vendor_ext = _is_vendor_extended_temp_cmd(original_line)

            # H 파라미터가 있으면 → 주의(warning)로 다운그레이드
            if vendor_ext and vendor_ext.get("H", 0) > 0:
                actual_temp = vendor_ext.get("H", 0)
                results.append(RuleResult(
                    rule_name="early_temp_off",
                    triggered=True,
                    anomaly=Anomaly(
                        type=AnomalyType.EARLY_TEMP_OFF,
                        line_index=event.line_index,
                        severity="warning",  # critical → warning 다운그레이드
                        message=f"[주의] 제조사 커스텀 코드 감지 ({event.cmd} S0 H{actual_temp}) - H 파라미터가 실제 온도({actual_temp}°C)일 수 있음, 확인 필요",
                        context={
                            "section": section.value,
                            "cmd": event.cmd,
                            "s_value": 0,
                            "h_value": actual_temp,
                            "vendor": vendor_ext.get("vendor"),
                            "vendor_extension": True,
                            "note": "Bambu/Orca 슬라이서의 H 파라미터는 실제 타겟 온도를 의미할 수 있습니다"
                        }
                    ),
                    confidence=0.6,  # 낮은 신뢰도 - LLM 검토 필요
                    needs_llm_review=True  # LLM이 최종 판단
                ))
            else:
                # H 파라미터 없음 → 진짜 치명적 문제
                results.append(RuleResult(
                    rule_name="early_temp_off",
                    triggered=True,
                    anomaly=Anomaly(
                        type=AnomalyType.EARLY_TEMP_OFF,
                        line_index=event.line_index,
                        severity="critical",  # 진짜 critical
                        message=f"[치명적] 출력 중 온도 0°C 설정 ({event.cmd}) - 콜드 익스트루전 위험, 출력 금지",
                        context={"section": section.value, "cmd": event.cmd, "temp": 0}
                    ),
                    confidence=0.99,
                    needs_llm_review=False  # 이건 LLM 검토 불필요, 무조건 문제
                ))

    return results

def rule_cold_extrusion(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙 [A2 강화]: 노즐 온도가 낮은 상태에서 익스트루전 시도

    [A2] 강화 사항:
    1. 타겟 온도 기준으로 판단 (M104/M109 직후)
    2. 예열 대기 패턴 인식 (M109 S140 후 익스트루전 없으면 정상)
    3. H 파라미터(Bambu 확장) 지원

    예열 대기 패턴 (정상):
    - M109 S140 (예열 대기) → 50줄 내 익스트루전 없음 → 정상 예열 시퀀스
    """
    results = []
    current_temp = 0.0
    current_h_temp = None  # 벤더 확장 H 파라미터 온도
    has_vendor_extension = False
    last_temp_cmd_line = -1  # 마지막 온도 명령 라인
    SAFE_TEMP = 150.0  # 기본값 (PLA 기준)
    PREHEAT_TEMP = 140.0  # 예열 온도 기준

    for i, line in enumerate(lines):
        # 온도 업데이트
        if line.cmd in ["M104", "M109"]:
            # 벤더 확장(H 파라미터) 확인
            vendor_ext = _is_vendor_extended_temp_cmd(line)
            if vendor_ext and vendor_ext.get("H", 0) > 0:
                # H 파라미터가 있으면 이를 실제 온도로 사용
                current_h_temp = vendor_ext.get("H", 0)
                current_temp = current_h_temp  # H를 실제 온도로 취급
                has_vendor_extension = True
            elif "S" in line.params:
                current_temp = line.params["S"]
                current_h_temp = None
                has_vendor_extension = False
            last_temp_cmd_line = i

        # 익스트루전 체크
        if line.cmd in ["G1", "G0"] and "E" in line.params:
            e_val = line.params.get("E", 0)
            section, _ = get_section_for_event(line.index, boundaries)

            # BODY에서만 체크 (START/END는 무시)
            if section != GCodeSection.BODY:
                continue

            # 양의 익스트루전만 체크
            if e_val <= 0:
                continue

            # [C2] 예열 대기 패턴 체크
            # M109 S140 같은 낮은 온도 후 50줄 내에 익스트루전이 없으면 정상 예열
            if PREHEAT_TEMP <= current_temp < SAFE_TEMP:
                # 온도 명령 이후 바로 익스트루전이 있는지 확인
                lines_since_temp = i - last_temp_cmd_line if last_temp_cmd_line >= 0 else 999

                # 온도 명령 직후(50줄 이내)가 아니면 → 이미 다른 온도로 변경됐을 가능성
                if lines_since_temp > 50:
                    continue  # 예열 시퀀스로 간주, 스킵

            # 낮은 온도에서 익스트루전
            if current_temp < SAFE_TEMP:
                # 벤더 확장이 있고 H 온도가 정상 범위면 → 주의로 다운그레이드
                if has_vendor_extension and current_h_temp and current_h_temp >= SAFE_TEMP:
                    results.append(RuleResult(
                        rule_name="cold_extrusion",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.COLD_EXTRUSION,
                            line_index=line.index,
                            severity="warning",  # critical → warning 다운그레이드
                            message=f"[주의] 제조사 커스텀 코드 사용 중 - H 파라미터({current_h_temp}°C)가 실제 온도일 수 있음",
                            context={
                                "s_temp": line.params.get("S", 0),
                                "h_temp": current_h_temp,
                                "e_val": e_val,
                                "safe_temp": SAFE_TEMP,
                                "vendor_extension": True,
                                "note": "Bambu/Orca 슬라이서의 H 파라미터는 실제 타겟 온도를 의미할 수 있습니다"
                            }
                        ),
                        confidence=0.5,  # 낮은 신뢰도
                        needs_llm_review=True
                    ))
                    break
                # 온도 0°C는 critical
                elif current_temp == 0:
                    results.append(RuleResult(
                        rule_name="cold_extrusion",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.COLD_EXTRUSION,
                            line_index=line.index,
                            severity="critical",
                            message=f"[치명적] 온도 0°C에서 익스트루전 시도 - 노즐 막힘, 모터 손상 위험",
                            context={"temp": current_temp, "e_val": e_val, "safe_temp": SAFE_TEMP}
                        ),
                        confidence=0.95,
                        needs_llm_review=False
                    ))
                    break
                # 매우 낮은 온도 (100°C 미만) → critical
                elif current_temp < 100:
                    results.append(RuleResult(
                        rule_name="cold_extrusion",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.COLD_EXTRUSION,
                            line_index=line.index,
                            severity="critical",
                            message=f"[치명적] 매우 낮은 온도({current_temp}°C)에서 익스트루전 - 콜드 익스트루전 위험",
                            context={
                                "temp": current_temp,
                                "e_val": e_val,
                                "safe_temp": SAFE_TEMP,
                                "issue_type": "low_target_temp_extrusion"
                            }
                        ),
                        confidence=0.9,
                        needs_llm_review=False
                    ))
                    break
                # 그 외 낮은 온도 → high
                else:
                    results.append(RuleResult(
                        rule_name="cold_extrusion",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.COLD_EXTRUSION,
                            line_index=line.index,
                            severity="high",
                            message=f"낮은 온도({current_temp}°C)에서 익스트루전 시도 (권장: {SAFE_TEMP}°C 이상)",
                            context={"temp": current_temp, "e_val": e_val, "safe_temp": SAFE_TEMP}
                        ),
                        confidence=0.85,
                        needs_llm_review=True
                    ))
                    break

    return results

def rule_rapid_temp_change(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 급격한 온도 변화 (50도 이상)
    """
    results = []
    prev_temp = None
    THRESHOLD = 50.0
    
    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)
        
        if prev_temp is not None:
            diff = abs(event.temp - prev_temp)
            
            # BODY에서 급격한 온도 변화
            if section == GCodeSection.BODY and diff >= THRESHOLD:
                results.append(RuleResult(
                    rule_name="rapid_temp_change",
                    triggered=True,
                    anomaly=Anomaly(
                        type=AnomalyType.RAPID_TEMP_CHANGE,
                        line_index=event.line_index,
                        severity="medium",
                        message=f"급격한 온도 변화: {prev_temp}°C → {event.temp}°C (차이: {diff}°C)",
                        context={"prev_temp": prev_temp, "new_temp": event.temp, "diff": diff}
                    ),
                    confidence=0.8,
                    needs_llm_review=True
                ))
        
        prev_temp = event.temp
    
    return results

def rule_bed_temp_off_early(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 베드 온도가 프린팅 완료 전에 꺼짐
    """
    results = []
    
    for event in temp_events:
        section, section_info = get_section_for_event(event.line_index, boundaries)
        
        # BODY에서 베드 온도 0 설정
        if section == GCodeSection.BODY and event.cmd == "M140" and event.temp == 0:
            lines_after = section_info["total_lines"] - event.line_index
            
            # 아직 많이 남았으면 문제
            if lines_after > 100:
                results.append(RuleResult(
                    rule_name="bed_temp_off_early",
                    triggered=True,
                    anomaly=Anomaly(
                        type=AnomalyType.EARLY_TEMP_OFF,
                        line_index=event.line_index,
                        severity="medium",
                        message=f"프린팅 완료 전 베드 온도 꺼짐 (남은 라인: {lines_after})",
                        context={"lines_after": lines_after}
                    ),
                    confidence=0.85,
                    needs_llm_review=True
                ))
    
    return results

def rule_low_temp_extrusion(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 비정상적으로 낮은 온도로 설정 (PLA 기준 180도 미만)
    """
    results = []
    MIN_REASONABLE_TEMP = 100.0  # 이 이하는 확실히 이상

    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)

        # START에서는 무시 (예열 전)
        if section == GCodeSection.START:
            continue

        # END에서는 무시 (냉각)
        if section == GCodeSection.END:
            continue

        # BODY에서 낮은 온도 설정 (0은 아니지만 낮음)
        if event.cmd in ["M104", "M109"] and 0 < event.temp < MIN_REASONABLE_TEMP:
            results.append(RuleResult(
                rule_name="low_temp_extrusion",
                triggered=True,
                anomaly=Anomaly(
                    type=AnomalyType.COLD_EXTRUSION,
                    line_index=event.line_index,
                    severity="high",
                    message=f"비정상적으로 낮은 노즐 온도 설정: {event.temp}°C",
                    context={"temp": event.temp, "min_reasonable": MIN_REASONABLE_TEMP}
                ),
                confidence=0.9,
                needs_llm_review=True
            ))

    return results


def rule_unexpected_temp_change_in_body(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: BODY 구간에서 급격한 온도 변경 명령 감지

    정상 패턴: START에서 온도 설정 → BODY에서 프린팅만 → END에서 온도 끄기
    비정상: BODY 중간에 급격한 온도 변경 명령 (20°C 이상 변화)

    미세 조정 (20°C 미만)은 정상으로 간주:
    - 필라멘트 교체
    - 브릿지/오버행 등 특수 구간
    - 멀티 컬러 프린팅
    """
    results = []

    # 임계값 설정
    NOZZLE_SIGNIFICANT_CHANGE = 20  # 노즐: 20°C 이상 변화만 감지
    BED_SIGNIFICANT_CHANGE = 15     # 베드: 15°C 이상 변화만 감지
    CRITICAL_CHANGE = 50            # 50°C 이상 변화는 critical

    # START 구간의 마지막 노즐/베드 온도 기록
    last_nozzle_temp = None
    last_bed_temp = None

    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)

        if section == GCodeSection.START:
            # START에서 설정된 온도 기록
            if event.cmd in ["M104", "M109"]:
                last_nozzle_temp = event.temp
            elif event.cmd in ["M140", "M190"]:
                last_bed_temp = event.temp

        elif section == GCodeSection.BODY:
            # BODY에서 온도 변경 감지 (S0 = 끄기는 다른 규칙에서 처리)
            if event.temp == 0:
                continue  # early_temp_off 규칙에서 처리

            # 노즐 온도 변경
            if event.cmd in ["M104", "M109"]:
                if last_nozzle_temp is not None:
                    diff = event.temp - last_nozzle_temp
                    abs_diff = abs(diff)

                    # 미세 조정은 무시 (정상)
                    if abs_diff < NOZZLE_SIGNIFICANT_CHANGE:
                        last_nozzle_temp = event.temp
                        continue

                    # 급격한 변화 감지
                    severity = "high" if abs_diff >= CRITICAL_CHANGE else "medium"
                    needs_review = abs_diff >= CRITICAL_CHANGE  # 큰 변화만 LLM 리뷰

                    results.append(RuleResult(
                        rule_name="unexpected_temp_change",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.RAPID_TEMP_CHANGE,
                            line_index=event.line_index,
                            severity=severity,
                            message=f"BODY 구간에서 노즐 온도 변경: {last_nozzle_temp}°C → {event.temp}°C ({'+' if diff > 0 else ''}{diff}°C)",
                            context={
                                "prev_temp": last_nozzle_temp,
                                "new_temp": event.temp,
                                "diff": diff,
                                "type": "nozzle"
                            }
                        ),
                        confidence=0.85,
                        needs_llm_review=needs_review
                    ))
                # 온도 업데이트 (연속 변경 추적)
                last_nozzle_temp = event.temp

            # 베드 온도 변경
            elif event.cmd in ["M140", "M190"]:
                if last_bed_temp is not None:
                    diff = event.temp - last_bed_temp
                    abs_diff = abs(diff)

                    # 미세 조정은 무시 (정상)
                    if abs_diff < BED_SIGNIFICANT_CHANGE:
                        last_bed_temp = event.temp
                        continue

                    results.append(RuleResult(
                        rule_name="unexpected_temp_change",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.RAPID_TEMP_CHANGE,
                            line_index=event.line_index,
                            severity="low",  # 베드 온도 변경은 덜 심각
                            message=f"BODY 구간에서 베드 온도 변경: {last_bed_temp}°C → {event.temp}°C ({'+' if diff > 0 else ''}{diff}°C)",
                            context={
                                "prev_temp": last_bed_temp,
                                "new_temp": event.temp,
                                "diff": diff,
                                "type": "bed"
                            }
                        ),
                        confidence=0.8,
                        needs_llm_review=False  # 베드 온도 변경은 LLM 리뷰 불필요
                    ))
                last_bed_temp = event.temp

    return results


# ============================================================
# [A1] 히터 끄기 후 익스트루전 감지 (END 코드 잘못 삽입)
# ============================================================

def rule_extrusion_after_heater_off(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙 [A1]: 히터 끄기(M104 S0 / M140 S0) 후에 익스트루전(G1 E+) 발생

    원인: END 코드가 중간에 잘못 삽입되었거나, 슬라이서 설정 오류

    심각도: critical (노즐 막힘, 출력 실패 위험)
    """
    results = []

    # 히터 끄기 명령 위치 추적
    heater_off_events = []

    for i, line in enumerate(lines):
        # M104 S0 / M109 S0 (노즐 히터 끄기)
        if line.cmd in ["M104", "M109"] and line.params.get("S") == 0:
            # H 파라미터 확인 (Bambu 확장)
            vendor_ext = _is_vendor_extended_temp_cmd(line)
            if vendor_ext and vendor_ext.get("H", 0) > 0:
                continue  # H 파라미터가 있으면 실제로 끄는 게 아님

            section, _ = get_section_for_event(i, boundaries)

            # END 구간에서의 M104 S0은 정상
            if section == GCodeSection.END:
                continue

            heater_off_events.append({
                "line_index": i,
                "cmd": line.cmd,
                "section": section.value
            })

    # 히터 끄기 후 익스트루전 찾기
    for heater_off in heater_off_events:
        off_line = heater_off["line_index"]

        # 히터 끄기 후 50줄 이내에서 양의 익스트루전 찾기
        extrusion_after = []
        for j in range(off_line + 1, min(off_line + 50, len(lines))):
            line = lines[j]

            # 다시 히터 켜기 명령이 나오면 중단
            if line.cmd in ["M104", "M109"] and line.params.get("S", 0) > 0:
                break

            # 양의 익스트루전 감지
            if line.cmd == "G1" and "E" in line.params:
                e_val = line.params.get("E", 0)
                if e_val > 0:
                    extrusion_after.append(j)
                    if len(extrusion_after) >= 3:  # 3번 이상 발견되면 충분
                        break

        # 익스트루전이 발견되면 문제
        if extrusion_after:
            results.append(RuleResult(
                rule_name="extrusion_after_heater_off",
                triggered=True,
                anomaly=Anomaly(
                    type=AnomalyType.COLD_EXTRUSION,
                    line_index=off_line,
                    severity="critical",
                    message=f"[치명적] 히터 끄기({heater_off['cmd']} S0) 후 익스트루전 발생 - END 코드가 잘못 삽입되었거나 설정 오류",
                    context={
                        "heater_off_line": off_line,
                        "extrusion_lines": extrusion_after[:3],
                        "extrusion_count": len(extrusion_after),
                        "section": heater_off["section"],
                        "issue_type": "end_code_misplaced"
                    }
                ),
                confidence=0.95,
                needs_llm_review=False  # 명확한 오류
            ))
            break  # 첫 번째만 보고

    return results


# ============================================================
# [A3] BODY 구간 내 과도한 온도 대기 (M109/M190)
# ============================================================

def rule_excessive_temp_wait_in_body(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙 [A3]: BODY 구간에서 M109/M190 (블로킹 온도 대기) 과다 사용

    문제: 불필요한 대기로 출력 시간 증가
    정상 케이스: 멀티 컬러 출력, 필라멘트 교체 시에는 정상

    기준: BODY에서 M109/M190 5회 이상 → medium severity
    """
    results = []

    body_temp_waits = []

    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)

        # BODY 구간에서 M109/M190 (블로킹 대기)
        if section == GCodeSection.BODY and event.cmd in ["M109", "M190"]:
            # 온도 0 설정은 제외 (다른 룰에서 처리)
            if event.temp > 0:
                body_temp_waits.append({
                    "line_index": event.line_index,
                    "cmd": event.cmd,
                    "temp": event.temp
                })

    # 5회 이상이면 경고
    if len(body_temp_waits) >= 5:
        first_wait = body_temp_waits[0]
        results.append(RuleResult(
            rule_name="excessive_temp_wait_in_body",
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.RAPID_TEMP_CHANGE,  # 적절한 타입 없으면 이걸로
                line_index=first_wait["line_index"],
                severity="medium",
                message=f"BODY 구간에서 온도 대기 명령({first_wait['cmd']}) {len(body_temp_waits)}회 발생 - 출력 시간 증가 가능",
                context={
                    "wait_count": len(body_temp_waits),
                    "wait_lines": [w["line_index"] for w in body_temp_waits[:10]],
                    "commands": list(set(w["cmd"] for w in body_temp_waits))
                }
            ),
            confidence=0.7,
            needs_llm_review=True  # 멀티 컬러 등 정상 케이스 가능
        ))

    return results


# ============================================================
# 속도 관련 규칙들
# ============================================================

# 속도 기준값 (G-code F 값은 mm/min 단위)
# mm/s로 변환: F값 / 60
SPEED_THRESHOLDS = {
    # 최대 속도 제한 (mm/s 기준)
    "max_print_speed_mms": 500,      # 500 mm/s (극한 속도, F30000)
    "max_travel_speed_mms": 700,     # 700 mm/s (최대 travel, F42000)
    "max_reasonable_print_mms": 300, # 300 mm/s (합리적 최대, F18000)

    # 최소 속도 제한
    "min_print_speed_mms": 5,        # 5 mm/s (너무 느림, F300)

    # 품질 권장 범위 (Bambu/Orca 기준)
    "quality_print_min_mms": 30,     # 30 mm/s (고품질)
    "quality_print_max_mms": 150,    # 150 mm/s (표준 품질)

    # 급격한 속도 변화 임계값
    "rapid_change_threshold_mms": 100,  # 100 mm/s 이상 급변
}


def rule_excessive_print_speed(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 과도하게 빠른 출력 속도 감지

    Bambu/Orca 기준:
    - 일반 출력: 70-150 mm/s
    - 빠른 출력: 150-300 mm/s
    - 극한 출력: 300+ mm/s (품질 저하 위험)

    Note: G-code F값은 mm/min 단위
    Note: F값은 한 번 설정되면 이후 명령에서 생략될 수 있음 (상태 추적 필요)
    """
    results = []
    MAX_REASONABLE = SPEED_THRESHOLDS["max_reasonable_print_mms"] * 60  # → mm/min
    MAX_EXTREME = SPEED_THRESHOLDS["max_print_speed_mms"] * 60

    excessive_count = 0
    extreme_count = 0
    first_excessive_line = None
    max_speed_found = 0
    current_f = 0.0  # 현재 F값 추적

    for line in lines:
        # F값 업데이트 (G0, G1 모두에서)
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            current_f = line.params["F"]

        section, _ = get_section_for_event(line.index, boundaries)

        # BODY 구간에서만 체크
        if section != GCodeSection.BODY:
            continue

        # G1 명령어 + E (출력 이동) - F는 현재 추적값 사용
        if line.cmd == "G1" and "E" in line.params:
            e_val = line.params.get("E", 0)

            # 양의 E = 실제 출력
            if e_val > 0 and current_f > 0:
                if current_f > max_speed_found:
                    max_speed_found = current_f

                if current_f > MAX_EXTREME:
                    extreme_count += 1
                    if first_excessive_line is None:
                        first_excessive_line = line.index
                elif current_f > MAX_REASONABLE:
                    excessive_count += 1
                    if first_excessive_line is None:
                        first_excessive_line = line.index

    # 극한 속도 발견 (500+ mm/s)
    if extreme_count > 0:
        results.append(RuleResult(
            rule_name="excessive_print_speed",
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.EXCESSIVE_SPEED,
                line_index=first_excessive_line or 0,
                severity="high",
                message=f"극한 출력 속도 감지: {max_speed_found/60:.0f} mm/s (권장 최대: {SPEED_THRESHOLDS['max_reasonable_print_mms']} mm/s)",
                context={
                    "max_speed_mms": round(max_speed_found / 60, 1),
                    "max_speed_mmmin": max_speed_found,
                    "extreme_count": extreme_count,
                    "threshold_mms": SPEED_THRESHOLDS["max_print_speed_mms"]
                }
            ),
            confidence=0.85,
            needs_llm_review=True
        ))
    elif excessive_count > 10:  # 빠른 속도가 자주 나타나면
        results.append(RuleResult(
            rule_name="excessive_print_speed",
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.EXCESSIVE_SPEED,
                line_index=first_excessive_line or 0,
                severity="medium",
                message=f"빠른 출력 속도 빈번: 최대 {max_speed_found/60:.0f} mm/s ({excessive_count}회 초과)",
                context={
                    "max_speed_mms": round(max_speed_found / 60, 1),
                    "excessive_count": excessive_count,
                    "threshold_mms": SPEED_THRESHOLDS["max_reasonable_print_mms"]
                }
            ),
            confidence=0.7,
            needs_llm_review=True
        ))

    return results


def rule_too_slow_print_speed(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 너무 느린 출력 속도 감지

    5 mm/s (F300) 미만은 거의 정지 수준으로, 의도적이지 않은 경우 문제
    Note: F값은 한 번 설정되면 이후 명령에서 생략될 수 있음
    """
    results = []
    MIN_SPEED = SPEED_THRESHOLDS["min_print_speed_mms"] * 60  # → mm/min

    slow_count = 0
    first_slow_line = None
    min_speed_found = float('inf')
    current_f = 0.0  # 현재 F값 추적

    for line in lines:
        # F값 업데이트
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            current_f = line.params["F"]

        section, _ = get_section_for_event(line.index, boundaries)

        if section != GCodeSection.BODY:
            continue

        # G1 + E (출력 이동)에서 매우 느린 속도
        if line.cmd == "G1" and "E" in line.params:
            e_val = line.params.get("E", 0)

            if e_val > 0 and 0 < current_f < MIN_SPEED:
                slow_count += 1
                if current_f < min_speed_found:
                    min_speed_found = current_f
                if first_slow_line is None:
                    first_slow_line = line.index

    if slow_count > 5:  # 5회 이상 발생
        results.append(RuleResult(
            rule_name="too_slow_print_speed",
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.INCONSISTENT_SPEED,
                line_index=first_slow_line or 0,
                severity="low",
                message=f"매우 느린 출력 속도 감지: {min_speed_found/60:.1f} mm/s ({slow_count}회)",
                context={
                    "min_speed_mms": round(min_speed_found / 60, 2),
                    "min_speed_mmmin": min_speed_found,
                    "slow_count": slow_count,
                    "threshold_mms": SPEED_THRESHOLDS["min_print_speed_mms"]
                }
            ),
            confidence=0.6,
            needs_llm_review=True
        ))

    return results


def rule_zero_speed_extrusion(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 속도 0 또는 F값 없이 익스트루전 시도

    이는 명백한 오류로, 프린터가 멈춘 상태에서 필라멘트만 밀어내는 상황
    """
    results = []
    current_f = 0.0

    for line in lines:
        section, _ = get_section_for_event(line.index, boundaries)

        # F값 추적
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            current_f = line.params["F"]

        # BODY에서 F=0 또는 F 미설정 상태로 익스트루전
        if section == GCodeSection.BODY and line.cmd == "G1":
            if "E" in line.params and line.params.get("E", 0) > 0:
                if current_f == 0:
                    results.append(RuleResult(
                        rule_name="zero_speed_extrusion",
                        triggered=True,
                        anomaly=Anomaly(
                            type=AnomalyType.ZERO_SPEED_EXTRUSION,
                            line_index=line.index,
                            severity="high",
                            message="속도 0 (F=0) 상태에서 익스트루전 시도 - 프린터 정지 상태에서 필라멘트 압출",
                            context={"current_f": current_f, "e_val": line.params.get("E", 0)}
                        ),
                        confidence=0.95,
                        needs_llm_review=False
                    ))
                    break  # 첫 번째만

    return results


def rule_rapid_speed_change(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 급격한 속도 변화 감지

    출력 중 100 mm/s 이상 급변은 품질 저하 및 기계적 스트레스 유발
    Note: F값은 한 번 설정되면 이후 명령에서 생략될 수 있음 (상태 추적 필요)
    """
    results = []
    THRESHOLD = SPEED_THRESHOLDS["rapid_change_threshold_mms"] * 60  # → mm/min

    current_f = 0.0  # 현재 F값 추적
    prev_print_speed = None
    rapid_changes = []

    for line in lines:
        # F값 업데이트 (G0, G1 모두에서)
        if line.cmd in ["G0", "G1"] and "F" in line.params:
            current_f = line.params["F"]

        section, _ = get_section_for_event(line.index, boundaries)

        if section != GCodeSection.BODY:
            continue

        # G1 + E (출력 이동)의 속도 추적 - F는 현재 추적값 사용
        if line.cmd == "G1" and "E" in line.params:
            e_val = line.params.get("E", 0)
            if e_val <= 0:
                continue  # 리트랙션은 제외

            if current_f > 0:
                if prev_print_speed is not None:
                    diff = abs(current_f - prev_print_speed)
                    if diff >= THRESHOLD:
                        rapid_changes.append({
                            "line": line.index,
                            "prev_mms": prev_print_speed / 60,
                            "new_mms": current_f / 60,
                            "diff_mms": diff / 60
                        })

                prev_print_speed = current_f

    if len(rapid_changes) > 0:
        # 가장 큰 변화 찾기
        max_change = max(rapid_changes, key=lambda x: x["diff_mms"])

        severity = "medium" if len(rapid_changes) < 10 else "high"

        results.append(RuleResult(
            rule_name="rapid_speed_change",
            triggered=True,
            anomaly=Anomaly(
                type=AnomalyType.INCONSISTENT_SPEED,
                line_index=max_change["line"],
                severity=severity,
                message=f"급격한 속도 변화 {len(rapid_changes)}회 감지. 최대: {max_change['prev_mms']:.0f} → {max_change['new_mms']:.0f} mm/s (차이: {max_change['diff_mms']:.0f} mm/s)",
                context={
                    "change_count": len(rapid_changes),
                    "max_change": max_change,
                    "threshold_mms": SPEED_THRESHOLDS["rapid_change_threshold_mms"]
                }
            ),
            confidence=0.75,
            needs_llm_review=True
        ))

    return results


# ============================================================
# 룰 엔진 레지스트리
# ============================================================

# 활성화된 규칙 목록 (새 규칙 추가 시 여기에 등록)
RULES: List[RuleFunction] = [
    # 온도 관련 (핵심)
    rule_extrusion_after_heater_off,  # [A1] 히터 끄기 후 익스트루전 (critical)
    rule_early_temp_off,
    rule_cold_extrusion,
    rule_rapid_temp_change,
    rule_bed_temp_off_early,
    rule_low_temp_extrusion,
    rule_unexpected_temp_change_in_body,
    rule_excessive_temp_wait_in_body,  # [A3] BODY 내 과도한 온도 대기
    # 속도 관련
    rule_excessive_print_speed,
    rule_too_slow_print_speed,
    rule_zero_speed_extrusion,
    rule_rapid_speed_change,
]

def run_all_rules(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    모든 규칙 실행 및 결과 수집
    """
    all_results = []
    
    for rule in RULES:
        try:
            results = rule(lines, temp_events, boundaries)
            all_results.extend(results)
        except Exception as e:
            # 개별 규칙 오류가 전체를 중단시키지 않음
            print(f"Warning: Rule {rule.__name__} failed: {e}")
    
    return all_results

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
        "total_rules_run": len(RULES),
        "total_triggered": len(triggered),
        "by_rule": by_rule,
        "needs_llm_review": len(get_llm_review_needed(results))
    }
