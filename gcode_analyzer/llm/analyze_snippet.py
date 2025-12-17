"""
LLM 스니펫 분석 실행 (토큰 추적 + 스트리밍 지원)
"""
import json
from typing import Dict, Any, Tuple, Optional, Callable
from .client import get_llm_client_lite
from .analyze_snippet_prompt import ANALYZE_SNIPPET_PROMPT
from .language import get_language_instruction
from ..data_preparer import LLMAnalysisInput
from langchain_core.output_parsers import JsonOutputParser

# 스트리밍 콜백 타입
StreamingCallback = Callable[[str], None]

async def analyze_snippet_with_llm(
    llm_input: LLMAnalysisInput,
    window: int = 50,
    streaming_callback: Optional[StreamingCallback] = None,
    language: str = "ko"
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    LLM을 사용하여 스니펫 분석
    
    Returns:
        Tuple[Dict, Dict]: (분석 결과, 토큰 사용량)
    """
    llm = get_llm_client_lite(max_output_tokens=1024)
    
    # 필라멘트 정보 포맷팅
    filament_info_str = "정보 없음"
    if llm_input.filament_info:
        fi = llm_input.filament_info
        filament_info_str = f"""
- 타입: {fi.get('name', 'Unknown')}
- 권장 노즐 온도: {fi.get('min_nozzle_temp', '?')}°C ~ {fi.get('max_nozzle_temp', '?')}°C
- 권장 베드 온도: {fi.get('min_bed_temp', '?')}°C ~ {fi.get('max_bed_temp', '?')}°C
"""

    # comprehensive_summary에서 상세 정보 추출
    comp_summary = llm_input.comprehensive_summary or {}
    temp_profile = comp_summary.get("temperature", {})
    feed_profile = comp_summary.get("feed_rate", {})
    ext_profile = comp_summary.get("extrusion", {})
    layer_profile = comp_summary.get("layer", {})
    support_profile = comp_summary.get("support", {})
    print_time = comp_summary.get("print_time", {})

    # 종합 요약 문자열 생성
    comprehensive_info_str = ""
    if comp_summary:
        comprehensive_info_str = f"""
=== 종합 요약 정보 ===
- 슬라이서: {comp_summary.get('slicer_info', '알 수 없음')}
- 총 라인: {comp_summary.get('total_lines', 0):,}줄
- 예상 출력 시간: {print_time.get('formatted_time', '알 수 없음')}

[온도 프로파일]
- 노즐: {temp_profile.get('nozzle_min', 0)}°C ~ {temp_profile.get('nozzle_max', 0)}°C (평균: {temp_profile.get('nozzle_avg', 0):.1f}°C)
- 베드: {temp_profile.get('bed_min', 0)}°C ~ {temp_profile.get('bed_max', 0)}°C
- 온도 변경 횟수: {temp_profile.get('nozzle_changes', 0)}회

[속도 정보]
- 속도 범위: {feed_profile.get('min_speed', 0):.0f} ~ {feed_profile.get('max_speed', 0):.0f} mm/min
- 평균 속도: {feed_profile.get('avg_speed', 0):.0f} mm/min
- 출력 속도: {feed_profile.get('print_speed_avg', 0):.0f} mm/min
- 이동 속도: {feed_profile.get('travel_speed_avg', 0):.0f} mm/min

[레이어 정보]
- 총 레이어: {layer_profile.get('total_layers', 0)}층
- 레이어 높이: {layer_profile.get('avg_layer_height', 0):.2f}mm

[익스트루전]
- 필라멘트 사용량: {ext_profile.get('total_filament_used', 0):.2f}m
- 리트랙션 횟수: {ext_profile.get('retraction_count', 0)}회
- 평균 리트랙션: {ext_profile.get('avg_retraction', 0):.2f}mm

[서포트]
- 서포트 사용: {'예' if support_profile.get('has_support', False) else '아니오'}
- 서포트 비율: {support_profile.get('support_ratio', 0):.1f}%
"""

    # 입력 데이터 준비
    input_data = {
        "total_layers": layer_profile.get("total_layers") or llm_input.summary.get("total_layers", 0),
        "layer_height": layer_profile.get("avg_layer_height") or llm_input.summary.get("layer_height", 0.2),
        "nozzle_temp_min": temp_profile.get("nozzle_min") or llm_input.summary.get("nozzle_temp_min", 0),
        "nozzle_temp_max": temp_profile.get("nozzle_max") or llm_input.summary.get("nozzle_temp_max", 0),
        "bed_temp_min": temp_profile.get("bed_min") or llm_input.summary.get("bed_temp_min", 0),
        "bed_temp_max": temp_profile.get("bed_max") or llm_input.summary.get("bed_temp_max", 0),
        "filament_info": filament_info_str,
        "comprehensive_info": comprehensive_info_str,  # 종합 요약 추가
        "event_line_index": llm_input.snippet_context.event_line_index,
        "event_cmd": llm_input.snippet_context.event_cmd,
        "event_temp": llm_input.snippet_context.event_temp,
        "lines_after_event": llm_input.snippet_context.lines_after_event,
        "window": window,
        "snippet_text": llm_input.snippet_context.snippet_text,
    }
    
    # 토큰 추정 (입력)
    prompt_text = ANALYZE_SNIPPET_PROMPT.format(**input_data)

    # 언어 지시문 추가
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    input_tokens_estimate = len(prompt_text) // 4  # 대략 4자 = 1토큰
    
    token_usage = {
        "input_tokens": input_tokens_estimate,
        "output_tokens": 0,
        "total_tokens": input_tokens_estimate
    }
    
    try:
        # 스트리밍 모드 vs 일반 모드
        if streaming_callback:
            # 스트리밍 모드: 청크 단위로 콜백 호출
            output_text = ""
            async for chunk in llm.astream(prompt_text):
                chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
                output_text += chunk_text
                # 콜백으로 실시간 전달
                streaming_callback(chunk_text)

            # 토큰 추정 (스트리밍에서는 메타데이터 접근 어려움)
            token_usage["output_tokens"] = len(output_text) // 4
            token_usage["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]
        else:
            # 일반 모드: 전체 응답 한번에
            response = await llm.ainvoke(prompt_text)

            # Gemini 응답에서 토큰 정보 추출 시도
            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if 'usage_metadata' in metadata:
                    usage = metadata['usage_metadata']
                    token_usage["input_tokens"] = usage.get('prompt_token_count', input_tokens_estimate)
                    token_usage["output_tokens"] = usage.get('candidates_token_count', 0)
                    token_usage["total_tokens"] = usage.get('total_token_count',
                        token_usage["input_tokens"] + token_usage["output_tokens"])

            output_text = response.content if hasattr(response, 'content') else str(response)

            # 출력 토큰 추정 (메타데이터 없으면)
            if token_usage["output_tokens"] == 0:
                token_usage["output_tokens"] = len(output_text) // 4
                token_usage["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]

        # JSON 파싱 (```json ... ``` 형식 처리)
        if "```json" in output_text:
            output_text = output_text.split("```json")[1].split("```")[0]
        elif "```" in output_text:
            output_text = output_text.split("```")[1].split("```")[0]

        result = json.loads(output_text.strip())
        return result, token_usage
        
    except Exception as e:
        return {
            "has_issue": False,
            "issue_type": "error",
            "severity": "none",
            "description": f"LLM 분석 중 오류 발생: {str(e)}",
            "impact": "",
            "suggestion": "",
            "affected_lines": []
        }, token_usage
