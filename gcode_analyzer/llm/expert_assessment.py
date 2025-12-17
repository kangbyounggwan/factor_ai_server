"""
Expert Assessment Execution Module
Flash 모델을 사용하여 빠른 최종 평가 생성
"""
import json
from typing import Dict, Any, List, Tuple, Optional, Callable
from .client import get_llm_client
from .expert_assessment_prompt import EXPERT_ASSESSMENT_PROMPT
from .language import get_language_instruction

# 스트리밍 콜백 타입
StreamingCallback = Callable[[str], None]


async def generate_expert_assessment(
    summary_info: Dict[str, Any],
    issues: List[Dict[str, Any]],
    streaming_callback: Optional[StreamingCallback] = None,
    language: str = "ko"
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    모든 분석 정보를 바탕으로 정답지(Expert Assessment) 생성
    Flash 모델 사용 (빠른 응답)
    """
    llm = get_llm_client(max_output_tokens=2048)
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 1. 이슈 최적화 (Snippet Context 제거 등)
    optimized_issues = []
    for issue in issues:
        # 꼭 필요한 정보만 복사
        # Line number extraction (check various keys)
        line_num = issue.get("line") or issue.get("line_index") or issue.get("event_line_index")

        # autofix_allowed 확인 (기본값 True)
        autofix_allowed = issue.get("autofix_allowed", True)

        opt_issue = {
            "line": line_num,
            "event_type": issue.get("event_type") or issue.get("issue_type"),
            "title": issue.get("title"),
            "description": issue.get("description"),
            "severity": issue.get("severity"),
            "recommendation": issue.get("recommendation") or issue.get("suggestion"),
            "autofix_allowed": autofix_allowed  # 수동 검토 필요 여부
        }
        optimized_issues.append(opt_issue)

    issues_json = json.dumps(optimized_issues, indent=2, ensure_ascii=False)
    
    # 2. 요약 정보 최적화 (Whitelist 방식)
    # 필요한 통계 정보만 명시적으로 포함
    
    # 온도 통계만 추출
    temp_stats = {}
    if "temperature" in summary_info:
        raw_temp = summary_info["temperature"]
        temp_stats = {
            "nozzle_min": raw_temp.get("nozzle_min"),
            "nozzle_max": raw_temp.get("nozzle_max"),
            "nozzle_avg": raw_temp.get("nozzle_avg"),
            "nozzle_changes": raw_temp.get("nozzle_changes"),
            "bed_min": raw_temp.get("bed_min"),
            "bed_max": raw_temp.get("bed_max")
        }
    
    # 속도 통계만 추출
    feed_stats = {}
    if "feed_rate" in summary_info:
        raw_feed = summary_info["feed_rate"]
        feed_stats = {
            "min_speed": raw_feed.get("min_speed"),
            "max_speed": raw_feed.get("max_speed"),
            "avg_speed": raw_feed.get("avg_speed"),
            "print_speed_avg": raw_feed.get("print_speed_avg"),
            "travel_speed_avg": raw_feed.get("travel_speed_avg")
        }

    # 기본 정보
    optimized_summary = {
        "file_name": summary_info.get("file_name"),
        "total_lines": summary_info.get("total_lines"),
        "filament_type": summary_info.get("filament_type"),
        "slicer_info": summary_info.get("slicer_info"),
        "temperature": temp_stats,
        "feed_rate": feed_stats,
        "extrusion": {
            "total_filament_used": summary_info.get("extrusion", {}).get("total_filament_used"),
            "retraction_count": summary_info.get("extrusion", {}).get("retraction_count"),
            "avg_retraction": summary_info.get("extrusion", {}).get("avg_retraction")
        },
        "layer": {
            "total_layers": summary_info.get("layer", {}).get("total_layers"),
            "avg_layer_height": summary_info.get("layer", {}).get("avg_layer_height")
        },
        "print_time": {
            "formatted_time": summary_info.get("print_time", {}).get("formatted_time")
        },
        "support": {
            "has_support": summary_info.get("support", {}).get("has_support"),
            "support_ratio": summary_info.get("support", {}).get("support_ratio")
        }
    }

    summary_json = json.dumps(optimized_summary, indent=2, ensure_ascii=False)

    # 프롬프트 구성
    input_data = {
        "summary_info": summary_json,
        "issues_json": issues_json
    }
    
    prompt_text = EXPERT_ASSESSMENT_PROMPT.format(**input_data)
    
    # 언어 설정
    language_instruction = get_language_instruction(language)
    prompt_text = f"{language_instruction}\n\n{prompt_text}"

    # 입력 토큰 추정
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
            
            # 메타데이터 추출
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
        
        result_dict = json.loads(json_text.strip())
        
        return result_dict, token_usage

    except Exception as e:
        # 실패 시 기본값 반환
        return {
            "quality_score": 0,
            "quality_grade": "F",
            "print_characteristics": {
                "complexity": "Unknown",
                "difficulty": "Unknown",
                "tags": []
            },
            "summary_text": f"분석 중 오류가 발생했습니다: {str(e)}",
            "check_points": {},
            "critical_issues": [],
            "overall_recommendations": ["시스템 오류로 분석을 완료할 수 없습니다."]
        }, token_usage
