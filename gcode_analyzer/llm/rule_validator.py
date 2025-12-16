"""
Rule Engine Issue Validator using Flash Lite
빠른 검증용 - Rule Engine에서 감지된 이슈를 LLM이 한 번 더 확인
"""
import json
from typing import Dict, Any, List, Tuple
from .client import get_llm_client_lite


VALIDATION_PROMPT = """당신은 3D 프린터 G-code 전문가입니다.
Rule Engine이 감지한 이슈가 실제 문제인지 검증해주세요.

## 감지된 이슈
- 규칙: {rule_name}
- 심각도: {severity}
- 라인: {line_index}
- 설명: {message}

## 관련 G-code (라인 {start_line}~{end_line})
```
{gcode_snippet}
```

## 컨텍스트
{context}

## 질문
이 이슈가 실제로 3D 프린팅에 문제를 일으킬 수 있는 진짜 문제인가요?

다음 JSON 형식으로만 답변:
```json
{{
  "is_valid_issue": true/false,
  "confidence": 0.0-1.0,
  "reason": "판단 이유 (한 문장)"
}}
```
"""


async def validate_rule_issues(
    rule_issues: List[Dict[str, Any]],
    parsed_lines: List[Any],
    context_lines: int = 10
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Rule Engine 이슈를 Flash Lite로 빠르게 검증

    Args:
        rule_issues: Rule Engine에서 감지된 이슈 리스트
        parsed_lines: 파싱된 G-code 라인
        context_lines: 앞뒤로 보여줄 라인 수

    Returns:
        (validated_issues, filtered_issues, token_usage)
        - validated_issues: 검증 통과한 이슈
        - filtered_issues: 오탐으로 판단되어 필터링된 이슈
        - token_usage: 토큰 사용량
    """
    if not rule_issues:
        return [], [], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    llm = get_llm_client_lite()
    validated = []
    filtered = []
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 라인 인덱스로 빠른 조회
    line_map = {line.index: line for line in parsed_lines}

    for issue in rule_issues:
        line_index = issue.get("event_line_index") or issue.get("line_index") or issue.get("line", 0)

        # G-code 스니펫 추출
        start_line = max(1, line_index - context_lines)
        end_line = min(len(parsed_lines), line_index + context_lines)

        snippet_lines = []
        for i in range(start_line, end_line + 1):
            if i in line_map:
                line = line_map[i]
                marker = " >>> " if i == line_index else "     "
                snippet_lines.append(f"{marker}{i}: {line.raw}")

        gcode_snippet = "\n".join(snippet_lines)

        # 프롬프트 생성
        prompt = VALIDATION_PROMPT.format(
            rule_name=issue.get("rule_name", "unknown"),
            severity=issue.get("severity", "unknown"),
            line_index=line_index,
            message=issue.get("description", issue.get("message", "")),
            start_line=start_line,
            end_line=end_line,
            gcode_snippet=gcode_snippet,
            context=json.dumps(issue.get("context", {}), ensure_ascii=False)
        )

        try:
            response = await llm.ainvoke(prompt)
            output_text = response.content if hasattr(response, 'content') else str(response)

            # 토큰 추정
            input_tokens = len(prompt) // 4
            output_tokens = len(output_text) // 4
            total_tokens["input_tokens"] += input_tokens
            total_tokens["output_tokens"] += output_tokens

            # JSON 파싱
            json_text = output_text
            if "```json" in output_text:
                json_text = output_text.split("```json")[1].split("```")[0]
            elif "```" in output_text:
                json_text = output_text.split("```")[1].split("```")[0]

            result = json.loads(json_text.strip())

            if result.get("is_valid_issue", True):
                # 검증 통과 - 이슈에 검증 정보 추가
                issue["llm_validated"] = True
                issue["validation_confidence"] = result.get("confidence", 1.0)
                issue["validation_reason"] = result.get("reason", "")
                validated.append(issue)
            else:
                # 오탐으로 판단
                issue["llm_validated"] = False
                issue["validation_confidence"] = result.get("confidence", 0.0)
                issue["validation_reason"] = result.get("reason", "")
                filtered.append(issue)

        except Exception as e:
            # 검증 실패 시 안전하게 이슈 유지
            issue["llm_validated"] = True
            issue["validation_error"] = str(e)
            validated.append(issue)

    total_tokens["total_tokens"] = total_tokens["input_tokens"] + total_tokens["output_tokens"]

    return validated, filtered, total_tokens
