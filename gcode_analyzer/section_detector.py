"""
G-code 구간 분류기
START_GCODE / BODY / END_GCODE 구간을 자동 감지

[B1] 강화된 섹션 감지:
- END 마커 정확도 향상
- 마지막 레이어 추적
- 다양한 슬라이서 포맷 지원
"""
from typing import List, Tuple
from enum import Enum
import re
from .models import GCodeLine

class GCodeSection(str, Enum):
    START = "START_GCODE"   # 시작 G-code (예열, 홈, 프라임 등)
    BODY = "BODY"           # 실제 프린팅 (레이어 0 ~ N)
    END = "END_GCODE"       # 종료 G-code (온도 끄기, 모터 비활성화 등)

class SectionBoundaries:
    """G-code 구간 경계선"""
    def __init__(
        self,
        start_end: int,      # START 끝나는 라인 (1-based)
        body_end: int,       # BODY 끝나는 라인 (1-based)
        total_lines: int,
        last_layer: int = 0,           # 마지막 레이어 번호
        last_layer_line: int = 0,      # 마지막 레이어 시작 라인
        last_extrusion_line: int = 0   # 마지막 익스트루전 라인
    ):
        self.start_end = start_end
        self.body_end = body_end
        self.total_lines = total_lines
        self.last_layer = last_layer
        self.last_layer_line = last_layer_line
        self.last_extrusion_line = last_extrusion_line

    def get_section(self, line_index: int) -> GCodeSection:
        """라인 번호로 구간 반환"""
        if line_index <= self.start_end:
            return GCodeSection.START
        elif line_index <= self.body_end:
            return GCodeSection.BODY
        else:
            return GCodeSection.END

    def is_near_end(self, line_index: int, threshold: int = 50) -> bool:
        """END 구간 근처인지 확인 (오탐 방지용)"""
        return line_index > self.body_end - threshold

    def __repr__(self):
        return (f"SectionBoundaries(START: 1-{self.start_end}, "
                f"BODY: {self.start_end+1}-{self.body_end}, "
                f"END: {self.body_end+1}-{self.total_lines}, "
                f"last_layer={self.last_layer})")


def _find_last_layer_info(lines: List[GCodeLine]) -> Tuple[int, int, int]:
    """
    마지막 레이어 정보 찾기

    Returns:
        (last_layer_num, last_layer_line, last_extrusion_line)
    """
    last_layer_num = 0
    last_layer_line = 0
    last_extrusion_line = 0

    # 레이어 패턴들 (다양한 슬라이서 지원)
    # Cura: ;LAYER:123
    # PrusaSlicer: ;LAYER_CHANGE, ; Z = 12.34
    # BambuStudio/OrcaSlicer: ; CHANGE_LAYER, ;LAYER:123
    layer_patterns = [
        re.compile(r';LAYER[:\s]*(\d+)', re.IGNORECASE),
        re.compile(r';\s*LAYER_CHANGE', re.IGNORECASE),
        re.compile(r';\s*CHANGE_LAYER', re.IGNORECASE),
    ]

    for i, line in enumerate(lines):
        # 레이어 번호 추출
        if line.comment:
            for pattern in layer_patterns:
                match = pattern.search(f";{line.comment}")
                if match:
                    if match.groups():
                        try:
                            layer_num = int(match.group(1))
                            if layer_num > last_layer_num:
                                last_layer_num = layer_num
                                last_layer_line = i
                        except ValueError:
                            pass
                    break

        # 마지막 익스트루전 라인 추적
        if line.cmd in ["G0", "G1"] and "E" in line.params:
            e_val = line.params.get("E", 0)
            if e_val > 0:  # 양의 익스트루전만
                last_extrusion_line = i

    return last_layer_num, last_layer_line, last_extrusion_line


