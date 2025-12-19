"""
G-code 분석 룰 엔진 모듈

구조:
- base.py: 기본 룰 엔진 (표준 G-code만 분석)
- klipper.py: Klipper 펌웨어 특화 룰
- bambu.py: Bambu Lab 특화 룰 (H 코드 등)
- factory.py: 컨텍스트 기반 룰 엔진 선택

사용법:
    from gcode_analyzer.rules import get_rule_engine

    engine = get_rule_engine(printer_context)
    result = engine.run_checks(lines, temp_events, boundaries)
"""

from .base import BaseRuleEngine, BasicCheckResult, ExtractedData, RuleEngineOutput
from .klipper import KlipperRuleEngine
from .bambu import BambuRuleEngine
from .factory import get_rule_engine, RuleEngineFactory
from .temp_scanner import scan_temperature_anomalies

__all__ = [
    'BaseRuleEngine',
    'KlipperRuleEngine',
    'BambuRuleEngine',
    'get_rule_engine',
    'RuleEngineFactory',
    'BasicCheckResult',
    'ExtractedData',
    'RuleEngineOutput',
    'scan_temperature_anomalies',
]
