"""
온도 패턴 스캐너 - BODY 섹션 전체 스캔
LLM 토큰 제한 없이 전체 온도 이상 패턴을 탐지
"""
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..models import TempEvent, GCodeLine
from ..section_detector import SectionBoundaries, GCodeSection
from ..config import DEFAULT_FILAMENTS


def scan_temperature_anomalies(
    temp_events: List[TempEvent],
    parsed_lines: List[GCodeLine],
    boundaries: SectionBoundaries,
    filament_type: str = "PLA"
) -> Dict[str, Any]:
    """
    BODY 섹션 전체를 스캔하여 온도 이상 패턴 탐지

    Args:
        temp_events: 온도 이벤트 목록
        parsed_lines: 파싱된 G-code 라인
        boundaries: 섹션 경계
        filament_type: 필라멘트 타입

    Returns:
        {
            "issues": [...],           # 개별 이슈 목록
            "grouped_issues": [...],   # 그룹화된 이슈 목록
            "summary": {...}           # 요약 정보
        }
    """
    # 시작 온도 찾기 (첫 번째 유효한 노즐 온도)
    initial_nozzle_temp: Optional[float] = None
    for event in temp_events:
        if event.cmd in ["M104", "M109"] and event.temp > 0:
            initial_nozzle_temp = event.temp
            break

    # 최소 온도 임계값 결정
    filament_config = DEFAULT_FILAMENTS.get(filament_type) if filament_type else None

    if filament_config:
        # 필라멘트 타입이 있으면 해당 최소 온도 사용
        min_temp = filament_config.min_nozzle_temp
    elif initial_nozzle_temp:
        # 필라멘트 타입 없으면 시작 온도의 95% (5% 허용)
        min_temp = initial_nozzle_temp * 0.95
    else:
        # 둘 다 없으면 기본값 180°C
        min_temp = 180.0

    issues = []
    prev_nozzle_temp: Optional[float] = None

    # 라인 인덱스로 빠른 조회용 맵
    line_map = {line.index: line for line in parsed_lines}

    for event in temp_events:
        # 노즐 온도만 검사 (M104, M109)
        if event.cmd not in ["M104", "M109"]:
            continue

        # BODY 섹션만 검사
        section = boundaries.get_section(event.line_index)
        if section != GCodeSection.BODY:
            # START/END 구간의 온도는 prev_temp 업데이트만
            prev_nozzle_temp = event.temp
            continue

        # H 파라미터 확인 (Bambu Lab/OrcaSlicer 확장)
        has_h_param = False
        if event.line_index in line_map:
            raw_line = line_map[event.line_index].raw.upper()
            has_h_param = " H" in raw_line or "\tH" in raw_line

        # 1. 온도 0 설정 (H 파라미터 없이)
        if event.temp == 0 and not has_h_param:
            issues.append({
                "type": "temp_zero_in_body",
                "line": event.line_index,
                "severity": "critical",
                "temp": event.temp,
                "cmd": event.cmd,
                "description": f"BODY 구간에서 노즐 온도 0 설정 ({event.cmd} S0)"
            })

        # 2. 저온 압출 위험 (필라멘트 최소 온도 미만, 0 제외)
        elif 0 < event.temp < min_temp and not has_h_param:
            issues.append({
                "type": "cold_extrusion",
                "line": event.line_index,
                "severity": "critical",
                "temp": event.temp,
                "min_temp": min_temp,
                "cmd": event.cmd,
                "description": f"저온 압출 위험: {event.temp}°C (최소 {min_temp:.0f}°C 필요)"
            })

        # 3. 급격한 온도 하락 (50°C 이상 감소)
        if prev_nozzle_temp is not None and prev_nozzle_temp > 0:
            temp_drop = prev_nozzle_temp - event.temp
            if temp_drop >= 50 and event.temp > 0:
                issues.append({
                    "type": "rapid_temp_drop",
                    "line": event.line_index,
                    "severity": "high",
                    "temp_before": prev_nozzle_temp,
                    "temp_after": event.temp,
                    "temp_drop": temp_drop,
                    "cmd": event.cmd,
                    "description": f"급격한 온도 하락: {prev_nozzle_temp}°C → {event.temp}°C ({temp_drop}°C 감소)"
                })

        prev_nozzle_temp = event.temp

    # 이슈 그룹화
    grouped_issues = group_similar_issues(issues, min_temp)

    return {
        "issues": issues,
        "grouped_issues": grouped_issues,
        "summary": {
            "total_issues": len(issues),
            "grouped_count": len(grouped_issues),
            "filament_type": filament_type or "unknown",
            "min_temp_threshold": min_temp,
            "initial_temp": initial_nozzle_temp
        }
    }


