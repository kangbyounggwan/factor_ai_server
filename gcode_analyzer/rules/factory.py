"""
룰 엔진 팩토리 - 컨텍스트 기반으로 적절한 룰 엔진 선택

분석 흐름:
1. PrinterContext 감지 (슬라이서/설비/펌웨어)
2. 컨텍스트에 맞는 룰 엔진 선택
3. 룰 엔진으로 기본 체크 실행
4. LLM 분석 (issue_detector)
5. 최종 결과 취합

사용법:
    from gcode_analyzer.rules import get_rule_engine
    from gcode_analyzer.segment_extractor import detect_printer_context

    # 컨텍스트 감지
    context = detect_printer_context(lines)

    # 룰 엔진 선택 및 실행
    engine = get_rule_engine(context)
    result = engine.run_checks(lines, temp_events, boundaries)
"""
from typing import List, Optional

from .base import BaseRuleEngine, RuleEngineOutput
from .klipper import KlipperRuleEngine
from .bambu import BambuRuleEngine

from ..segment_extractor import (
    PrinterContext,
    SlicerType, EquipmentType, FirmwareType
)
from ..models import GCodeLine, TempEvent
from ..section_detector import SectionBoundaries


class RuleEngineFactory:
    """
    컨텍스트 기반 룰 엔진 팩토리

    우선순위:
    1. 펌웨어 타입 (Klipper > Marlin)
    2. 설비 타입 (BambuLab 등)
    3. 슬라이서 타입 (필요시)
    4. 기본 룰 엔진
    """

    @staticmethod
    def create(context: PrinterContext) -> BaseRuleEngine:
        """
        PrinterContext를 기반으로 적절한 룰 엔진 생성

        Args:
            context: 감지된 프린터 컨텍스트

        Returns:
            BaseRuleEngine: 적절한 룰 엔진 인스턴스

        우선순위:
        1. Bambu Lab 설비 (G9111, H 파라미터 등 고유 명령어 사용)
        2. Klipper 펌웨어 (START_PRINT 매크로 등)
        3. BambuStudio 슬라이서
        4. 기본 룰 엔진
        """
        # 1. Bambu Lab 설비 → BambuRuleEngine (최우선)
        #    Bambu Lab은 SET_VELOCITY_LIMIT 등 Klipper 스타일 명령어를 사용하지만
        #    실제 Klipper가 아니므로 설비 감지가 우선
        if context.equipment_type == EquipmentType.BAMBULAB:
            return BambuRuleEngine(
                equipment_model=context.equipment_model
            )

        # 2. Klipper 펌웨어 → KlipperRuleEngine
        if context.firmware_type == FirmwareType.KLIPPER:
            return KlipperRuleEngine(
                klipper_metadata=context.firmware_metadata
            )

        # 3. BambuStudio 슬라이서 → BambuRuleEngine
        if context.slicer_type == SlicerType.BAMBUSTUDIO:
            return BambuRuleEngine(
                equipment_model=context.equipment_model
            )

        # 4. 기본 룰 엔진
        return BaseRuleEngine()

    @staticmethod
    def get_engine_type(context: PrinterContext) -> str:
        """컨텍스트에 해당하는 엔진 타입 반환 (디버깅용)"""
        if context.equipment_type == EquipmentType.BAMBULAB:
            return "bambu"
        if context.firmware_type == FirmwareType.KLIPPER:
            return "klipper"
        if context.slicer_type == SlicerType.BAMBUSTUDIO:
            return "bambu"
        return "base"


def get_rule_engine(context: PrinterContext) -> BaseRuleEngine:
    """
    컨텍스트 기반으로 적절한 룰 엔진 반환

    편의 함수 - RuleEngineFactory.create()의 단축 버전

    Args:
        context: 감지된 프린터 컨텍스트

    Returns:
        BaseRuleEngine: 적절한 룰 엔진 인스턴스

    사용 예:
        context = detect_printer_context(lines)
        engine = get_rule_engine(context)
        result = engine.run_checks(lines, temp_events, boundaries)
    """
    return RuleEngineFactory.create(context)


def run_analysis_with_context(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    boundaries: SectionBoundaries,
    context: Optional[PrinterContext] = None
) -> RuleEngineOutput:
    """
    컨텍스트 기반 전체 분석 실행

    컨텍스트가 없으면 자동 감지

    Args:
        lines: 파싱된 G-code 라인들
        temp_events: 온도 이벤트들
        boundaries: 섹션 경계
        context: 프린터 컨텍스트 (없으면 자동 감지)

    Returns:
        RuleEngineOutput: 분석 결과
    """
    from ..segment_extractor import detect_printer_context

    # 컨텍스트 자동 감지
    if context is None:
        context = detect_printer_context(lines)

    # 적절한 룰 엔진 선택
    engine = get_rule_engine(context)

    # 체크 실행
    result = engine.run_checks(lines, temp_events, boundaries)

    # 컨텍스트 정보 추가
    result.extracted_data.printer_context = context.to_dict()

    return result
