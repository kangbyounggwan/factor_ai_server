"""
LLM Issue Detector - Flash Lite를 사용한 직접 문제 탐지
Rule Engine은 데이터만 추출하고, 실제 문제 탐지는 LLM이 수행

3가지 분석 단계:
1. 온도 분석 (Temperature Analysis)
2. 속도/동작 분석 (Motion Analysis)
3. 구조/시퀀스 분석 (Structure Analysis)
"""
import json
import asyncio
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, asdict
from .client import get_llm_client_lite


# ============================================================
# 프롬프트 정의
# ============================================================

TEMPERATURE_ANALYSIS_PROMPT = """당신은 3D 프린터 G-code 온도 분석 전문가입니다.
제공된 온도 데이터를 분석하여 실제 문제가 될 수 있는 이슈를 찾아주세요.

## 온도 데이터
### 노즐 온도 설정 이력
{nozzle_temps}

### 베드 온도 설정 이력
{bed_temps}

### BODY 구간 내 온도 변화
{body_temp_changes}

### 기본 정보
- 필라멘트 타입: {filament_type}
- 첫 압출 라인: {first_extrusion_line}
- 구간 정보: START(1~{start_end}), BODY({start_end}~{body_end}), END({body_end}~{total_lines})

## 분석 기준
1. **콜드 익스트루전**: 익스트루전 전 온도가 충분한가? (PLA: 180+, ABS: 220+, PETG: 210+)
2. **온도 대기 누락**: M104 후 M109 없이 바로 압출하는가?
3. **BODY 내 온도 0**: 출력 중 온도가 0으로 설정되는가? (H 파라미터 확인)
4. **급격한 온도 변화**: 50°C 이상 급변이 있는가?
5. **베드 온도 누락**: 베드 온도 설정이 없는가?

## 응답 형식 (JSON)
```json
{{
  "issues": [
    {{
      "type": "cold_extrusion | temp_wait_missing | temp_zero | rapid_temp_change | no_bed_temp",
      "severity": "critical | high | medium | low",
      "line": 라인번호,
      "description": "문제 설명 (50자 이내)",
      "evidence": "근거 (예: M104 S0 at line 500)",
      "fix": "수정 방법"
    }}
  ],
  "summary": "온도 설정 전반에 대한 한 줄 평가"
}}
```

**중요**: 실제 문제만 보고하세요. 정상적인 패턴은 이슈로 보고하지 마세요.
- H 파라미터가 있는 M109 S0은 정상 (Bambu/Orca 확장)
- END 구간의 온도 0 설정은 정상
- START 구간의 예열 대기는 정상

JSON만 응답:
"""

MOTION_ANALYSIS_PROMPT = """당신은 3D 프린터 G-code 동작 분석 전문가입니다.
제공된 속도/동작 데이터를 분석하여 문제를 찾아주세요.

## 속도 데이터
{speed_stats}

### 속도 범위
- 최소: {min_speed} mm/s
- 최대: {max_speed} mm/s
- 평균: {avg_speed} mm/s
- 출력 평균: {print_speed} mm/s
- 이동 평균: {travel_speed} mm/s

### 익스트루전 정보
- 첫 익스트루전: 라인 {first_extrusion}
- 마지막 익스트루전: 라인 {last_extrusion}
- 온도 대기 전 익스트루전: {extrusion_before_wait}

## 분석 기준
1. **과속**: 출력 속도 300+ mm/s는 품질 저하 위험
2. **극저속**: 5 mm/s 미만은 비정상
3. **속도 미설정**: F 값 없이 익스트루전
4. **급격한 가감속**: 출력 중 200+ mm/s 급변

## 응답 형식 (JSON)
```json
{{
  "issues": [
    {{
      "type": "excessive_speed | too_slow | no_feed_rate | rapid_accel",
      "severity": "critical | high | medium | low",
      "line": 라인번호 (있으면),
      "description": "문제 설명",
      "evidence": "근거",
      "fix": "수정 방법"
    }}
  ],
  "summary": "속도 설정 전반에 대한 한 줄 평가"
}}
```

JSON만 응답:
"""

STRUCTURE_ANALYSIS_PROMPT = """당신은 3D 프린터 G-code 구조 분석 전문가입니다.
G-code 전체 구조와 시퀀스를 분석하여 문제를 찾아주세요.

## 구조 정보
- 총 라인 수: {total_lines}
- START 구간: 1 ~ {start_end} ({start_ratio}%)
- BODY 구간: {start_end} ~ {body_end} ({body_ratio}%)
- END 구간: {body_end} ~ {total_lines} ({end_ratio}%)

### 기본 체크 결과
{basic_checks}

### 온도 이벤트 수
- 노즐 온도 명령: {nozzle_count}회
- 베드 온도 명령: {bed_count}회
- BODY 내 온도 변경: {body_temp_count}회

## 분석 기준
1. **구간 비율 이상**: START가 50% 이상이면 비정상
2. **END 코드 누락**: END 구간이 없거나 너무 짧음
3. **BODY 내 과도한 온도 명령**: 10회 이상이면 확인 필요
4. **필수 설정 누락**: 기본 체크 실패 항목

## 응답 형식 (JSON)
```json
{{
  "issues": [
    {{
      "type": "structure_abnormal | missing_end | excessive_body_temp | missing_setup",
      "severity": "critical | high | medium | low",
      "line": 라인번호 (있으면),
      "description": "문제 설명",
      "evidence": "근거",
      "fix": "수정 방법"
    }}
  ],
  "summary": "G-code 구조 전반에 대한 한 줄 평가"
}}
```

JSON만 응답:
"""


