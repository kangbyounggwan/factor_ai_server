"""
LLM-based G-code Patch Generator
이슈에 대해 실제 적용 가능한 G-code 패치를 생성
"""
import json
from typing import Dict, Any, List, Tuple, Optional, Callable
from .client import get_llm_client
from .patch_generator_prompt import PATCH_GENERATOR_PROMPT, BATCH_PATCH_GENERATOR_PROMPT
from .language import get_language_instruction
from ..models import GCodeLine

StreamingCallback = Callable[[str], None]


def extract_snippet(
    lines: List[GCodeLine],
    target_line_index: int,
    context_size: int = 5
) -> Dict[str, Any]:
    """
    대상 라인 앞뒤로 context_size 줄씩 추출

    Args:
        lines: 파싱된 G-code 라인들
        target_line_index: 대상 라인 번호 (1-based)
        context_size: 앞뒤로 추출할 라인 수

    Returns:
        {
            "before": ["line1", "line2", ...],  # 앞 5줄
            "target": "target line content",
            "after": ["line6", "line7", ...],   # 뒤 5줄
            "target_line_number": 123
        }
    """
    idx_0 = target_line_index - 1  # 0-based index

    # 범위 계산
    start_before = max(0, idx_0 - context_size)
    end_before = idx_0
    start_after = idx_0 + 1
    end_after = min(len(lines), idx_0 + context_size + 1)

    # 앞 줄들
    before_lines = []
    for i in range(start_before, end_before):
        before_lines.append(f"{lines[i].index}: {lines[i].raw.strip()}")

    # 패딩 (부족하면 빈 문자열)
    while len(before_lines) < context_size:
        before_lines.insert(0, "")

    # 대상 라인
    target_line = ""
    if 0 <= idx_0 < len(lines):
        target_line = lines[idx_0].raw.strip()

    # 뒤 줄들
    after_lines = []
    for i in range(start_after, end_after):
        after_lines.append(f"{lines[i].index}: {lines[i].raw.strip()}")

    # 패딩
    while len(after_lines) < context_size:
        after_lines.append("")

    return {
        "before": before_lines,
        "target": target_line,
        "after": after_lines,
        "target_line_number": target_line_index
    }


