"""
G-code 분석 룰 엔진
확장 가능한 규칙 기반 이상 탐지 시스템

사용법:
1. 새 규칙 함수 작성 (rules/ 디렉토리)
2. RULES 리스트에 추가
3. 자동으로 분석에 포함됨
"""
from typing import List, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

from .models import GCodeLine, TempEvent, Anomaly, AnomalyType
from .section_detector import SectionBoundaries, GCodeSection, get_section_for_event

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
    """
    results = []
    
    for event in temp_events:
        section, _ = get_section_for_event(event.line_index, boundaries)
        
        # BODY에서 온도 0 설정 = 문제
        if section == GCodeSection.BODY and event.temp == 0:
            results.append(RuleResult(
                rule_name="early_temp_off",
                triggered=True,
                anomaly=Anomaly(
                    type=AnomalyType.EARLY_TEMP_OFF,
                    line_index=event.line_index,
                    severity="high",
                    message=f"출력 중간(BODY)에서 온도 0 설정 ({event.cmd})",
                    context={"section": section.value, "cmd": event.cmd}
                ),
                confidence=0.95,
                needs_llm_review=True
            ))
    
    return results

def rule_cold_extrusion(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> List[RuleResult]:
    """
    규칙: 노즐 온도가 낮은 상태에서 익스트루전 시도
    """
    results = []
    current_temp = 0.0
    SAFE_TEMP = 150.0  # 기본값 (설정 가능)
    
    for line in lines:
        # 온도 업데이트
        if line.cmd in ["M104", "M109"]:
            if "S" in line.params:
                current_temp = line.params["S"]
        
        # 익스트루전 체크
        if line.cmd in ["G1", "G0"] and "E" in line.params:
            e_val = line.params.get("E", 0)
            section, _ = get_section_for_event(line.index, boundaries)
            
            # BODY에서 낮은 온도로 익스트루전
            if section == GCodeSection.BODY and current_temp < SAFE_TEMP and e_val > 0:
                results.append(RuleResult(
                    rule_name="cold_extrusion",
                    triggered=True,
                    anomaly=Anomaly(
                        type=AnomalyType.COLD_EXTRUSION,
                        line_index=line.index,
                        severity="high",
                        message=f"낮은 온도({current_temp}°C)에서 익스트루전 시도",
                        context={"temp": current_temp, "e_val": e_val, "safe_temp": SAFE_TEMP}
                    ),
                    confidence=0.9,
                    needs_llm_review=True
                ))
                break  # 첫 번째만 보고
    
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

# ============================================================
# 룰 엔진 레지스트리
# ============================================================

# 활성화된 규칙 목록 (새 규칙 추가 시 여기에 등록)
RULES: List[RuleFunction] = [
    rule_early_temp_off,
    rule_cold_extrusion,
    rule_rapid_temp_change,
    rule_bed_temp_off_early,
    rule_low_temp_extrusion,
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