# ============================================================
# 분석 결과 타입
# ============================================================
@dataclass
class DetectedIssue:
    """LLM이 탐지한 이슈"""
    type: str
    severity: str
    line: Optional[int]
    description: str
    evidence: str
    fix: str
    source: str  # temperature, motion, structure


@dataclass
class AnalysisResult:
    """분석 결과"""
    issues: List[DetectedIssue]
    summaries: Dict[str, str]
    token_usage: Dict[str, int]


# ============================================================
# 분석 함수들
# ============================================================
async def analyze_temperature(
    extracted_data: Dict[str, Any],
    filament_type: str = "PLA"
) -> Tuple[List[DetectedIssue], str, Dict[str, int]]:
    """온도 분석"""
    llm = get_llm_client_lite(max_output_tokens=1024)
    tokens = {"input": 0, "output": 0}

    # 프롬프트 구성
    nozzle_temps = extracted_data.get("nozzle_temps", [])
    bed_temps = extracted_data.get("bed_temps", [])
    body_changes = extracted_data.get("temp_changes_in_body", [])
    section_info = extracted_data.get("section_info", {})

    prompt = TEMPERATURE_ANALYSIS_PROMPT.format(
        nozzle_temps=json.dumps(nozzle_temps[:20], ensure_ascii=False),  # 최대 20개
        bed_temps=json.dumps(bed_temps[:10], ensure_ascii=False),
        body_temp_changes=json.dumps(body_changes[:15], ensure_ascii=False),
        filament_type=filament_type,
        first_extrusion_line=extracted_data.get("first_extrusion_line", "없음"),
        start_end=section_info.get("start_end", 0),
        body_end=section_info.get("body_end", 0),
        total_lines=section_info.get("total_lines", 0)
    )

    tokens["input"] = len(prompt) // 4

    try:
        response = await llm.ainvoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        tokens["output"] = len(output) // 4

        # JSON 파싱
        result = _parse_json_response(output)
        issues = []
        for item in result.get("issues", []):
            issues.append(DetectedIssue(
                type=item.get("type", "unknown"),
                severity=item.get("severity", "medium"),
                line=item.get("line"),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                fix=item.get("fix", ""),
                source="temperature"
            ))

        return issues, result.get("summary", ""), tokens

    except Exception as e:
        return [], f"분석 실패: {str(e)}", tokens


async def analyze_motion(
    extracted_data: Dict[str, Any]
) -> Tuple[List[DetectedIssue], str, Dict[str, int]]:
    """속도/동작 분석"""
    llm = get_llm_client_lite(max_output_tokens=1024)
    tokens = {"input": 0, "output": 0}

    speed_stats = extracted_data.get("speed_stats", {})

    prompt = MOTION_ANALYSIS_PROMPT.format(
        speed_stats=json.dumps(speed_stats, ensure_ascii=False),
        min_speed=speed_stats.get("min_mms", 0),
        max_speed=speed_stats.get("max_mms", 0),
        avg_speed=speed_stats.get("avg_mms", 0),
        print_speed=speed_stats.get("print_avg_mms", 0),
        travel_speed=speed_stats.get("travel_avg_mms", 0),
        first_extrusion=extracted_data.get("first_extrusion_line", "없음"),
        last_extrusion=extracted_data.get("last_extrusion_line", "없음"),
        extrusion_before_wait=extracted_data.get("extrusion_before_temp_wait", False)
    )

    tokens["input"] = len(prompt) // 4

    try:
        response = await llm.ainvoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        tokens["output"] = len(output) // 4

        result = _parse_json_response(output)
        issues = []
        for item in result.get("issues", []):
            issues.append(DetectedIssue(
                type=item.get("type", "unknown"),
                severity=item.get("severity", "medium"),
                line=item.get("line"),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                fix=item.get("fix", ""),
                source="motion"
            ))

        return issues, result.get("summary", ""), tokens

    except Exception as e:
        return [], f"분석 실패: {str(e)}", tokens


