"""
델타 기반 G-code 병합기
Delta-based G-code Merger

클라이언트에서 전송한 델타(변경사항)를 원본 G-code와 병합하여
수정된 G-code를 스트리밍 방식으로 생성

메모리 효율적: 50만 줄 G-code도 전체를 메모리에 올리지 않고 처리
"""
from typing import List, Iterator, Dict, Set, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import logging

from .models import LineDelta, DeltaAction

logger = logging.getLogger("uvicorn.error")


class DeltaMergeResult:
    """델타 병합 결과 통계"""
    def __init__(self):
        self.total_lines = 0
        self.applied_deltas = 0
        self.skipped_deltas = 0
        self.warnings: List[str] = []


def _prepare_delta_maps(deltas: List[LineDelta]) -> Tuple[
    Dict[int, str],      # modify_map
    Set[int],            # delete_set
    Dict[int, List[str]], # insert_before_map
    Dict[int, List[str]]  # insert_after_map
]:
    """
    델타 목록을 액션별 맵으로 정리

    Returns:
        (modify_map, delete_set, insert_before_map, insert_after_map)
    """
    modify_map: Dict[int, str] = {}
    delete_set: Set[int] = set()
    insert_before_map: Dict[int, List[str]] = defaultdict(list)
    insert_after_map: Dict[int, List[str]] = defaultdict(list)

    for delta in deltas:
        action = delta.action
        idx = delta.line_index

        if action == DeltaAction.MODIFY or action == "modify":
            if delta.new_content:
                modify_map[idx] = delta.new_content
        elif action == DeltaAction.DELETE or action == "delete":
            delete_set.add(idx)
        elif action == DeltaAction.INSERT_BEFORE or action == "insert_before":
            if delta.new_content:
                insert_before_map[idx].append(delta.new_content)
        elif action == DeltaAction.INSERT_AFTER or action == "insert_after":
            if delta.new_content:
                insert_after_map[idx].append(delta.new_content)

    return modify_map, delete_set, insert_before_map, insert_after_map


def merge_deltas_streaming(
    original_lines_iter: Iterator[str],
    deltas: List[LineDelta],
    result: Optional[DeltaMergeResult] = None
) -> Iterator[str]:
    """
    스트리밍 방식으로 델타를 원본과 병합

    메모리 효율적: 전체 파일을 메모리에 올리지 않음
    50만 줄 G-code도 문제없이 처리

    Args:
        original_lines_iter: 원본 G-code 라인 이터레이터
        deltas: 적용할 델타 목록
        result: 결과 통계 객체 (선택적)

    Yields:
        병합된 G-code 라인들
    """
    if result is None:
        result = DeltaMergeResult()

    # 델타를 액션별 맵으로 정리
    modify_map, delete_set, insert_before_map, insert_after_map = _prepare_delta_maps(deltas)

    # 적용된 델타 추적
    applied_indices: Set[int] = set()

    # 스트리밍 병합
    for idx, line in enumerate(original_lines_iter):
        result.total_lines += 1

        # 1. insert_before 처리 (해당 라인 앞에 삽입)
        if idx in insert_before_map:
            for insert_content in insert_before_map[idx]:
                # 줄바꿈이 없으면 추가
                if not insert_content.endswith('\n'):
                    insert_content += '\n'
                yield insert_content
                applied_indices.add(idx)
                result.applied_deltas += 1

        # 2. modify/delete 처리
        if idx in delete_set:
            # 삭제: 출력하지 않음
            applied_indices.add(idx)
            result.applied_deltas += 1
            # insert_after는 여전히 처리 (삭제된 라인 위치에 추가)
        elif idx in modify_map:
            # 수정: 새 내용으로 대체
            new_content = modify_map[idx]
            if not new_content.endswith('\n'):
                new_content += '\n'
            yield new_content
            applied_indices.add(idx)
            result.applied_deltas += 1
        else:
            # 원본 유지
            # 이미 \n 포함되어 있을 수 있으므로 확인
            if not line.endswith('\n'):
                line += '\n'
            yield line

        # 3. insert_after 처리 (해당 라인 뒤에 삽입)
        # 삭제된 라인이어도 insert_after는 처리
        if idx in insert_after_map:
            for insert_content in insert_after_map[idx]:
                if not insert_content.endswith('\n'):
                    insert_content += '\n'
                yield insert_content
                applied_indices.add(idx)
                result.applied_deltas += 1

    # 스킵된 델타 계산 (존재하지 않는 라인 인덱스 등)
    all_delta_indices = (
        set(modify_map.keys()) |
        delete_set |
        set(insert_before_map.keys()) |
        set(insert_after_map.keys())
    )
    skipped_indices = all_delta_indices - applied_indices
    result.skipped_deltas = len(skipped_indices)

    if skipped_indices:
        result.warnings.append(
            f"일부 델타가 적용되지 않음 (라인 인덱스 범위 초과): {sorted(skipped_indices)[:10]}"
        )


