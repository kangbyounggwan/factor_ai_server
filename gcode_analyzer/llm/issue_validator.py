"""
Issue Validator - 룰 엔진 감지 이슈의 LLM 검증

룰 엔진에서 감지된 이슈가 실제 문제인지 오탐(false positive)인지 검증합니다.
주변 G-code 컨텍스트 (앞뒤 50줄)를 분석하여 최종 판정합니다.
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .client import get_llm_client_lite
from .language import get_language_instruction

logger = logging.getLogger(__name__)


ISSUE_VALIDATION_PROMPT = """당신은 3D 프린팅 G-code 전문가입니다.
아래 이슈가 실제 문제인지, 아니면 오탐(false positive)인지 판단해주세요.

## 감지된 이슈
- 유형: {issue_type}
- 라인: {line_number}
- 설명: {description}
- 심각도: {severity}

## G-code 컨텍스트 (문제 라인 주변 코드)
```gcode
{gcode_context}
```

## 🔧 제조사별 커스텀 코드 주의사항
다음 패턴은 **정상 코드**입니다. 오탐으로 판정해야 합니다:

1. **Bambu Lab / OrcaSlicer H-코드**:
   - `M104 S25 H220` → H=실제온도, S=대기시간 (정상)
   - `M109 S25 H220` → H=실제온도, S=대기시간 (정상)
   - `M104 H210` → H=실제온도 (정상)

2. **Klipper 매크로**:
   - `PRINT_START`, `SET_HEATER_TEMPERATURE` 등 → 정상

3. **온도 대기 순서**:
   - `M109 S220` (온도 설정 + 대기) 이후 압출 → 정상
   - M109가 M104보다 먼저 나와도, 압출 전에 대기했으면 → 정상

4. **END_GCODE 섹션**:
   - 출력 종료 후 `M104 S0` (온도 0)은 정상 종료 코드

## 판정 기준
- **실제 문제**: 압출 시점에 노즐 온도가 부족하거나, 출력 중에 비정상적으로 온도가 0이 되는 경우
- **오탐**: H-코드 사용, M109 대기 후 압출, END_GCODE에서 온도 0 설정 등

## 응답 형식 (JSON만)
{{
  "is_valid_issue": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "판정 이유 (100자 이내)",
  "corrected_severity": "critical|high|medium|low|info|none"
}}

