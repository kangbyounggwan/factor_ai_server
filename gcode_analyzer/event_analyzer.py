"""
이벤트 분석기 - Python 규칙 기반 1차 필터링
LLM에 보내기 전에 정상/이상 여부를 판단
"""
from typing import List, Optional
from pydantic import BaseModel
from enum import Enum
from .models import GCodeLine, TempEvent
from .section_detector import GCodeSection, SectionBoundaries, get_section_for_event

class AnomalyConfidence(str, Enum):
    CERTAIN = "certain"       # 확실한 문제 (Python 규칙으로 판정)
    PROBABLE = "probable"     # 문제일 가능성 높음 (LLM 확인 필요)
    UNLIKELY = "unlikely"     # 정상일 가능성 높음
    NORMAL = "normal"         # 정상 (LLM 안 보내도 됨)

class EventAnalysisResult(BaseModel):
    """이벤트 분석 결과"""
    event: dict  # TempEvent as dict
    section: str
    section_info: dict
    
    is_anomaly: bool
    confidence: str  # AnomalyConfidence value
    anomaly_type: Optional[str] = None
    reason: str
    
    # LLM에 보낼지 여부
    needs_llm_analysis: bool
    
    class Config:
        use_enum_values = True

def analyze_temp_event(
    event: TempEvent,
    boundaries: SectionBoundaries,
    lines: List[GCodeLine],
    prev_event: Optional[TempEvent] = None
) -> EventAnalysisResult:
    """
    온도 이벤트를 Python 규칙으로 1차 분석
    
    Returns:
        EventAnalysisResult: 분석 결과
    """
    section, section_info = get_section_for_event(event.line_index, boundaries)
    lines_after = boundaries.total_lines - event.line_index
    
    # 기본값
    is_anomaly = False
    confidence = AnomalyConfidence.NORMAL
    anomaly_type = None
    reason = ""
    needs_llm = False
    
    # ========== 규칙 기반 분석 ==========
    
    # 1. END_GCODE에서 온도 0 설정 → 정상
    if section == GCodeSection.END and event.temp == 0:
        is_anomaly = False
        confidence = AnomalyConfidence.NORMAL
        reason = "종료 G-code에서 온도 끄기는 정상입니다."
        needs_llm = False
    
    # 2. START_GCODE에서 온도 설정 → 정상
    elif section == GCodeSection.START and event.temp > 0:
        is_anomaly = False
        confidence = AnomalyConfidence.NORMAL
        reason = "시작 G-code에서 온도 설정은 정상입니다."
        needs_llm = False
    
    # 3. BODY에서 온도 0 설정 → 문제!
    elif section == GCodeSection.BODY and event.temp == 0:
        is_anomaly = True
        confidence = AnomalyConfidence.CERTAIN
        anomaly_type = "early_temp_off"
        reason = f"출력 중간(BODY 구간)에서 온도를 0으로 설정했습니다. 남은 라인: {lines_after}"
        needs_llm = True
    
    # 4. 급격한 온도 변화 (50도 이상)
    elif prev_event and abs(event.temp - prev_event.temp) >= 50:
        # END에서는 허용
        if section == GCodeSection.END:
            is_anomaly = False
            confidence = AnomalyConfidence.UNLIKELY
            reason = "종료 구간에서 급격한 온도 변화는 일반적입니다."
            needs_llm = False
        else:
            is_anomaly = True
            confidence = AnomalyConfidence.PROBABLE
            anomaly_type = "rapid_temp_change"
            reason = f"온도가 {prev_event.temp}°C → {event.temp}°C로 급격히 변경되었습니다."
            needs_llm = True
    
    # 5. 첫 온도 설정 (START에서) → 정상
    elif prev_event is None and event.temp > 0:
        is_anomaly = False
        confidence = AnomalyConfidence.NORMAL
        reason = "첫 온도 설정입니다."
        needs_llm = False
    
    # 6. 그 외 BODY에서 온도 재설정
    elif section == GCodeSection.BODY and event.temp > 0:
        # 온도 변경이 작으면 정상 (재료 변경 등)
        if prev_event and abs(event.temp - prev_event.temp) < 20:
            is_anomaly = False
            confidence = AnomalyConfidence.UNLIKELY
            reason = f"온도 미세 조정 ({prev_event.temp}°C → {event.temp}°C)"
            needs_llm = False
        else:
            # 검토 필요
            is_anomaly = False
            confidence = AnomalyConfidence.PROBABLE
            reason = f"출력 중 온도 변경 ({event.temp}°C). 의도된 변경인지 확인 필요."
            needs_llm = True
    
    # 기본: 판단 어려움 → LLM에 위임
    else:
        confidence = AnomalyConfidence.PROBABLE
        reason = "추가 분석이 필요합니다."
        needs_llm = True
    
    return EventAnalysisResult(
        event=event.dict(),
        section=section.value,
        section_info=section_info,
        is_anomaly=is_anomaly,
        confidence=confidence.value,
        anomaly_type=anomaly_type,
        reason=reason,
        needs_llm_analysis=needs_llm
    )

def analyze_all_temp_events(
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries,
    lines: List[GCodeLine]
) -> List[EventAnalysisResult]:
    """
    모든 온도 이벤트를 분석하고 결과 반환
    """
    results = []
    prev_event = None
    
    for event in temp_events:
        result = analyze_temp_event(event, boundaries, lines, prev_event)
        results.append(result)
        prev_event = event
    
    return results

def get_summary(results: List[EventAnalysisResult]) -> dict:
    """분석 결과 요약"""
    total = len(results)
    by_section = {"START_GCODE": 0, "BODY": 0, "END_GCODE": 0}
    by_confidence = {"certain": 0, "probable": 0, "unlikely": 0, "normal": 0}
    anomalies = 0
    needs_llm = 0
    
    for r in results:
        by_section[r.section] = by_section.get(r.section, 0) + 1
        by_confidence[r.confidence] = by_confidence.get(r.confidence, 0) + 1
        if r.is_anomaly:
            anomalies += 1
        if r.needs_llm_analysis:
            needs_llm += 1
    
    return {
        "total_events": total,
        "by_section": by_section,
        "by_confidence": by_confidence,
        "confirmed_anomalies": anomalies,
        "needs_llm_analysis": needs_llm,
        "normal_events": total - needs_llm
    }