async def generate_patch_for_issue(
    issue: Dict[str, Any],
    lines: List[GCodeLine],
    filament_info: Optional[Dict[str, Any]] = None,
    slicer_info: Optional[str] = None,
    streaming_callback: Optional[StreamingCallback] = None,
    language: str = "ko"
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    단일 이슈에 대한 패치 생성

    Args:
        issue: 이슈 정보 (id, line, type, severity, description, fix_proposal 등)
        lines: 파싱된 G-code 라인들
        filament_info: 필라멘트 정보
        slicer_info: 슬라이서 정보
        streaming_callback: 스트리밍 콜백
        language: 언어 설정

    Returns:
        (패치 결과, 토큰 사용량)
    """
    llm = get_llm_client()
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 이슈에서 라인 번호 추출
    line_number = issue.get("line") or issue.get("line_index") or issue.get("event_line_index")
    if not line_number:
        return {"error": "라인 번호 없음"}, token_usage

    # 스니펫 추출
    snippet = extract_snippet(lines, line_number, context_size=5)

    # 필라멘트 정보 기본값
    if not filament_info:
        filament_info = {
            "type": "PLA",
            "nozzle_temp": "200-220",
            "bed_temp": "60"
        }

    # 프롬프트 구성
    input_data = {
        "issue_json": json.dumps(issue, indent=2, ensure_ascii=False),
        "snippet_before": "\n".join(snippet["before"]),
        "target_line_number": line_number,
        "target_line": snippet["target"],
        "snippet_after": "\n".join(snippet["after"]),
        "filament_type": filament_info.get("type", "PLA"),
        "filament_nozzle_temp": filament_info.get("nozzle_temp", "200-220"),
        "filament_bed_temp": filament_info.get("bed_temp", "60"),
        "slicer_info": slicer_info or "Unknown"
    }

    prompt_text = PATCH_GENERATOR_PROMPT.format(**input_data)

    # 언어 설정
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    # 토큰 추정
    input_tokens_estimate = len(prompt_text) // 4
    token_usage["input_tokens"] = input_tokens_estimate

    output_text = ""
    try:
        if streaming_callback:
            async for chunk in llm.astream(prompt_text):
                chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
                output_text += chunk_text
                streaming_callback(chunk_text)
            token_usage["output_tokens"] = len(output_text) // 4
        else:
            response = await llm.ainvoke(prompt_text)

            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if 'usage_metadata' in metadata:
                    usage = metadata['usage_metadata']
                    token_usage["input_tokens"] = usage.get('prompt_token_count', input_tokens_estimate)
                    token_usage["output_tokens"] = usage.get('candidates_token_count', 0)

            output_text = response.content if hasattr(response, 'content') else str(response)

            if token_usage["output_tokens"] == 0:
                token_usage["output_tokens"] = len(output_text) // 4

        token_usage["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]

        # JSON 파싱
        json_text = output_text
        if "```json" in output_text:
            json_text = output_text.split("```json")[1].split("```")[0]
        elif "```" in output_text:
            json_text = output_text.split("```")[1].split("```")[0]

        result = json.loads(json_text.strip())
        return result, token_usage

    except Exception as e:
        return {
            "error": str(e),
            "patch_id": issue.get("patch_id", "PATCH-ERR"),
            "issue_id": issue.get("id", "ISSUE-ERR"),
            "line_number": line_number,
            "action": "review",
            "can_auto_apply": False,
            "original_code": {
                "line": snippet["target"],
                "context_before": snippet["before"],
                "context_after": snippet["after"]
            },
            "patched_code": None,
            "explanation": f"패치 생성 실패: {str(e)}",
            "risk_level": "high"
        }, token_usage


async def generate_patches_batch(
    issues: List[Dict[str, Any]],
    lines: List[GCodeLine],
    filament_info: Optional[Dict[str, Any]] = None,
    slicer_info: Optional[str] = None,
    streaming_callback: Optional[StreamingCallback] = None,
    language: str = "ko"
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    여러 이슈에 대한 패치 일괄 생성

    Args:
        issues: 이슈 목록
        lines: 파싱된 G-code 라인들
        filament_info: 필라멘트 정보
        slicer_info: 슬라이서 정보
        streaming_callback: 스트리밍 콜백
        language: 언어 설정

    Returns:
        (패치 결과 목록, 토큰 사용량)
    """
    llm = get_llm_client()
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    if not issues:
        return {"patches": [], "summary": {"total_patches": 0, "auto_applicable": 0, "needs_review": 0}}, token_usage

    # 각 이슈에 대한 스니펫 추출
    snippets = []
    for issue in issues:
        line_number = issue.get("line") or issue.get("line_index") or issue.get("event_line_index")
        if line_number:
            snippet = extract_snippet(lines, line_number, context_size=5)
            snippets.append({
                "issue_id": issue.get("id"),
                "line_number": line_number,
                "snippet": snippet
            })

    # 필라멘트 정보 기본값
    if not filament_info:
        filament_info = {
            "type": "PLA",
            "nozzle_temp": "200-220",
            "bed_temp": "60"
        }

    # 프롬프트 구성
    input_data = {
        "issues_json": json.dumps(issues, indent=2, ensure_ascii=False),
        "snippets_json": json.dumps(snippets, indent=2, ensure_ascii=False),
        "filament_type": filament_info.get("type", "PLA"),
        "filament_nozzle_temp": filament_info.get("nozzle_temp", "200-220"),
        "filament_bed_temp": filament_info.get("bed_temp", "60"),
        "slicer_info": slicer_info or "Unknown"
    }

    prompt_text = BATCH_PATCH_GENERATOR_PROMPT.format(**input_data)

    # 언어 설정
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    # 토큰 추정
    input_tokens_estimate = len(prompt_text) // 4
    token_usage["input_tokens"] = input_tokens_estimate

    output_text = ""
    try:
        if streaming_callback:
            async for chunk in llm.astream(prompt_text):
                chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
                output_text += chunk_text
                streaming_callback(chunk_text)
            token_usage["output_tokens"] = len(output_text) // 4
        else:
            response = await llm.ainvoke(prompt_text)

            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if 'usage_metadata' in metadata:
                    usage = metadata['usage_metadata']
                    token_usage["input_tokens"] = usage.get('prompt_token_count', input_tokens_estimate)
                    token_usage["output_tokens"] = usage.get('candidates_token_count', 0)

            output_text = response.content if hasattr(response, 'content') else str(response)

            if token_usage["output_tokens"] == 0:
                token_usage["output_tokens"] = len(output_text) // 4

        token_usage["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]

        # JSON 파싱
        json_text = output_text
        if "```json" in output_text:
            json_text = output_text.split("```json")[1].split("```")[0]
        elif "```" in output_text:
            json_text = output_text.split("```")[1].split("```")[0]

        result = json.loads(json_text.strip())
        return result, token_usage

    except Exception as e:
        # 실패 시 개별 처리로 폴백
        return {
            "patches": [],
            "summary": {
                "total_patches": 0,
                "auto_applicable": 0,
                "needs_review": len(issues)
            },
            "error": str(e)
        }, token_usage


def format_patch_diff(patch: Dict[str, Any]) -> str:
    """
    패치 결과를 diff 형식으로 포맷팅
    """
    lines = []
    lines.append(f"=== Patch {patch.get('patch_id', '?')} ===")
    lines.append(f"Issue: {patch.get('issue_id', '?')}")
    lines.append(f"Line: {patch.get('line_number', '?')}")
    lines.append(f"Action: {patch.get('action', '?')}")
    lines.append(f"Risk: {patch.get('risk_level', '?')}")
    lines.append(f"Auto-apply: {patch.get('can_auto_apply', False)}")
    lines.append("")

    original = patch.get("original_code", {})
    patched = patch.get("patched_code", {})

    lines.append("--- Original ---")
    for ctx in original.get("context_before", []):
        lines.append(f"  {ctx}")
    lines.append(f"- {original.get('line', '')}")
    for ctx in original.get("context_after", []):
        lines.append(f"  {ctx}")

    lines.append("")
    lines.append("+++ Patched +++")
    for ctx in patched.get("context_before", []) if patched else []:
        lines.append(f"  {ctx}")
    lines.append(f"+ {patched.get('line', '') if patched else '[삭제됨]'}")
    for ctx in patched.get("context_after", []) if patched else []:
        lines.append(f"  {ctx}")

    lines.append("")
    lines.append(f"Explanation: {patch.get('explanation', '')}")
    lines.append("=" * 40)

    return "\n".join(lines)