def generate_header_comment(
    deltas: List[LineDelta],
    original_filename: Optional[str] = None
) -> Iterator[str]:
    """
    수정 이력 헤더 주석 생성

    Args:
        deltas: 적용된 델타 목록
        original_filename: 원본 파일명

    Yields:
        헤더 주석 라인들
    """
    yield "; ============================================\n"
    yield "; Modified by Factor AI G-code Analyzer\n"
    yield f"; Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if original_filename:
        yield f"; Original: {original_filename}\n"
    yield f"; Applied {len(deltas)} changes\n"
    yield "; ============================================\n"

    # 변경 요약
    modify_count = sum(1 for d in deltas if d.action in [DeltaAction.MODIFY, "modify"])
    delete_count = sum(1 for d in deltas if d.action in [DeltaAction.DELETE, "delete"])
    insert_count = sum(1 for d in deltas if d.action in [
        DeltaAction.INSERT_BEFORE, DeltaAction.INSERT_AFTER,
        "insert_before", "insert_after"
    ])

    if modify_count:
        yield f"; - Modified: {modify_count} lines\n"
    if delete_count:
        yield f"; - Deleted: {delete_count} lines\n"
    if insert_count:
        yield f"; - Inserted: {insert_count} lines\n"

    yield "; ============================================\n"
    yield ";\n"


def stream_from_file(file_path: str) -> Iterator[str]:
    """
    로컬 파일에서 라인 단위로 스트리밍

    Args:
        file_path: 파일 경로

    Yields:
        파일 라인들
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            yield line


def stream_from_string(content: str) -> Iterator[str]:
    """
    문자열에서 라인 단위로 스트리밍

    Args:
        content: G-code 문자열

    Yields:
        라인들
    """
    for line in content.splitlines(keepends=True):
        yield line


async def stream_from_url(url: str) -> Iterator[str]:
    """
    URL에서 라인 단위로 스트리밍 (Supabase Storage 등)

    Args:
        url: 파일 URL

    Yields:
        파일 라인들
    """
    import httpx

    async with httpx.AsyncClient() as client:
        async with client.stream('GET', url) as response:
            response.raise_for_status()
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    yield line + '\n'
            # 마지막 줄 (줄바꿈 없이 끝난 경우)
            if buffer:
                yield buffer


def merge_deltas_to_list(
    original_lines: List[str],
    deltas: List[LineDelta]
) -> Tuple[List[str], DeltaMergeResult]:
    """
    리스트 기반 델타 병합 (작은 파일용)

    Args:
        original_lines: 원본 라인 리스트
        deltas: 적용할 델타 목록

    Returns:
        (병합된 라인 리스트, 결과 통계)
    """
    result = DeltaMergeResult()
    merged_lines = list(merge_deltas_streaming(iter(original_lines), deltas, result))
    return merged_lines, result


def validate_deltas(deltas: List[LineDelta], total_lines: int) -> List[str]:
    """
    델타 유효성 검증

    Args:
        deltas: 검증할 델타 목록
        total_lines: 원본 파일 총 라인 수

    Returns:
        경고 메시지 목록
    """
    warnings = []

    for delta in deltas:
        # 라인 인덱스 범위 검사
        if delta.line_index < 0:
            warnings.append(f"음수 라인 인덱스: {delta.line_index}")
        elif delta.line_index >= total_lines:
            warnings.append(f"라인 인덱스 범위 초과: {delta.line_index} (총 {total_lines}줄)")

        # 액션별 필수 필드 검사
        if delta.action in [DeltaAction.MODIFY, DeltaAction.INSERT_BEFORE, DeltaAction.INSERT_AFTER,
                           "modify", "insert_before", "insert_after"]:
            if not delta.new_content:
                warnings.append(f"라인 {delta.line_index}: {delta.action} 액션에 new_content 필요")

    return warnings
