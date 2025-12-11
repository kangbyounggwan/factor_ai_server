"""
LLM 입력 데이터 준비 로직
G-code 파서 + DB 데이터 + 컨텍스트 조합
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from .models import GCodeLine, GCodeSummary, TempEvent
from .config import AnalysisConfig, FilamentConfig, DEFAULT_FILAMENTS

class SnippetContext(BaseModel):
    """온도 이벤트 주변 스니펫과 컨텍스트"""
    event_line_index: int
    event_cmd: str
    event_temp: float
    snippet_start: int
    snippet_end: int
    snippet_text: str
    lines_after_event: int  # 이벤트 이후 남은 라인 수

class LLMAnalysisInput(BaseModel):
    """LLM에 전달할 전체 입력 데이터"""
    # G-code 요약 정보 (기본)
    summary: Dict[str, Any]

    # 종합 요약 정보 (상세 - 온도/속도/서포트/시간 등)
    comprehensive_summary: Optional[Dict[str, Any]] = None

    # 분석할 스니펫 컨텍스트
    snippet_context: SnippetContext

    # 필라멘트 정보 (DB 또는 G-code에서 추출)
    filament_info: Optional[Dict[str, Any]] = None

    # 프린터 정보 (DB에서 가져올 수 있음)
    printer_info: Optional[Dict[str, Any]] = None

def extract_temp_event_snippets(
    lines: List[GCodeLine],
    temp_events: List[TempEvent],
    config: AnalysisConfig
) -> List[SnippetContext]:
    """
    각 온도 이벤트 주변의 스니펫을 추출
    """
    snippets = []
    total_lines = len(lines)
    
    for event in temp_events:
        idx_0 = event.line_index - 1  # 0-based index
        window = config.snippet_window
        
        start_0 = max(0, idx_0 - window)
        end_0 = min(total_lines, idx_0 + window + 1)
        
        # 스니펫 텍스트 생성
        snippet_lines = lines[start_0:end_0]
        snippet_text = "\n".join([
            f"{line.index}: {line.raw.strip()}" 
            for line in snippet_lines
        ])
        
        # 이벤트 이후 남은 라인 수
        lines_after = total_lines - event.line_index
        
        snippets.append(SnippetContext(
            event_line_index=event.line_index,
            event_cmd=event.cmd,
            event_temp=event.temp,
            snippet_start=start_0 + 1,  # 1-based
            snippet_end=end_0,
            snippet_text=snippet_text,
            lines_after_event=lines_after
        ))
    
    return snippets

def detect_filament_from_gcode(lines: List[GCodeLine]) -> Optional[str]:
    """
    G-code 주석에서 필라멘트 타입 추출
    슬라이서마다 다른 형식을 처리
    """
    for line in lines[:500]:  # 앞부분에서만 검색
        if line.comment:
            comment = line.comment.upper()
            # Cura, Prusa, etc. 다양한 형식 처리
            if "FILAMENT_TYPE" in comment or "FILAMENT TYPE" in comment:
                for ftype in ["PLA", "ABS", "PETG", "TPU", "NYLON", "ASA"]:
                    if ftype in comment:
                        return ftype
            # 간단한 패턴
            for ftype in ["PLA", "ABS", "PETG", "TPU"]:
                if f"; {ftype}" in line.comment.upper() or f";{ftype}" in line.comment.upper():
                    return ftype
    return None

def prepare_llm_input(
    lines: List[GCodeLine],
    summary: GCodeSummary,
    snippet_context: SnippetContext,
    filament_type: Optional[str] = None,
    printer_name: Optional[str] = None,
    db_printer_info: Optional[Dict] = None
) -> LLMAnalysisInput:
    """
    LLM 분석을 위한 입력 데이터 조합
    
    Args:
        lines: 파싱된 G-code 라인
        summary: G-code 요약 정보
        snippet_context: 분석할 스니펫
        filament_type: 필라멘트 타입 (None이면 자동 감지)
        printer_name: 프린터 이름 (DB 조회용)
        db_printer_info: DB에서 가져온 프린터 정보
    """
    # 필라멘트 정보 결정
    if filament_type is None:
        filament_type = detect_filament_from_gcode(lines)
    
    filament_info = None
    if filament_type and filament_type in DEFAULT_FILAMENTS:
        filament_info = DEFAULT_FILAMENTS[filament_type].dict()
    
    return LLMAnalysisInput(
        summary=summary.dict(),
        snippet_context=snippet_context,
        filament_info=filament_info,
        printer_info=db_printer_info
    )

def filter_significant_temp_events(temp_events: List[TempEvent]) -> List[TempEvent]:
    """
    분석이 필요한 중요 온도 이벤트만 필터링
    - 온도가 0으로 설정된 경우
    - 온도가 급격히 변한 경우
    """
    significant = []
    prev_temp = None
    
    for event in temp_events:
        is_significant = False
        
        # 온도 0 설정 (꺼짐)
        if event.temp == 0:
            is_significant = True
        
        # 급격한 온도 변화 (50도 이상)
        if prev_temp is not None and abs(event.temp - prev_temp) >= 50:
            is_significant = True
        
        # 첫 온도 설정
        if prev_temp is None and event.temp > 0:
            is_significant = True
            
        if is_significant:
            significant.append(event)
        
        prev_temp = event.temp
    
    return significant
