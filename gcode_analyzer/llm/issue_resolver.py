"""
Issue Resolver - AI 해결하기 기능 실행 모듈
이슈의 원인 분석 및 해결 방법 제공 (간결한 3섹션 구조)
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from .client import get_llm_client
from .issue_resolver_prompt import ISSUE_RESOLVER_PROMPT
from .language import get_language_instruction

logger = logging.getLogger(__name__)


# ============================================================
# 통일된 응답 모델 (단일/그룹 공통)
# ============================================================

class CodeFix(BaseModel):
    """코드 수정 정보 (단일 라인)"""
    has_fix: bool = Field(description="수정 필요 여부")
    line_number: Optional[int] = Field(None, description="라인 번호")
    original: Optional[str] = Field(None, description="원본 코드 (라인번호: 코드 형식)")
    fixed: Optional[str] = Field(None, description="수정된 코드 (라인번호: 코드 형식)")


class Explanation(BaseModel):
    """문제 해설"""
    summary: str = Field(description="핵심 설명 (1-2문장)")
    cause: str = Field(description="원인 분석 (2-3문장)")
    is_false_positive: bool = Field(default=False, description="오탐 여부")
    severity: str = Field(default="medium", description="심각도: none|low|medium|high|critical")


class Solution(BaseModel):
    """
    해결 방안 (통일된 형식)

    ## 공통 응답 형식
    - code_fix: 대표 수정 (단일 이슈용, 항상 존재)
    - code_fixes: 모든 수정 배열 (단일이어도 1개 배열로 제공)

    ### 단일 이슈
    code_fix = {has_fix: true, line_number: 123, ...}
    code_fixes = [{has_fix: true, line_number: 123, ...}]  # 1개 배열

    ### 그룹 이슈
    code_fix = {has_fix: true, line_number: 123, ...}  # 대표 (첫 번째)
    code_fixes = [{...}, {...}, ...]  # 모든 수정
    """
    action_needed: bool = Field(description="조치 필요 여부")
    steps: List[str] = Field(description="해결 단계")
    code_fix: Optional[CodeFix] = Field(None, description="대표 코드 수정 (첫 번째 또는 단일)")
    code_fixes: Optional[List[CodeFix]] = Field(None, description="모든 코드 수정 배열")


class IssueResolution(BaseModel):
    """이슈 해결 결과 (3섹션)"""
    explanation: Explanation
    solution: Solution
    tips: List[str]


# 기본 CodeFix 객체 (수정 없음)
DEFAULT_CODE_FIX = {
    "has_fix": False,
    "line_number": None,
    "original": None,
    "fixed": None
}


async def resolve_issue(
    issue: Dict[str, Any],
    gcode_context: str = "",
    summary_info: Optional[Dict[str, Any]] = None,
    language: str = "ko"
) -> Dict[str, Any]:
    """
    이슈에 대한 상세 분석 및 해결 방법 제공

    Args:
        issue: 이슈 정보
            - 독립 이슈: line, type, severity, gcode_context 등
            - 그룹 이슈: is_grouped=True, all_issues=[{line, gcode_context, ...}, ...]
        gcode_context: 해당 라인 주변의 G-code 컨텍스트 (독립 이슈용, 없으면 issue에서 추출)
        summary_info: 전체 분석 요약 정보 (온도, 속도 등)
        language: 응답 언어

    Returns:
        {
            "resolution": {...},  # 해결 결과 (explanation, solution, tips)
            "updated_issue": {...}  # 수정된 원본 이슈 (오탐 시 severity="none", has_issue=false 등)
        }
    """
    llm = get_llm_client(max_output_tokens=1024)

    # ============================================================
    # gcode_context 결정: 파라미터 > issue 내부 > all_issues에서 추출
    # ============================================================
    final_gcode_context = gcode_context

    if not final_gcode_context:
        # 1. issue 자체에 gcode_context가 있는 경우 (독립 이슈)
        if issue.get("gcode_context"):
            final_gcode_context = issue.get("gcode_context")

        # 2. all_issues가 있는 경우: 각 라인의 gcode_context 조합 (단일/그룹 공통)
        elif issue.get("all_issues"):
            all_issues = issue.get("all_issues", [])
            context_parts = []

            # 최대 5개 라인만 컨텍스트 제공 (토큰 절약)
            for idx, sub_issue in enumerate(all_issues[:5]):
                line_num = sub_issue.get("line")
                sub_context = sub_issue.get("gcode_context", "")

                if sub_context:
                    context_parts.append(f"--- 문제 라인 {idx + 1}: Line {line_num} ---")
                    context_parts.append(sub_context)
                    context_parts.append("")  # 빈 줄로 구분

            remaining = len(all_issues) - 5
            if remaining > 0:
                context_parts.append(f"... 외 {remaining}건 동일 패턴")

            final_gcode_context = '\n'.join(context_parts)

    # gcode_context가 여전히 없으면 기본 메시지
    if not final_gcode_context:
        final_gcode_context = "(G-code 컨텍스트 없음)"

    # 입력 데이터 준비
    issue_json = json.dumps(issue, indent=2, ensure_ascii=False)
    summary_json = json.dumps(summary_info or {}, indent=2, ensure_ascii=False)

    # 프롬프트 구성
    prompt_text = ISSUE_RESOLVER_PROMPT.format(
        issue_json=issue_json,
        gcode_context=final_gcode_context,
        summary_info=summary_json
    )

    # 언어 설정
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    try:
        response = await llm.ainvoke(prompt_text)

        # response.content가 리스트인 경우 처리 (Claude API 응답 형식)
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, list):
                # 리스트인 경우 텍스트 블록 추출
                output_text = ""
                for block in content:
                    if hasattr(block, 'text'):
                        output_text += block.text
                    elif isinstance(block, dict) and 'text' in block:
                        output_text += block['text']
                    elif isinstance(block, str):
                        output_text += block
            else:
                output_text = str(content)
        else:
            output_text = str(response)

        # JSON 파싱
        json_text = output_text
        if "```json" in output_text:
            json_text = output_text.split("```json")[1].split("```")[0]
        elif "```" in output_text:
            json_text = output_text.split("```")[1].split("```")[0]

        resolution = json.loads(json_text.strip())

        # ============================================================
        # 응답 정규화: code_fix / code_fixes 통일
        # ============================================================
        solution = resolution.get("solution", {})
        code_fix = solution.get("code_fix")
        code_fixes = solution.get("code_fixes")

        # 1. code_fix가 None이면 기본값 설정
        if code_fix is None:
            code_fix = DEFAULT_CODE_FIX.copy()

        # 2. code_fixes 정규화 (항상 배열로)
        if code_fixes is None:
            # code_fix가 있으면 1개짜리 배열로
            if code_fix.get("has_fix"):
                code_fixes = [code_fix.copy()]
            else:
                code_fixes = []
        elif not isinstance(code_fixes, list):
            code_fixes = []

        # 3. code_fix가 없는데 code_fixes가 있으면 첫 번째를 대표로
        if not code_fix.get("has_fix") and code_fixes:
            code_fix = code_fixes[0].copy() if code_fixes[0] else DEFAULT_CODE_FIX.copy()

        solution["code_fix"] = code_fix
        solution["code_fixes"] = code_fixes
        resolution["solution"] = solution

        # 원본 이슈 수정 (오탐 여부에 따라)
        updated_issue = _update_issue_from_resolution(issue, resolution)

        logger.info(f"[IssueResolver] Successfully resolved issue: {issue.get('type', 'unknown')}, is_false_positive={resolution.get('explanation', {}).get('is_false_positive', False)}")

        return {
            "resolution": resolution,
            "updated_issue": updated_issue
        }

    except json.JSONDecodeError as e:
        logger.error(f"[IssueResolver] JSON parsing error: {e}")
        fallback = _get_fallback_response(issue, str(e))
        return {
            "resolution": fallback,
            "updated_issue": issue  # 오류 시 원본 유지
        }
    except Exception as e:
        logger.error(f"[IssueResolver] Error resolving issue: {e}")
        fallback = _get_fallback_response(issue, str(e))
        return {
            "resolution": fallback,
            "updated_issue": issue  # 오류 시 원본 유지
        }


def _update_issue_from_resolution(
    original_issue: Dict[str, Any],
    resolution: Dict[str, Any]
) -> Dict[str, Any]:
    """
    AI 해결 결과를 바탕으로 원본 이슈 업데이트

    - 오탐(false positive)인 경우: severity="none", has_issue=false
    - 실제 문제인 경우: 심각도 조정, 해결책 추가
    """
    updated = original_issue.copy()

    explanation = resolution.get("explanation", {})
    solution = resolution.get("solution", {})

    is_false_positive = explanation.get("is_false_positive", False)
    new_severity = explanation.get("severity", original_issue.get("severity", "medium"))

    if is_false_positive:
        # 오탐으로 판정된 경우
        updated["has_issue"] = False
        updated["severity"] = "none"
        updated["is_false_positive"] = True
        updated["false_positive_reason"] = explanation.get("cause", "오탐으로 판정됨")
    else:
        # 실제 문제인 경우
        updated["has_issue"] = True
        updated["severity"] = new_severity if new_severity != "none" else original_issue.get("severity", "medium")
        updated["is_false_positive"] = False

    # 해결책 정보 추가
    updated["ai_resolution"] = {
        "summary": explanation.get("summary", ""),
        "cause": explanation.get("cause", ""),
        "action_needed": solution.get("action_needed", True),
        "steps": solution.get("steps", []),
        "tips": resolution.get("tips", [])
    }

    # ============================================================
    # 코드 수정 정보 (통일된 형식)
    # - code_fix: 대표 수정 (항상 존재)
    # - code_fixes: 모든 수정 배열 (항상 배열)
    # ============================================================
    code_fix = solution.get("code_fix") or DEFAULT_CODE_FIX.copy()
    code_fixes = solution.get("code_fixes") or []

    updated["code_fix"] = code_fix
    updated["code_fixes"] = code_fixes

    # 그룹 이슈인 경우: all_issues 내 각 이슈도 업데이트
    if original_issue.get("all_issues"):
        updated_all_issues = []
        for idx, sub_issue in enumerate(original_issue.get("all_issues", [])):
            updated_sub = sub_issue.copy()
            updated_sub["has_issue"] = not is_false_positive
            updated_sub["severity"] = "none" if is_false_positive else new_severity
            updated_sub["is_false_positive"] = is_false_positive
            if is_false_positive:
                updated_sub["false_positive_reason"] = explanation.get("cause", "오탐으로 판정됨")

            # 각 sub_issue에 해당하는 code_fix 매칭
            if idx < len(code_fixes):
                updated_sub["code_fix"] = code_fixes[idx]
            else:
                updated_sub["code_fix"] = DEFAULT_CODE_FIX.copy()

            updated_all_issues.append(updated_sub)
        updated["all_issues"] = updated_all_issues

    return updated


def _get_fallback_response(issue: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
    """
    오류 발생 시 기본 응답 (통일된 형식)

    Returns:
        code_fix: 대표 수정 (항상 객체)
        code_fixes: 모든 수정 (항상 배열)
    """
    # lines 배열에서 첫 번째 라인 번호 추출
    lines = issue.get("lines", [])
    line_number = lines[0] if lines else issue.get("event_line_index")

    # 기본 code_fix (수정 없음)
    default_fix = {
        "has_fix": False,
        "line_number": line_number,
        "original": None,
        "fixed": None
    }

    return {
        "explanation": {
            "summary": issue.get("description", "분석 중 오류가 발생했습니다."),
            "cause": f"자동 분석 실패: {error_msg}",
            "is_false_positive": False,
            "severity": issue.get("severity", "medium")
        },
        "solution": {
            "action_needed": True,
            "steps": [
                issue.get("fix_proposal", "슬라이서 설정을 확인하세요."),
                "문제가 지속되면 G-code를 다시 생성하세요."
            ],
            "code_fix": default_fix,
            "code_fixes": []  # 항상 배열
        },
        "tips": [
            "슬라이서 설정을 확인하세요.",
            "G-code를 다시 생성해보세요."
        ]
    }


def extract_gcode_context(
    gcode_content: str,
    line_number: int,
    context_lines: int = 10
) -> str:
    """
    G-code에서 특정 라인 주변의 컨텍스트 추출

    Args:
        gcode_content: 전체 G-code 내용
        line_number: 대상 라인 번호 (1-based) 또는 쉼표 구분 문자열
        context_lines: 앞뒤로 포함할 라인 수

    Returns:
        라인 번호가 포함된 G-code 컨텍스트
    """
    if not line_number or not gcode_content:
        return ""

    # 문자열인 경우 (그룹 이슈: "524, 589, 746")
    if isinstance(line_number, str):
        try:
            line_numbers = [int(x.strip()) for x in line_number.split(",")]
            return extract_gcode_context_multi(gcode_content, line_numbers, context_lines)
        except ValueError:
            return ""

    # 리스트인 경우
    if isinstance(line_number, list):
        return extract_gcode_context_multi(gcode_content, line_number, context_lines)

    lines = gcode_content.split('\n')
    total_lines = len(lines)

    # 0-based index로 변환
    target_idx = line_number - 1

    # 범위 계산
    start_idx = max(0, target_idx - context_lines)
    end_idx = min(total_lines, target_idx + context_lines + 1)

    # 컨텍스트 생성
    context_parts = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = lines[i]

        # 대상 라인 강조
        if i == target_idx:
            context_parts.append(f">>> {line_num}: {line_content}  <<< [문제 라인]")
        else:
            context_parts.append(f"    {line_num}: {line_content}")

    return '\n'.join(context_parts)


def extract_gcode_context_multi(
    gcode_content: str,
    line_numbers: List[int],
    context_lines: int = 5
) -> str:
    """
    G-code에서 여러 라인의 컨텍스트 추출 (그룹 이슈용)

    Args:
        gcode_content: 전체 G-code 내용
        line_numbers: 대상 라인 번호들 (1-based)
        context_lines: 각 라인 앞뒤로 포함할 라인 수 (기본 5)

    Returns:
        각 문제 라인별 컨텍스트 (구분선으로 분리)
    """
    if not line_numbers or not gcode_content:
        return ""

    lines = gcode_content.split('\n')
    total_lines = len(lines)

    # 최대 5개 라인만 컨텍스트 제공 (토큰 절약)
    target_lines = line_numbers[:5]
    remaining = len(line_numbers) - 5

    context_parts = []

    for idx, line_number in enumerate(target_lines):
        if not isinstance(line_number, int):
            continue

        target_idx = line_number - 1
        if target_idx < 0 or target_idx >= total_lines:
            continue

        # 범위 계산
        start_idx = max(0, target_idx - context_lines)
        end_idx = min(total_lines, target_idx + context_lines + 1)

        context_parts.append(f"--- 문제 라인 {idx + 1}: Line {line_number} ---")

        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i]

            if i == target_idx:
                context_parts.append(f">>> {line_num}: {line_content}  <<< [문제]")
            else:
                context_parts.append(f"    {line_num}: {line_content}")

        context_parts.append("")  # 빈 줄로 구분

    if remaining > 0:
        context_parts.append(f"... 외 {remaining}건 동일 패턴")

    return '\n'.join(context_parts)