JSON만 응답하세요:
"""


@dataclass
class ValidationResult:
    """검증 결과"""
    is_valid_issue: bool  # True: 실제 문제, False: 오탐
    confidence: float
    reasoning: str
    corrected_severity: str


async def validate_single_issue(
    issue: Dict[str, Any],
    gcode_context: str,
    language: str = "ko"
) -> Tuple[ValidationResult, Dict[str, int]]:
    """
    단일 이슈 검증

    Args:
        issue: 이슈 정보
        gcode_context: 주변 G-code (앞뒤 50줄)
        language: 응답 언어

    Returns:
        (ValidationResult, token_usage)
    """
    llm = get_llm_client_lite(max_output_tokens=512)

    issue_type = issue.get("issue_type") or issue.get("type", "unknown")
    line_number = issue.get("line") or issue.get("event_line_index", 0)
    description = issue.get("description", "")
    severity = issue.get("severity", "medium")

    prompt_text = ISSUE_VALIDATION_PROMPT.format(
        issue_type=issue_type,
        line_number=line_number,
        description=description,
        severity=severity,
        gcode_context=gcode_context
    )

    # 언어 설정
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    try:
        response = await llm.ainvoke(prompt_text)
        output_text = response.content if hasattr(response, 'content') else str(response)

        # 토큰 사용량
        if hasattr(response, 'usage_metadata'):
            tokens["input_tokens"] = getattr(response.usage_metadata, 'input_tokens', 0)
            tokens["output_tokens"] = getattr(response.usage_metadata, 'output_tokens', 0)
            tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]

        # JSON 파싱
        json_text = output_text
        if "```json" in output_text:
            json_text = output_text.split("```json")[1].split("```")[0]
        elif "```" in output_text:
            json_text = output_text.split("```")[1].split("```")[0]

        result_dict = json.loads(json_text.strip())

        return ValidationResult(
            is_valid_issue=result_dict.get("is_valid_issue", True),
            confidence=result_dict.get("confidence", 0.5),
            reasoning=result_dict.get("reasoning", ""),
            corrected_severity=result_dict.get("corrected_severity", severity)
        ), tokens

    except json.JSONDecodeError as e:
        logger.warning(f"[IssueValidator] JSON parse error: {e}")
        # 파싱 실패 시 원본 유지 (안전하게 실제 문제로 간주)
        return ValidationResult(
            is_valid_issue=True,
            confidence=0.5,
            reasoning="검증 응답 파싱 실패",
            corrected_severity=severity
        ), tokens

    except Exception as e:
        logger.error(f"[IssueValidator] Validation error: {e}")
        return ValidationResult(
            is_valid_issue=True,
            confidence=0.5,
            reasoning=f"검증 실패: {str(e)}",
            corrected_severity=severity
        ), tokens


def extract_context_for_validation(
    parsed_lines: list,
    line_number: int,
    context_lines: int = 50
) -> str:
    """
    검증용 G-code 컨텍스트 추출 (앞뒤 50줄)

    Args:
        parsed_lines: 파싱된 G-code 라인들
        line_number: 대상 라인 번호 (1-based)
        context_lines: 앞뒤로 포함할 라인 수

    Returns:
        라인 번호가 포함된 G-code 컨텍스트
    """
    if not line_number or not parsed_lines:
        return ""

    total_lines = len(parsed_lines)
    target_idx = line_number - 1  # 0-based

    start_idx = max(0, target_idx - context_lines)
    end_idx = min(total_lines, target_idx + context_lines + 1)

    context_parts = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = parsed_lines[i].raw.strip() if hasattr(parsed_lines[i], 'raw') else str(parsed_lines[i])

        if i == target_idx:
            context_parts.append(f">>> {line_num}: {line_content}  <<< [문제 라인]")
        else:
            context_parts.append(f"    {line_num}: {line_content}")

    return '\n'.join(context_parts)


async def validate_issues(
    issues: List[Dict[str, Any]],
    parsed_lines: list,
    language: str = "ko",
    context_lines: int = 50
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    여러 이슈를 LLM으로 검증하여 실제 문제만 필터링

    Args:
        issues: 검증할 이슈 목록
        parsed_lines: 파싱된 G-code 라인들
        language: 응답 언어
        context_lines: 컨텍스트 라인 수 (기본 50)

    Returns:
        (validated_issues, filtered_issues, total_tokens)
        - validated_issues: 실제 문제로 확인된 이슈
        - filtered_issues: 오탐으로 제거된 이슈
        - total_tokens: 총 토큰 사용량
    """
    if not issues:
        return [], [], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    validated_issues = []
    filtered_issues = []
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for issue in issues:
        line_number = issue.get("line") or issue.get("event_line_index")

        # 라인 번호가 없으면 검증 없이 통과 (안전하게 이슈 유지)
        if not line_number:
            validated_issues.append({
                **issue,
                "validation": {
                    "validated": True,
                    "confidence": 0.5,
                    "reasoning": "라인 번호 없음 - 검증 생략"
                }
            })
            continue

        # G-code 컨텍스트 추출
        gcode_context = extract_context_for_validation(parsed_lines, line_number, context_lines)

        # LLM 검증
        result, tokens = await validate_single_issue(issue, gcode_context, language)

        # 토큰 합산
        total_tokens["input_tokens"] += tokens["input_tokens"]
        total_tokens["output_tokens"] += tokens["output_tokens"]
        total_tokens["total_tokens"] += tokens["total_tokens"]

        if result.is_valid_issue:
            # 실제 문제: 심각도 수정 적용
            validated_issue = {
                **issue,
                "severity": result.corrected_severity if result.corrected_severity != "none" else issue.get("severity"),
                "validation": {
                    "validated": True,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning
                }
            }
            validated_issues.append(validated_issue)
            logger.info(f"[IssueValidator] Issue VALIDATED (line {line_number}): {result.reasoning}")
        else:
            # 오탐: 제거 목록에 추가
            filtered_issue = {
                **issue,
                "validation": {
                    "validated": False,
                    "is_false_positive": True,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning
                }
            }
            filtered_issues.append(filtered_issue)
            logger.info(f"[IssueValidator] Issue FILTERED as false positive (line {line_number}): {result.reasoning}")

    logger.info(
        f"[IssueValidator] Validation complete: "
        f"{len(validated_issues)} valid, {len(filtered_issues)} filtered"
    )

    return validated_issues, filtered_issues, total_tokens
