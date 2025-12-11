"""
G-code 구간 분류기
START_GCODE / BODY / END_GCODE 구간을 자동 감지
"""
from typing import List, Tuple
from enum import Enum
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
        total_lines: int
    ):
        self.start_end = start_end
        self.body_end = body_end
        self.total_lines = total_lines
    
    def get_section(self, line_index: int) -> GCodeSection:
        """라인 번호로 구간 반환"""
        if line_index <= self.start_end:
            return GCodeSection.START
        elif line_index <= self.body_end:
            return GCodeSection.BODY
        else:
            return GCodeSection.END
    
    def __repr__(self):
        return f"SectionBoundaries(START: 1-{self.start_end}, BODY: {self.start_end+1}-{self.body_end}, END: {self.body_end+1}-{self.total_lines})"

def detect_sections(lines: List[GCodeLine]) -> SectionBoundaries:
    """
    G-code에서 구간 경계를 자동 감지
    
    감지 기준:
    - START 끝: 첫 번째 ;LAYER:0 또는 ;TYPE: 주석 발견
    - BODY 끝: 마지막 레이어 이후, M84/M106 S0/G28 등 종료 명령 시작점
    """
    total_lines = len(lines)
    if total_lines == 0:
        return SectionBoundaries(0, 0, 0)
    
    # 기본값: 전체가 BODY
    start_end = 0
    body_end = total_lines
    
    # START 끝 감지: 첫 번째 레이어 시작점
    first_layer_markers = [";LAYER:0", ";LAYER_CHANGE", ";TYPE:"]
    for i, line in enumerate(lines):
        if line.comment:
            for marker in first_layer_markers:
                if marker in line.comment.upper() or marker in f";{line.comment}".upper():
                    start_end = i  # 이 라인 직전까지 START
                    break
            if start_end > 0:
                break
    
    # 만약 레이어 마커가 없으면, 첫 번째 Z 이동을 START 끝으로
    if start_end == 0:
        for i, line in enumerate(lines[:min(500, total_lines)]):
            if line.cmd in ["G0", "G1"] and "Z" in line.params:
                if line.params.get("Z", 0) > 0 and line.params.get("Z", 0) < 1:
                    start_end = i
                    break
    
    # 아직도 못 찾았으면 처음 100줄을 START로
    if start_end == 0:
        start_end = min(100, total_lines)
    
    # END 시작 감지: 뒤에서부터 탐색
    end_markers_comment = [";END", "END GCODE", "; END", ";Time elapsed", "END_GCODE"]
    end_found = False

    # 1. 먼저 종료 코멘트 찾기 (가장 확실한 기준) - 앞에서부터 탐색
    search_start = max(0, total_lines - 500)
    for i in range(search_start, total_lines):
        line = lines[i]
        if line.comment:
            for marker in end_markers_comment:
                if marker.upper() in line.comment.upper():
                    body_end = i
                    end_found = True
                    break
            if end_found:
                break

    # 2. 종료 코멘트 없으면, M104 S0 / M140 S0 찾기 (뒤에서부터)
    if not end_found:
        for i in range(total_lines - 1, search_start, -1):
            line = lines[i]
            if line.cmd in ["M104", "M140"] and line.params.get("S") == 0:
                body_end = i
                end_found = True
                break

    # 3. 그래도 못 찾으면, G28 (홈으로) 또는 M84 (모터 끄기) 찾기
    if not end_found:
        for i in range(total_lines - 1, search_start, -1):
            line = lines[i]
            if line.cmd in ["G28", "M84"]:
                # 이 명령이 있는 곳부터 END 시작점 앞으로 찾기
                for j in range(i, search_start, -1):
                    prev_line = lines[j]
                    # 마지막 압출(E 파라미터) 라인 = BODY 끝
                    if prev_line.cmd in ["G0", "G1"] and "E" in prev_line.params:
                        body_end = j + 1
                        end_found = True
                        break
                break

    # 4. 최소한 끝에서 50줄은 END로 보장 (fallback)
    min_end_size = min(50, max(total_lines // 20, 10))  # 최소 50줄 또는 전체의 5%
    if body_end > total_lines - min_end_size:
        body_end = total_lines - min_end_size

    # body_end가 start_end보다 작으면 안됨
    if body_end <= start_end:
        body_end = total_lines - min(50, total_lines // 10)
    
    return SectionBoundaries(start_end, body_end, total_lines)

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
        "total_lines": boundaries.total_lines
    }
