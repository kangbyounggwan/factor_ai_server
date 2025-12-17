"""
G-code 분석 룰 엔진 (최적화 버전)
기본 체크만 수행 - 실제 문제 탐지는 LLM이 담당

역할:
1. 프린터 컨텍스트 감지 (슬라이서/설비/펌웨어)
2. 필수 설정 존재 여부 체크 (온도, 베드 등)
3. 데이터 추출 및 정리 (LLM 전달용)
4. 명백한 구조적 오류만 감지

분석 흐름:
컨텍스트 감지 -> 기본 체크 -> LLM 분석 -> 최종 취합

모듈 구조:
- rules/base.py: 기본 룰 엔진 (표준 G-code)
- rules/klipper.py: Klipper 특화 룰
- rules/bambu.py: Bambu Lab 특화 룰
- rules/factory.py: 컨텍스트 기반 엔진 선택

사용법:
    # 방법 1: 컨텍스트 기반 자동 선택 (권장)
    from gcode_analyzer.rule_engine import run_analysis_with_context
    result = run_analysis_with_context(lines, temp_events, boundaries)

    # 방법 2: 직접 엔진 선택
    from gcode_analyzer.segment_extractor import detect_printer_context
    from gcode_analyzer.rule_engine import get_rule_engine
    context = detect_printer_context(lines)
    engine = get_rule_engine(context)
    result = engine.run_checks(lines, temp_events, boundaries)

    # 방법 3: 하위 호환 (기존 코드용)
    from gcode_analyzer.rule_engine import run_basic_checks
    result = run_basic_checks(lines, temp_events, boundaries)
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .models import GCodeLine, TempEvent, Anomaly, AnomalyType
from .section_detector import SectionBoundaries, GCodeSection, get_section_for_event
from .segment_extractor import (
    PrinterContext, detect_printer_context,
    SlicerType, EquipmentType, FirmwareType
)

# 새 모듈에서 import
from .rules.base import (
    BaseRuleEngine,
    BasicCheckResult,
    ExtractedData,
    RuleEngineOutput
)
from .rules.klipper import KlipperRuleEngine
from .rules.bambu import BambuRuleEngine
from .rules.factory import (
    get_rule_engine,
    run_analysis_with_context,
    RuleEngineFactory
)


# ============================================================
# 하위 호환성 함수들
# ============================================================
def run_basic_checks(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries,
    context: Optional[PrinterContext] = None
) -> RuleEngineOutput:
    """
    기본 체크 실행 및 LLM용 데이터 추출

    컨텍스트가 주어지면 적절한 룰 엔진 자동 선택
    컨텍스트가 없으면 자동 감지

    Args:
        lines: 파싱된 G-code 라인
        temp_events: 온도 이벤트
        boundaries: 섹션 경계
        context: 프린터 컨텍스트 (선택, 없으면 자동 감지)

    Returns:
        RuleEngineOutput: 기본 체크 결과 + 추출 데이터 + 치명적 플래그
    """
    return run_analysis_with_context(lines, temp_events, boundaries, context)


def extract_data_for_llm(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries
) -> ExtractedData:
    """
    LLM 분석을 위한 데이터 추출 (하위 호환용)

    새 코드에서는 run_basic_checks() 또는 engine.run_checks() 사용 권장
    """
    engine = BaseRuleEngine()
    return engine._extract_data(lines, temp_events, boundaries)


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


# ============================================================
# Re-export for convenience
# ============================================================
__all__ = [
    # 새 API
    'run_analysis_with_context',
    'get_rule_engine',
    'RuleEngineFactory',
    'BaseRuleEngine',
    'KlipperRuleEngine',
    'BambuRuleEngine',
    'BasicCheckResult',
    'ExtractedData',
    'RuleEngineOutput',
    # 컨텍스트 관련
    'PrinterContext',
    'detect_printer_context',
    'SlicerType',
    'EquipmentType',
    'FirmwareType',
    # 하위 호환
    'run_basic_checks',
    'extract_data_for_llm',
    'run_all_rules',
    'RuleResult',
    'get_triggered_anomalies',
    'get_llm_review_needed',
    'get_rule_summary',
]