def detect_sections(lines: List[GCodeLine]) -> SectionBoundaries:
    """
    G-code에서 구간 경계를 자동 감지 (강화된 버전)

    감지 기준:
    - START 끝: 첫 번째 ;LAYER:0 또는 ;TYPE: 주석 발견
    - BODY 끝: END 마커 또는 마지막 레이어 이후 온도 끄기 명령

    [B1] 강화된 END 감지:
    1. 명시적 END 코멘트 (;END, ;END_GCODE, ; end gcode 등)
    2. 마지막 레이어 이후 M104 S0 / M140 S0
    3. 마지막 익스트루전 이후 온도 끄기 명령
    4. G28 / M84 종료 명령
    """
    total_lines = len(lines)
    if total_lines == 0:
        return SectionBoundaries(0, 0, 0)

    # 기본값: 전체가 BODY
    start_end = 0
    body_end = total_lines

    # 마지막 레이어 정보 먼저 수집
    last_layer_num, last_layer_line, last_extrusion_line = _find_last_layer_info(lines)

    # ============================================================
    # START 끝 감지: 첫 번째 레이어 시작점
    # ============================================================
    # 1단계: 명시적 START_GCODE 종료 마커 찾기 (가장 정확)
    start_end_markers = [
        "MACHINE_START_GCODE_END",  # Bambu/Orca
        "START_GCODE_END",
        "start printing object",     # Bambu/Orca - 실제 출력 시작
        "LAYER:0",                   # 레이어 0 시작
    ]
    for i, line in enumerate(lines):
        if line.comment:
            comment_upper = line.comment.upper()
            for marker in start_end_markers:
                if marker.upper() in comment_upper:
                    start_end = i  # 이 라인 직전까지 START
                    break
            if start_end > 0:
                break

    # 2단계: 명시적 마커가 없으면 레이어/타입 마커로 fallback
    # 주의: "; FEATURE:" 는 START_GCODE 내부에서도 나올 수 있으므로
    #       MACHINE_START_GCODE_END 이후에만 의미있음
    if start_end == 0:
        fallback_markers = [
            ";LAYER_CHANGE", ";TYPE:", "; CHANGE_LAYER", ";Z:"
        ]
        for i, line in enumerate(lines):
            if line.comment:
                comment_check = f";{line.comment}".upper()
                for marker in fallback_markers:
                    if marker.upper() in comment_check:
                        start_end = i  # 이 라인 직전까지 START
                        break
                if start_end > 0:
                    break

    # 만약 레이어 마커가 없으면, 첫 번째 Z 이동을 START 끝으로
    if start_end == 0:
        for i, line in enumerate(lines[:min(500, total_lines)]):
            if line.cmd in ["G0", "G1"] and "Z" in line.params:
                z_val = line.params.get("Z", 0)
                if 0 < z_val < 1:  # 첫 레이어 높이 (0.1~0.3mm 정도)
                    start_end = i
                    break

    # 아직도 못 찾았으면 처음 100줄을 START로
    if start_end == 0:
        start_end = min(100, total_lines)

    # ============================================================
    # END 시작 감지 (강화된 버전)
    # ============================================================

    # END 마커 패턴들 (다양한 슬라이서 지원)
    # 주의: "hotend", "frontend" 등과 구분하기 위해 정확한 매칭 필요
    end_markers_exact = [
        # 명시적 END 마커 (정확히 매칭해야 함)
        "END_GCODE", "END GCODE", "END_GCODE_BEGIN", "End of Gcode",
        # Bambu/Orca
        "EXECUTABLE_BLOCK_END", "filament end gcode",
        # PrusaSlicer
        "Filament-specific end G-code",
    ]
    # 단독 "END"는 단어 경계로 체크 (hotend와 구분)
    end_pattern = re.compile(r'\bEND\b(?!_GCODE)', re.IGNORECASE)

    end_found = False
    search_start = max(0, total_lines - 500)

    # 1. 마지막 익스트루전 이후 온도 끄기 명령 찾기 (가장 정확한 기준)
    # 출력 완료 후 온도를 끄는 시점이 END의 시작
    if last_extrusion_line > 0:
        for i in range(last_extrusion_line + 1, total_lines):
            line = lines[i]
            # 온도 0으로 설정 = END 시작
            if line.cmd in ["M104", "M140"] and line.params.get("S") == 0:
                body_end = i
                end_found = True
                break
            # M109 S0 / M190 S0 도 END 시작
            if line.cmd in ["M109", "M190"] and line.params.get("S") == 0:
                body_end = i
                end_found = True
                break

    # 2. 명시적 END 코멘트 찾기 (fallback)
    if not end_found:
        for i in range(search_start, total_lines):
            line = lines[i]
            if line.comment:
                comment_text = line.comment
                comment_upper = comment_text.upper()

                # 정확한 마커 매칭 (대소문자 무시)
                marker_matched = False
                for marker in end_markers_exact:
                    if marker.upper() in comment_upper:
                        body_end = i
                        end_found = True
                        marker_matched = True
                        break

                # 단독 "END" 단어 매칭 (hotend, frontend 등 제외)
                if not marker_matched and end_pattern.search(comment_text):
                    body_end = i
                    end_found = True

                if end_found:
                    break

    # 3. 뒤에서부터 M104 S0 / M140 S0 찾기
    if not end_found:
        for i in range(total_lines - 1, search_start, -1):
            line = lines[i]
            if line.cmd in ["M104", "M140", "M109", "M190"]:
                if line.params.get("S") == 0:
                    # 이 명령 이전의 마지막 익스트루전을 BODY 끝으로
                    for j in range(i - 1, search_start, -1):
                        prev_line = lines[j]
                        if prev_line.cmd in ["G0", "G1"] and "E" in prev_line.params:
                            body_end = j + 1
                            end_found = True
                            break
                    if not end_found:
                        body_end = i
                        end_found = True
                    break

    # 4. G28 (홈으로) 또는 M84 (모터 끄기) 찾기
    if not end_found:
        for i in range(total_lines - 1, search_start, -1):
            line = lines[i]
            if line.cmd in ["G28", "M84"]:
                # 이 명령 이전의 마지막 익스트루전 찾기
                for j in range(i, search_start, -1):
                    prev_line = lines[j]
                    if prev_line.cmd in ["G0", "G1"] and "E" in prev_line.params:
                        body_end = j + 1
                        end_found = True
                        break
                break

    # 5. Fallback: 마지막 익스트루전 라인 + 여유분
    if not end_found and last_extrusion_line > 0:
        # 마지막 익스트루전 이후 50줄을 END로
        body_end = min(last_extrusion_line + 50, total_lines - 10)
        end_found = True

    # 6. 최종 Fallback: 끝에서 50줄은 END로
    if not end_found:
        min_end_size = min(50, max(total_lines // 20, 10))
        body_end = total_lines - min_end_size

    # body_end가 start_end보다 작으면 안됨
    if body_end <= start_end:
        body_end = total_lines - min(50, total_lines // 10)

    # body_end가 total_lines보다 크면 안됨
    if body_end >= total_lines:
        body_end = total_lines - 1

    return SectionBoundaries(
        start_end=start_end,
        body_end=body_end,
        total_lines=total_lines,
        last_layer=last_layer_num,
        last_layer_line=last_layer_line,
        last_extrusion_line=last_extrusion_line
    )


def get_section_for_event(
    line_index: int,
    boundaries: SectionBoundaries
) -> Tuple[GCodeSection, dict]:
    """
    이벤트 라인의 구간과 추가 정보 반환
    """
    section = boundaries.get_section(line_index)

    # 구간 내 위치 정보
    if section == GCodeSection.START:
        position_in_section = line_index
        section_size = boundaries.start_end
    elif section == GCodeSection.BODY:
        position_in_section = line_index - boundaries.start_end
        section_size = boundaries.body_end - boundaries.start_end
    else:
        position_in_section = line_index - boundaries.body_end
        section_size = boundaries.total_lines - boundaries.body_end

    progress = position_in_section / section_size if section_size > 0 else 0

    return section, {
        "section": section.value,
        "position_in_section": position_in_section,
        "section_size": section_size,
        "progress_in_section": round(progress, 3),
        "total_lines": boundaries.total_lines,
        "last_layer": boundaries.last_layer,
        "is_near_end": boundaries.is_near_end(line_index)
    }


def is_end_gcode_pattern(line: GCodeLine, boundaries: SectionBoundaries) -> bool:
    """
    END G-code 패턴인지 확인 (오탐 방지용)

    END 구간에서 정상적으로 나타나는 패턴:
    - M104 S0 / M140 S0 (온도 끄기)
    - M107 (팬 끄기)
    - G28 (홈으로)
    - M84 (모터 끄기)
    """
    section = boundaries.get_section(line.index)

    if section == GCodeSection.END:
        return True

    # BODY 끝부분에서 종료 패턴 감지
    if boundaries.is_near_end(line.index, threshold=30):
        # 온도 0으로 설정
        if line.cmd in ["M104", "M140", "M109", "M190"]:
            if line.params.get("S") == 0:
                return True
        # 모터/팬 끄기
        if line.cmd in ["M84", "M107"]:
            return True
        # 홈으로
        if line.cmd == "G28":
            return True

    return False
