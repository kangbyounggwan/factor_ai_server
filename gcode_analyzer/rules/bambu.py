"""
Bambu Lab 특화 룰 엔진

Bambu Lab 특성:
1. M104/M109에 H 파라미터 사용 (H1 = 멀티 노즐)
2. G9111 온도 명령어 (bedTemp=, extruderTemp=)
3. BambuStudio 슬라이서 전용 주석/마커
4. M73 L 레이어 진행률 명령
5. 독자적 AMS(자동 필라멘트 시스템) 명령어

분석 시 주의:
- M104 S0 H1 은 보조 노즐 끄기 (에러 아님)
- G9111 bedTemp=60 extruderTemp=210 형태의 온도 설정
- BODY에서 H 파라미터 있는 온도 0 설정은 정상
"""
from typing import List, Dict, Any, Optional
import re

from .base import BaseRuleEngine, BasicCheckResult, ExtractedData
from ..models import GCodeLine, TempEvent
from ..section_detector import SectionBoundaries, GCodeSection, get_section_for_event


class BambuRuleEngine(BaseRuleEngine):
    """
    Bambu Lab 특화 룰 엔진

    H 파라미터, G9111 명령어 등 Bambu 전용 문법 인식
    """

    ENGINE_TYPE = "bambu"

    def __init__(self, equipment_model: Optional[str] = None):
        """
        Args:
            equipment_model: 프린터 모델 (X1, P1, A1 등)
        """
        super().__init__()
        self.equipment_model = equipment_model

    def _is_x1_series(self) -> bool:
        """X1 시리즈인지 (멀티 노즐 지원)"""
        if self.equipment_model:
            return 'X1' in self.equipment_model.upper()
        return False

    # ============================================================
    # Bambu 특화 체크 오버라이드
    # ============================================================
    def _check_nozzle_temp_exists(
        self,
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries,
        lines: List[GCodeLine] = None
    ) -> BasicCheckResult:
        """
        노즐 온도 설정 존재 여부 - Bambu 버전

        G9111 extruderTemp= 형태도 인식
        """
        # 표준 온도 이벤트
        nozzle_temps = [e for e in temp_events if e.cmd in ["M104", "M109"] and e.temp > 0]

        if nozzle_temps:
            return BasicCheckResult(
                check_name="nozzle_temp_exists",
                passed=True,
                message="노즐 온도 정상 설정",
                details={
                    "count": len(nozzle_temps),
                    "first_temp": nozzle_temps[0].temp,
                    "source": "standard"
                }
            )

        # G9111에서 온도 확인 (Bambu Lab 전용)
        if lines:
            g9111_temps = self._extract_g9111_temps(lines)
            if g9111_temps.get("extruder"):
                return BasicCheckResult(
                    check_name="nozzle_temp_exists",
                    passed=True,
                    message="노즐 온도 정상 설정 (G9111)",
                    details={
                        "temp": g9111_temps["extruder"],
                        "source": "G9111"
                    }
                )

        return BasicCheckResult(
            check_name="nozzle_temp_exists",
            passed=False,
            message="노즐 온도 설정 없음",
            details={"count": 0}
        )

    def _run_basic_checks(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> List["BasicCheckResult"]:
        """기본 체크 실행 - Bambu 버전 (G9111 지원)"""
        return [
            self._check_nozzle_temp_exists(temp_events, boundaries, lines),
            self._check_bed_temp_exists(temp_events, boundaries, lines),
            self._check_temp_wait_before_extrusion(lines, temp_events, boundaries),
            self._check_feed_rate_exists(lines),
        ]

    def _check_bed_temp_exists(
        self,
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries,
        lines: List[GCodeLine] = None
    ) -> BasicCheckResult:
        """베드 온도 설정 존재 여부 - Bambu 버전"""
        # 표준 온도 이벤트
        bed_temps = [e for e in temp_events if e.cmd in ["M140", "M190"] and e.temp > 0]

        if bed_temps:
            return BasicCheckResult(
                check_name="bed_temp_exists",
                passed=True,
                message="베드 온도 정상 설정",
                details={
                    "count": len(bed_temps),
                    "first_temp": bed_temps[0].temp,
                    "source": "standard"
                }
            )

        # G9111에서 베드 온도 확인
        if lines:
            g9111_temps = self._extract_g9111_temps(lines)
            if g9111_temps.get("bed"):
                return BasicCheckResult(
                    check_name="bed_temp_exists",
                    passed=True,
                    message="베드 온도 정상 설정 (G9111)",
                    details={
                        "temp": g9111_temps["bed"],
                        "source": "G9111"
                    }
                )

        return BasicCheckResult(
            check_name="bed_temp_exists",
            passed=False,
            message="베드 온도 설정 없음",
            details={"count": 0}
        )

    def _check_temp_wait_before_extrusion(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> BasicCheckResult:
        """압출 전 온도 대기 여부 - Bambu 버전"""
        # G9111이 있으면 프린터가 자동으로 온도 대기 처리
        g9111_temps = self._extract_g9111_temps(lines)
        if g9111_temps.get("extruder"):
            return BasicCheckResult(
                check_name="temp_wait_before_extrusion",
                passed=True,
                message="온도 대기 처리 (G9111 - 프린터 자동 처리)",
                details={
                    "source": "G9111",
                    "extruder_temp": g9111_temps.get("extruder")
                }
            )

        # 표준 체크 실행
        return super()._check_temp_wait_before_extrusion(lines, temp_events, boundaries)

    def _extract_data(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> ExtractedData:
        """데이터 추출 - Bambu 특화 정보 포함"""
        data = super()._extract_data(lines, temp_events, boundaries)

        # Bambu 컨텍스트 추가
        data.printer_context = {
            "equipment": "bambulab",
            "model": self.equipment_model,
            "is_x1_series": self._is_x1_series(),
            "has_ams": self._detect_ams_usage(lines)
        }

        # G9111 온도 명령 감지
        g9111_temps = self._extract_g9111_temps(lines)
        if g9111_temps:
            data.printer_context["g9111_temps"] = g9111_temps
            if g9111_temps.get("extruder"):
                data.has_nozzle_temp = True
            if g9111_temps.get("bed"):
                data.has_bed_temp = True

        return data

    def _extract_g9111_temps(self, lines: List[GCodeLine]) -> Dict[str, float]:
        """G9111 명령어에서 온도 추출"""
        temps = {}
        for line in lines:
            if line.cmd == "G9111":
                raw = line.raw or ""
                bed_match = re.search(r'bedTemp\s*=\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
                ext_match = re.search(r'extruderTemp\s*=\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
                if bed_match:
                    temps["bed"] = float(bed_match.group(1))
                if ext_match:
                    temps["extruder"] = float(ext_match.group(1))
                if temps:
                    break
        return temps

    def _detect_ams_usage(self, lines: List[GCodeLine]) -> bool:
        """AMS 사용 여부 감지"""
        for line in lines[:500]:  # 앞부분만 확인
            raw = line.raw or ""
            if 'AMS' in raw.upper() or 'T' in (line.cmd or '') and line.cmd in ['T0', 'T1', 'T2', 'T3']:
                return True
        return False

    # ============================================================
    # Bambu 특화 치명적 플래그
    # ============================================================
    def _detect_critical_flags(
        self,
        lines: List[GCodeLine],
        temp_events: List[TempEvent],
        boundaries: SectionBoundaries
    ) -> List[str]:
        """
        치명적 플래그 감지 - Bambu 버전

        H 파라미터가 있는 온도 0 설정은 정상 (보조 노즐 끄기)
        """
        flags = []

        # BODY에서 노즐 온도 0 설정 체크 (H 파라미터 있으면 제외)
        for event in temp_events:
            if event.cmd in ["M104", "M109"] and event.temp == 0:
                section, _ = get_section_for_event(event.line_index, boundaries)
                if section == GCodeSection.BODY:
                    # 원본 라인에서 H 파라미터 확인
                    for line in lines:
                        if line.index == event.line_index:
                            # H 파라미터 있으면 보조 노즐 끄기 - 정상
                            if "H" not in line.raw.upper():
                                flags.append(f"BODY_TEMP_ZERO:line_{event.line_index}")
                            # H 파라미터 있으면 무시 (정상적인 멀티 노즐 동작)
                            break

        # 콜드 익스트루전 체크
        current_temp = 0.0
        g9111_temps = self._extract_g9111_temps(lines)
        if g9111_temps.get("extruder"):
            current_temp = g9111_temps["extruder"]

        for line in lines:
            if line.cmd in ["M104", "M109"] and "S" in line.params:
                # H 파라미터 없는 경우만 메인 노즐 온도로 간주
                if "H" not in line.raw.upper():
                    current_temp = line.params["S"]

            if line.cmd == "G1" and "E" in line.params:
                e_val = line.params.get("E", 0)
                section, _ = get_section_for_event(line.index, boundaries)
                if section == GCodeSection.BODY and e_val > 0 and current_temp == 0:
                    flags.append(f"COLD_EXTRUSION_ZERO:line_{line.index}")
                    break

        return flags