async def analyze_structure(
    extracted_data: Dict[str, Any],
    basic_checks: List[Dict[str, Any]]
) -> Tuple[List[DetectedIssue], str, Dict[str, int]]:
    """구조/시퀀스 분석"""
    llm = get_llm_client_lite(max_output_tokens=1024)
    tokens = {"input": 0, "output": 0}

    section_info = extracted_data.get("section_info", {})
    total = section_info.get("total_lines", 1)
    start_end = section_info.get("start_end", 0)
    body_end = section_info.get("body_end", 0)

    start_ratio = round(start_end / total * 100, 1) if total > 0 else 0
    body_ratio = round((body_end - start_end) / total * 100, 1) if total > 0 else 0
    end_ratio = round((total - body_end) / total * 100, 1) if total > 0 else 0

    # 기본 체크 결과 포맷
    checks_text = "\n".join([
        f"- {c.get('check_name', 'unknown')}: {'✓ 통과' if c.get('passed', False) else '✗ 실패'} - {c.get('message', '')}"
        for c in basic_checks
    ])

    prompt = STRUCTURE_ANALYSIS_PROMPT.format(
        total_lines=total,
        start_end=start_end,
        body_end=body_end,
        start_ratio=start_ratio,
        body_ratio=body_ratio,
        end_ratio=end_ratio,
        basic_checks=checks_text,
        nozzle_count=len(extracted_data.get("nozzle_temps", [])),
        bed_count=len(extracted_data.get("bed_temps", [])),
        body_temp_count=len(extracted_data.get("temp_changes_in_body", []))
    )

    tokens["input"] = len(prompt) // 4

    try:
        response = await llm.ainvoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        tokens["output"] = len(output) // 4

        result = _parse_json_response(output)
        issues = []
        for item in result.get("issues", []):
            issues.append(DetectedIssue(
                type=item.get("type", "unknown"),
                severity=item.get("severity", "medium"),
                line=item.get("line"),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                fix=item.get("fix", ""),
                source="structure"
            ))

        return issues, result.get("summary", ""), tokens

    except Exception as e:
        return [], f"분석 실패: {str(e)}", tokens


# ============================================================
# 메인 분석 함수
# ============================================================
async def detect_issues_with_llm(
    extracted_data: Dict[str, Any],
    basic_checks: List[Dict[str, Any]],
    filament_type: str = "PLA"
) -> AnalysisResult:
    """
    Flash Lite를 사용하여 3가지 관점에서 병렬 분석

    Args:
        extracted_data: rule_engine.extract_data_for_llm()의 결과
        basic_checks: 기본 체크 결과
        filament_type: 필라멘트 종류

    Returns:
        AnalysisResult: 탐지된 모든 이슈와 요약
    """
    # 3가지 분석을 병렬로 실행
    temp_task = analyze_temperature(extracted_data, filament_type)
    motion_task = analyze_motion(extracted_data)
    structure_task = analyze_structure(extracted_data, basic_checks)

    results = await asyncio.gather(temp_task, motion_task, structure_task)

    # 결과 수집
    all_issues = []
    summaries = {}
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    sources = ["temperature", "motion", "structure"]
    for i, (issues, summary, tokens) in enumerate(results):
        all_issues.extend(issues)
        summaries[sources[i]] = summary
        total_tokens["input_tokens"] += tokens.get("input", 0)
        total_tokens["output_tokens"] += tokens.get("output", 0)

    total_tokens["total_tokens"] = total_tokens["input_tokens"] + total_tokens["output_tokens"]

    # 중복 제거 (같은 라인의 같은 타입)
    unique_issues = _deduplicate_issues(all_issues)

    # 심각도 순 정렬
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique_issues.sort(key=lambda x: severity_order.get(x.severity, 4))

    return AnalysisResult(
        issues=unique_issues,
        summaries=summaries,
        token_usage=total_tokens
    )


def _parse_json_response(text: str) -> Dict[str, Any]:
    """LLM 응답에서 JSON 추출"""
    try:
        # ```json 블록 추출
        if "```json" in text:
            json_text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_text = text.split("```")[1].split("```")[0]
        else:
            json_text = text

        return json.loads(json_text.strip())
    except:
        return {"issues": [], "summary": "파싱 실패"}


def _deduplicate_issues(issues: List[DetectedIssue]) -> List[DetectedIssue]:
    """중복 이슈 제거"""
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.type, issue.line)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


# ============================================================
# 이슈를 기존 형식으로 변환 (하위 호환)
# ============================================================
def convert_to_legacy_format(issues: List[DetectedIssue]) -> List[Dict[str, Any]]:
    """DetectedIssue를 기존 이슈 형식으로 변환"""
    legacy_issues = []
    for i, issue in enumerate(issues):
        legacy_issues.append({
            "id": f"LLM-{i+1}",
            "has_issue": True,
            "issue_type": issue.type,
            "severity": issue.severity,
            "description": issue.description,
            "impact": issue.evidence,
            "suggestion": issue.fix,
            "affected_lines": [issue.line] if issue.line else [],
            "event_line_index": issue.line,
            "line": issue.line,
            "from_llm_detector": True,
            "source": issue.source,
            "autofix_allowed": issue.severity in ["critical", "high"]
        })
    return legacy_issues
