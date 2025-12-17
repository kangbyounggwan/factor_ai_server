"""
Klipper 펌웨어 특화 룰 엔진

Klipper 특성:
1. START_PRINT/PRINT_START 매크로로 온도 설정 (M104/M109 없을 수 있음)
2. END_PRINT/PRINT_END 매크로로 종료 처리
3. SET_PRESSURE_ADVANCE, SET_VELOCITY_LIMIT 등 Klipper 전용 명령어
4. 매크로 내부에서 온도/팬 등 처리하므로 G-code에 직접 없을 수 있음

분석 시 주의:
- M104/M109 없어도 START_PRINT EXTRUDER=210 형태면 정상
- M140/M190 없어도 START_PRINT BED=60 형태면 정상
- 온도 명령 부재를 false positive로 판단하지 않음
"""
from typing import List, Dict, Any, Optional
import re

from .base import BaseRuleEngine, BasicCheckResult, ExtractedData, RuleEngineOutput
from ..models import GCodeLine, TempEvent
from ..section_detector import SectionBoundaries, GCodeSection, get_section_for_event


class KlipperRuleEngine(BaseRuleEngine):
    """
    Klipper 펌웨어 특화 룰 엔진

    매크로 기반 온도 설정을 인식하여 false positive 방지
    """

    ENGINE_TYPE = "klipper"

    def __init__(self, klipper_metadata: Optional[Dict[str, Any]] = None):
        """
        Args:
            klipper_metadata: FirmwareDetector에서 추출한 Klipper 메타데이터
                - extruder_temp: START_PRINT에서 설정된 노즐 온도
                - bed_temp: START_PRINT에서 설정된 베드 온도
                - start_macro: 감지된 시작 매크로 라인
                - detected_macros: 감지된 매크로 목록
        """
        super().__init__()
        self.klipper_metadata = klipper_metadata or {}

    def _get_macro_extruder_temp(self) -> Optional[float]:
        """START_PRINT 매크로에서 설정된 노즐 온도"""
        return self.klipper_metadata.get('extruder_temp')

    def _get_macro_bed_temp(self) -> Optional[float]:
        """START_PRINT 매크로에서 설정된 베드 온도"""
        return self.klipper_metadata.get('bed_temp')

    def _has_start_macro(self) -> bool:
        """시작 매크로가 감지되었는지"""
        return 'start_macro' in self.klipper_metadata

    # ============================================================
    # Klipper 특화 체크 오버라이드
    # ============================================================
    def _check_nozzle_temp_exists(
        self,
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> BasicCheckResult:
        """
        노즐 온도 설정 존재 여부 - Klipper 버전

        Klipper는 START_PRINT EXTRUDER=210 형태로 온도 설정 가능
        매크로에서 온도가 감지되면 M104/M109 없어도 정상
        """
        # 1. 매크로에서 온도 확인
        macro_temp = self._get_macro_extruder_temp()
        if macro_temp and macro_temp > 0:
            return BasicCheckResult(
                check_name="nozzle_temp_exists",
                passed=True,
                message=f"노즐 온도 매크로 설정 (START_PRINT EXTRUDER={macro_temp})",
                details={
                    "source": "klipper_macro",
                    "temp": macro_temp,
                    "macro": self.klipper_metadata.get('start_macro', '')
                }
            )

        # 2. 표준 G-code에서 확인 (기본 로직)
        nozzle_temps = [e for e in temp_events if e.cmd in ["M104", "M109"] and e.temp > 0]

        if nozzle_temps:
            return BasicCheckResult(
                check_name="nozzle_temp_exists",
                passed=True,
                message="노즐 온도 정상 설정 (표준 G-code)",
                details={"count": len(nozzle_temps), "first_temp": nozzle_temps[0].temp}
            )

        # 3. 시작 매크로는 있지만 온도 파라미터 없음 → 매크로 내부 처리로 추정
        if self._has_start_macro():
            return BasicCheckResult(
                check_name="nozzle_temp_exists",
                passed=True,
                message="노즐 온도 매크로 내부 처리 추정 (START_PRINT)",
                details={
                    "source": "klipper_macro_internal",
                    "note": "Klipper 매크로 내부에서 온도 설정 가능",
                    "macro": self.klipper_metadata.get('start_macro', '')
                },
                skipped=False
            )

        # 4. 매크로도 없고 온도 설정도 없음 → 실패
        return BasicCheckResult(
            check_name="nozzle_temp_exists",
            passed=False,
            message="노즐 온도 설정 없음 (Klipper 매크로/표준 G-code 모두 미발견)",
            details={"count": 0}
        )

    def _check_bed_temp_exists(
        self,
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> BasicCheckResult:
        """
        베드 온도 설정 존재 여부 - Klipper 버전

        Klipper는 START_PRINT BED=60 형태로 온도 설정 가능
        """
        # 1. 매크로에서 온도 확인
        macro_temp = self._get_macro_bed_temp()
        if macro_temp and macro_temp > 0:
            return BasicCheckResult(
                check_name="bed_temp_exists",
                passed=True,
                message=f"베드 온도 매크로 설정 (START_PRINT BED={macro_temp})",
                details={
                    "source": "klipper_macro",
                    "temp": macro_temp
                }
            )

        # 2. 표준 G-code에서 확인
        bed_temps = [e for e in temp_events if e.cmd in ["M140", "M190"] and e.temp > 0]

        if bed_temps:
            return BasicCheckResult(
                check_name="bed_temp_exists",
                passed=True,
                message="베드 온도 정상 설정 (표준 G-code)",
                details={"count": len(bed_temps), "first_temp": bed_temps[0].temp}
            )

        # 3. 시작 매크로 있음 → 매크로 내부 처리로 추정
        if self._has_start_macro():
            return BasicCheckResult(
                check_name="bed_temp_exists",
                passed=True,
                message="베드 온도 매크로 내부 처리 추정 (START_PRINT)",
                details={
                    "source": "klipper_macro_internal",
                    "note": "Klipper 매크로 내부에서 온도 설정 가능"
                },
                skipped=False
            )

        # 4. 베드 없는 프린터일 수도 있음 (Delta 등)
        return BasicCheckResult(
            check_name="bed_temp_exists",
            passed=False,
            message="베드 온도 설정 없음 (히팅 베드 없는 프린터일 수 있음)",
            details={"count": 0, "note": "Klipper 환경에서 베드 없이 운용 가능"}
        )

    def _check_temp_wait_before_extrusion(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> BasicCheckResult:
        """
        압출 전 온도 대기 여부 - Klipper 버전

        Klipper START_PRINT 매크로는 내부적으로 온도 대기 처리 가능
        """
        # 시작 매크로가 있으면 매크로 내부에서 대기 처리로 간주
        if self._has_start_macro():
            return BasicCheckResult(
                check_name="temp_wait_before_extrusion",
                passed=True,
                message="온도 대기 매크로 내부 처리 (START_PRINT)",
                details={
                    "source": "klipper_macro",
                    "note": "Klipper 매크로에서 M109/M190 실행"
                }
            )

        # 표준 체크 실행
        return super()._check_temp_wait_before_extrusion(lines, temp_events, boundaries)

    # ============================================================
    # Klipper 특화 데이터 추출
    # ============================================================
    def _extract_data(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> ExtractedData:
        """데이터 추출 - Klipper 메타데이터 포함"""
        data = super()._extract_data(lines, temp_events, boundaries)

        # Klipper 컨텍스트 추가
        data.printer_context = {
            "firmware": "klipper",
            "has_start_macro": self._has_start_macro(),
            "macro_extruder_temp": self._get_macro_extruder_temp(),
            "macro_bed_temp": self._get_macro_bed_temp(),
            "detected_macros": self.klipper_metadata.get('detected_macros', [])
        }

        # Klipper 매크로 온도가 있으면 추가
        if self._get_macro_extruder_temp():
            data.has_nozzle_temp = True
        if self._get_macro_bed_temp():
            data.has_bed_temp = True

        return data

    # ============================================================
    # Klipper 특화 치명적 플래그
    # ============================================================
    def _detect_critical_flags(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> List[str]:
        """
        치명적 플래그 감지 - Klipper 버전

        Klipper 매크로 환경에서는 일부 플래그를 다르게 처리
        """
        flags = []

        # 기본 플래그 감지
        base_flags = super()._detect_critical_flags(lines, temp_events, boundaries)

        # Klipper 매크로가 있으면 특정 플래그 무시
        # (매크로 내부에서 온도 설정/대기 처리)
        if self._has_start_macro():
            # M104 S0 → START_PRINT 순서는 정상적인 Klipper 패턴
            # START_PRINT 직전 온도 0 설정 후 매크로 내부에서 재설정
            ignored_prefixes = ("COLD_EXTRUSION_ZERO", "BODY_TEMP_ZERO")
            flags = [f for f in base_flags if not f.startswith(ignored_prefixes)]
        else:
            flags = base_flags

        return flags