def group_similar_issues(
    issues: List[Dict[str, Any]],
    min_temp: float
) -> List[Dict[str, Any]]:
    """
    같은 타입의 이슈를 그룹화

    ## 통일된 리턴 형식 (line 필드 없음, lines 배열만 사용)

    ### 단일 이슈 (is_grouped: False)
    {
        "id": "TEMP-1",
        "type": "cold_extrusion",
        "is_grouped": False,
        "count": 1,
        "severity": "critical",
        "lines": [12345],           # 항상 배열 (단일이어도)
        "title": "저온 압출 위험",
        "description": "...",
        "all_issues": [{            # 단일이어도 배열
            "line": 12345,          # 개별 이슈 내부에만 line 존재
            "gcode_context": "..."  # nodes.py에서 추가
        }]
    }

    ### 그룹 이슈 (is_grouped: True)
    {
        "id": "TEMP-GROUP-1",
        "type": "cold_extrusion",
        "is_grouped": True,
        "count": 5,
        "severity": "critical",
        "lines": [12345, 12500, ...], # 모든 라인 배열
        "title": "저온 압출 위험",
        "description": "...",
        "all_issues": [{...}, ...]    # 모든 개별 이슈
    }

    Args:
        issues: 개별 이슈 목록
        min_temp: 최소 온도 임계값

    Returns:
        그룹화된 이슈 목록 (통일된 형식)
    """
    if not issues:
        return []

    # 타입별로 그룹화
    grouped = defaultdict(list)
    for issue in issues:
        grouped[issue["type"]].append(issue)

    result = []
    group_id = 1

    for issue_type, type_issues in grouped.items():
        lines = [i["line"] for i in type_issues]
        severity = _get_max_severity([i["severity"] for i in type_issues])

        if len(type_issues) == 1:
            # 단일 이슈 (통일된 형식)
            single = type_issues[0]
            result.append({
                "id": f"TEMP-{group_id}",
                "type": single["type"],
                "is_grouped": False,
                "count": 1,
                "severity": single["severity"],
                "lines": [single["line"]],        # 항상 배열 (line 필드 제거)
                "title": _get_issue_title(single["type"]),
                "description": single["description"],
                "all_issues": [single]            # 단일이어도 배열로
            })
        else:
            # 그룹 이슈 (통일된 형식)
            result.append({
                "id": f"TEMP-GROUP-{group_id}",
                "type": issue_type,
                "is_grouped": True,
                "count": len(type_issues),
                "severity": severity,
                "lines": lines,                   # 항상 배열 (line 필드 제거)
                "title": _get_issue_title(issue_type),
                "description": _get_grouped_description(issue_type, len(type_issues), min_temp),
                "all_issues": type_issues         # 모든 개별 이슈
            })

        group_id += 1

    # 심각도 순 정렬
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    result.sort(key=lambda x: severity_order.get(x["severity"], 4))

    return result


def _get_issue_title(issue_type: str) -> str:
    """이슈 타입별 제목"""
    titles = {
        "temp_zero_in_body": "출력 중 온도 0 설정",
        "cold_extrusion": "저온 압출 위험",
        "rapid_temp_drop": "급격한 온도 하락"
    }
    return titles.get(issue_type, issue_type)


def _get_grouped_description(
    issue_type: str,
    count: int,
    min_temp: float
) -> str:
    """그룹화된 이슈 설명"""
    descriptions = {
        "temp_zero_in_body": f"BODY 구간에서 노즐 온도를 0으로 설정한 위치 {count}건",
        "cold_extrusion": f"최소 온도({min_temp:.0f}°C) 미만 저온 압출 위험 {count}건",
        "rapid_temp_drop": f"50°C 이상 급격한 온도 하락 {count}건"
    }
    return descriptions.get(issue_type, f"{issue_type} {count}건")


def _get_max_severity(severities: List[str]) -> str:
    """가장 높은 심각도 반환"""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return min(severities, key=lambda s: severity_order.get(s, 4))
