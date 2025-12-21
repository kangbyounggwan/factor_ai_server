"""
도구 분배기 - Intent에 따라 적절한 도구 호출
"""
import os
import base64
import uuid
import logging
from typing import List, Optional, Dict, Any

from .models import (
    ChatIntent, Attachment, AttachmentType, ToolResult, UserPlan,
    GCodeAnalysisParams, TroubleshootParams, ModellingParams,
    ConversationHistoryItem
)

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """
    Intent에 따라 적절한 도구로 라우팅

    각 도구는 기존 모듈을 래핑:
    - GCODE_ANALYSIS → gcode_analyzer.analyzer
    - TROUBLESHOOT → gcode_analyzer.troubleshoot
    - MODELLING_TEXT/IMAGE → modelling_api
    """

    def __init__(self, language: str = "ko", selected_model: Optional[str] = None):
        self.language = language
        self.selected_model = selected_model

    async def dispatch(
        self,
        intent: ChatIntent,
        message: str,
        attachments: Optional[List[Attachment]],
        user_id: str,
        user_plan: UserPlan,
        extracted_params: Dict[str, Any],
        printer_info: Optional[Dict[str, Any]] = None,
        filament_type: Optional[str] = None,
        conversation_history: Optional[List[ConversationHistoryItem]] = None,
        analysis_id: Optional[str] = None,
        issue_to_resolve: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        의도에 따라 적절한 도구 실행

        Args:
            intent: 분류된 의도
            message: 사용자 메시지
            attachments: 첨부 파일
            user_id: 사용자 ID
            user_plan: 사용자 플랜
            extracted_params: 추출된 파라미터
            printer_info: 프린터 정보
            filament_type: 필라멘트 타입
            analysis_id: G-code 분석 ID (이슈 해결 시)
            issue_to_resolve: 해결할 이슈 정보

        Returns:
            ToolResult: 도구 실행 결과
        """
        attachments = attachments or []

        try:
            if intent == ChatIntent.GCODE_ISSUE_RESOLVE:
                return await self._execute_issue_resolve(
                    analysis_id, issue_to_resolve
                )

            elif intent == ChatIntent.GCODE_ANALYSIS:
                return await self._execute_gcode_analysis(
                    attachments, user_id, printer_info, filament_type
                )

            elif intent == ChatIntent.GCODE_GENERAL:
                # 제너럴 모드: 세그먼트 분석 후 LLM 텍스트 답변만 (리포트 없음)
                return await self._execute_gcode_general(
                    message, attachments, printer_info, filament_type
                )

            elif intent == ChatIntent.TROUBLESHOOT:
                return await self._execute_troubleshoot(
                    message, attachments, user_plan, printer_info, filament_type
                )

            elif intent == ChatIntent.MODELLING_TEXT:
                prompt = extracted_params.get("prompt", message)
                return await self._execute_modelling_text(prompt, user_id)

            elif intent == ChatIntent.MODELLING_IMAGE:
                prompt = extracted_params.get("prompt", message)
                return await self._execute_modelling_image(
                    prompt, attachments, user_id
                )

            elif intent == ChatIntent.GENERAL_QUESTION:
                return await self._execute_general_qa(message, conversation_history)

            elif intent == ChatIntent.GREETING:
                return ToolResult(
                    tool_name="greeting",
                    success=True,
                    data={"type": "greeting"}
                )

            elif intent == ChatIntent.HELP:
                return ToolResult(
                    tool_name="help",
                    success=True,
                    data={"type": "help"}
                )

            else:
                return ToolResult(
                    tool_name="unknown",
                    success=False,
                    error=f"Unknown intent: {intent}"
                )

        except Exception as e:
            logger.error(f"Tool dispatch failed: {e}", exc_info=True)
            return ToolResult(
                tool_name=intent.value,
                success=False,
                error=str(e)
            )

    async def _execute_gcode_general(
        self,
        message: str,
        attachments: List[Attachment],
        printer_info: Optional[Dict[str, Any]],
        filament_type: Optional[str]
    ) -> ToolResult:
        """
        G-code 제너럴 모드: 세그먼트 분석 후 LLM 텍스트 답변만 (리포트 없음)

        도구 선택 없이 G-code 파일을 첨부한 경우:
        - 세그먼트 추출 (파싱, 요약)
        - LLM이 분석 데이터를 바탕으로 텍스트 답변 생성
        - 리포트/스트림 URL 없음
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        from ..llm.client import get_llm_by_model
        from ..parser import parse_gcode_from_string
        from ..summary import summarize_gcode
        from ..temp_tracker import extract_temp_events
        from ..section_detector import detect_sections

        # G-code 파일 찾기
        gcode_attachment = next(
            (a for a in attachments if a.type == AttachmentType.GCODE),
            None
        )

        if not gcode_attachment:
            return ToolResult(
                tool_name="gcode_general",
                success=False,
                error="G-code 파일이 첨부되지 않았습니다."
            )

        # base64 디코딩
        try:
            gcode_content = base64.b64decode(gcode_attachment.content).decode('utf-8')
        except Exception as e:
            return ToolResult(
                tool_name="gcode_general",
                success=False,
                error=f"G-code 파일 디코딩 실패: {e}"
            )

        filename = gcode_attachment.filename or "uploaded.gcode"

        try:
            # 1. 파싱 및 요약 (세그먼트 분석)
            parse_result = parse_gcode_from_string(gcode_content)
            parsed_lines = parse_result.lines
            summary = summarize_gcode(parsed_lines)
            boundaries = detect_sections(parsed_lines)
            temp_events = extract_temp_events(parsed_lines)

            # 2. 분석 데이터 구성
            analysis_data = {
                "filename": filename,
                "total_lines": len(parsed_lines),
                "layer_count": summary.total_layers,
                "layer_height": summary.layer_height,
                "estimated_time": summary.estimated_print_time,
                "temperature": {
                    "nozzle_min": summary.nozzle_temp_min,
                    "nozzle_max": summary.nozzle_temp_max,
                    "bed_min": summary.bed_temp_min,
                    "bed_max": summary.bed_temp_max,
                    "nozzle_events": len([e for e in temp_events if e.cmd in ["M104", "M109"]]),
                    "bed_events": len([e for e in temp_events if e.cmd in ["M140", "M190"]])
                },
                "sections": {
                    "start_end": boundaries.start_end,
                    "body_end": boundaries.body_end,
                    "total_lines": boundaries.total_lines
                },
                "speed": {
                    "max": summary.max_speed,
                    "avg": summary.avg_speed
                },
                "retraction_count": summary.retraction_count,
                "printer_info": printer_info,
                "filament_type": filament_type or summary.filament_type or "unknown"
            }

            # 3. LLM 텍스트 답변 생성
            model_name = self.selected_model or "gemini-2.5-flash-lite"
            llm = get_llm_by_model(
                model_name=model_name,
                temperature=0.3,
                max_output_tokens=2048
            )

            system_prompt = """당신은 3D 프린팅 G-code 전문가입니다.
사용자가 G-code 파일을 첨부하고 질문했습니다.
아래 분석 데이터를 바탕으로 사용자의 질문에 답변해주세요.

## 분석 데이터
{analysis_data}

## 응답 지침
1. 사용자 질문에 맞는 정보만 제공하세요
2. 데이터에 없는 정보는 추측하지 마세요
3. 마크다운 형식으로 깔끔하게 정리해주세요
4. 필요시 개선 제안이나 주의사항을 추가해주세요

## 마크다운 포맷팅 규칙
- 제목은 ### 사용
- 리스트는 - 또는 1. 사용
- 중요 정보는 **볼드** 처리
- 구분선은 --- 사용"""

            import json
            formatted_prompt = system_prompt.format(
                analysis_data=json.dumps(analysis_data, indent=2, ensure_ascii=False)
            )

            messages = [
                SystemMessage(content=formatted_prompt),
                HumanMessage(content=message)
            ]

            response = await llm.ainvoke(messages)

            return ToolResult(
                tool_name="gcode_general",
                success=True,
                data={
                    "answer": response.content,
                    "analysis_summary": analysis_data,
                    "filename": filename
                }
            )

        except Exception as e:
            logger.error(f"G-code general analysis failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="gcode_general",
                success=False,
                error=f"G-code 분석 실패: {str(e)}"
            )

    async def _execute_gcode_analysis(
        self,
        attachments: List[Attachment],
        user_id: str,
        printer_info: Optional[Dict[str, Any]],
        filament_type: Optional[str]
    ) -> ToolResult:
        """
        G-code 분석 실행 (Chat API 통합)

        세그먼트 추출 + LLM 분석을 내부 함수로 직접 호출하여
        단일 Chat API 요청으로 처리합니다.

        Returns:
            ToolResult: 세그먼트 데이터 + analysis_id 포함
        """
        # G-code 파일 찾기
        gcode_attachment = next(
            (a for a in attachments if a.type == AttachmentType.GCODE),
            None
        )

        if not gcode_attachment:
            return ToolResult(
                tool_name="gcode_analysis",
                success=False,
                error="G-code 파일이 첨부되지 않았습니다."
            )

        # base64 디코딩
        try:
            gcode_content = base64.b64decode(gcode_attachment.content).decode('utf-8')
        except Exception as e:
            return ToolResult(
                tool_name="gcode_analysis",
                success=False,
                error=f"G-code 파일 디코딩 실패: {e}"
            )

        filename = gcode_attachment.filename or f"temp_{uuid.uuid4().hex[:8]}.gcode"

        try:
            # 내부 함수 직접 호출 (세그먼트 추출 + 백그라운드 LLM 분석)
            from ..api.router import process_gcode_analysis_internal

            result = await process_gcode_analysis_internal(
                gcode_content=gcode_content,
                user_id=user_id,
                printer_info=printer_info,
                filament_type=filament_type,
                language=self.language
            )

            return ToolResult(
                tool_name="gcode_analysis",
                success=True,
                data={
                    "analysis_id": result.analysis_id,
                    "status": result.status,
                    "segments": result.segments,
                    "layer_count": result.layer_count,
                    "filename": filename,
                    "message": result.message
                },
                # 최상위 레벨에도 노출 (편의용)
                analysis_id=result.analysis_id,
                segments=result.segments
            )

        except ValueError as e:
            # 인코딩/추출 오류
            logger.error(f"G-code analysis failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="gcode_analysis",
                success=False,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"G-code analysis failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="gcode_analysis",
                success=False,
                error=f"G-code 분석 실패: {str(e)}"
            )

    async def _execute_troubleshoot(
        self,
        message: str,
        attachments: List[Attachment],
        user_plan: UserPlan,
        printer_info: Optional[Dict[str, Any]],
        filament_type: Optional[str]
    ) -> ToolResult:
        """문제 진단 실행"""
        from ..troubleshoot.image_analyzer import ImageAnalyzer
        from ..troubleshoot.web_searcher import WebSearcher
        from ..troubleshoot.solution_generator import SolutionGenerator
        from ..troubleshoot.models import ProblemType, UserPlan as TroubleshootUserPlan

        # 이미지 추출
        images = []
        for attachment in attachments:
            if attachment.type == AttachmentType.IMAGE:
                images.append(attachment.content)

        # 프린터 정보 추출
        manufacturer = printer_info.get("manufacturer") if printer_info else None
        model = printer_info.get("model") if printer_info else None

        # UserPlan 매핑
        plan_mapping = {
            UserPlan.FREE: TroubleshootUserPlan.FREE,
            UserPlan.STARTER: TroubleshootUserPlan.STARTER,
            UserPlan.PRO: TroubleshootUserPlan.PRO,
            UserPlan.ENTERPRISE: TroubleshootUserPlan.ENTERPRISE,
        }
        troubleshoot_plan = plan_mapping.get(user_plan, TroubleshootUserPlan.FREE)

        try:
            # 1. 이미지 분석 (있는 경우)
            image_analysis = None
            if images:
                analyzer = ImageAnalyzer(language=self.language)
                image_analysis = await analyzer.analyze_images(images)

            # 2. 문제 유형 및 구체적 증상 결정
            if image_analysis and image_analysis.detected_problems:
                problem_type = image_analysis.detected_problems[0]
            else:
                problem_type = ProblemType.UNKNOWN

            # 이미지 분석에서 추출한 구체적 정보 활용
            enhanced_symptom = message
            if image_analysis:
                # 이미지 분석 설명 추가
                if image_analysis.description:
                    enhanced_symptom = f"{message}. {image_analysis.description}"

            # 3. 웹 검색 (플랜에 따라 분기)
            searcher = WebSearcher(language=self.language, user_plan=troubleshoot_plan)
            search_results = await searcher.search(
                manufacturer=manufacturer,
                model=model,
                problem_type=problem_type,
                symptom_text=enhanced_symptom
            )

            # 4. 솔루션 생성
            generator = SolutionGenerator(language=self.language)
            solution_data = await generator.generate_solution(
                manufacturer=manufacturer,
                model=model,
                symptom_text=message,
                image_analysis=image_analysis,
                search_results=search_results,
                filament_type=filament_type
            )

            # 참조 자료 추출 (각 검색 결과에서 최대 5개씩)
            references = []
            for result in search_results:
                for ref in result.results[:5]:
                    references.append({
                        "title": ref.title,
                        "url": ref.url,
                        "source": ref.source,
                        "snippet": ref.snippet
                    })

            # 참조자료 제목 → URL 매핑 생성 (부분 매칭 지원)
            ref_url_map = {ref["title"]: ref["url"] for ref in references}

            def find_best_url(source_ref_title: str) -> str:
                """source_ref 제목과 가장 잘 매칭되는 참조자료 URL 찾기"""
                # 정확한 매칭
                if source_ref_title in ref_url_map:
                    return ref_url_map[source_ref_title]

                # 부분 매칭: source_ref 제목이 참조자료 제목에 포함되어 있는 경우
                source_lower = source_ref_title.lower()
                for ref_title, url in ref_url_map.items():
                    ref_lower = ref_title.lower()
                    # 양방향 부분 매칭
                    if source_lower in ref_lower or ref_lower in source_lower:
                        return url
                    # 핵심 단어 매칭 (3단어 이상 일치)
                    source_words = set(source_lower.split())
                    ref_words = set(ref_lower.split())
                    common_words = source_words & ref_words
                    if len(common_words) >= 3:
                        return url

                return ""

            return ToolResult(
                tool_name="troubleshoot",
                success=True,
                data={
                    "problem": {
                        "type": solution_data["problem"].type.value,
                        "confidence": solution_data["problem"].confidence,
                        "description": solution_data["problem"].description
                    },
                    "solutions": [
                        {
                            "title": s.title,
                            "steps": s.steps,
                            "difficulty": s.difficulty.value,
                            "estimated_time": s.estimated_time,
                            "source_refs": [
                                {"title": ref, "url": find_best_url(ref)}
                                for ref in (s.source_refs or [])
                            ] if s.source_refs else None
                        }
                        for s in solution_data["solutions"]
                    ],
                    "expert_opinion": {
                        "summary": solution_data["expert_opinion"].summary,
                        "prevention_tips": solution_data["expert_opinion"].prevention_tips,
                        "source_refs": [
                            {"title": ref, "url": find_best_url(ref)}
                            for ref in (solution_data["expert_opinion"].source_refs or [])
                        ] if solution_data["expert_opinion"].source_refs else None
                    },
                    "references": references[:10]
                }
            )

        except Exception as e:
            logger.error(f"Troubleshoot failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="troubleshoot",
                success=False,
                error=str(e)
            )

    async def _execute_modelling_text(
        self,
        prompt: str,
        user_id: str
    ) -> ToolResult:
        """Text-to-3D 실행"""
        try:
            # modelling_api 임포트
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

            from modelling_api import run_text_to_3d

            result = await run_text_to_3d(
                prompt=prompt,
                user_id=user_id,
                quality="medium"
            )

            return ToolResult(
                tool_name="modelling_text",
                success=True,
                data={
                    "task_id": result.get("task_id"),
                    "model_id": result.get("model_id"),
                    "status": result.get("status", "processing"),
                    "glb_url": result.get("result_glb_url") or result.get("supabase_glb_url"),
                    "stl_url": result.get("supabase_stl_url"),
                    "thumbnail_url": result.get("supabase_thumbnail_url"),
                    "prompt": prompt
                }
            )

        except ImportError as e:
            logger.error(f"modelling_api import failed: {e}")
            return ToolResult(
                tool_name="modelling_text",
                success=False,
                error="3D 모델링 서비스를 사용할 수 없습니다."
            )
        except Exception as e:
            logger.error(f"Text-to-3D failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="modelling_text",
                success=False,
                error=str(e)
            )

    async def _execute_modelling_image(
        self,
        prompt: str,
        attachments: List[Attachment],
        user_id: str
    ) -> ToolResult:
        """Image-to-3D 실행"""
        # 이미지 찾기
        image_attachment = next(
            (a for a in attachments if a.type == AttachmentType.IMAGE),
            None
        )

        if not image_attachment:
            return ToolResult(
                tool_name="modelling_image",
                success=False,
                error="이미지가 첨부되지 않았습니다."
            )

        try:
            # modelling_api 임포트
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

            from modelling_api import run_image_to_3d

            # base64 이미지를 data URL로 변환
            mime_type = image_attachment.mime_type or "image/jpeg"
            image_data_url = f"data:{mime_type};base64,{image_attachment.content}"

            result = await run_image_to_3d(
                image_url=image_data_url,
                prompt=prompt,
                user_id=user_id
            )

            return ToolResult(
                tool_name="modelling_image",
                success=True,
                data={
                    "task_id": result.get("task_id"),
                    "model_id": result.get("model_id"),
                    "status": result.get("status", "processing"),
                    "glb_url": result.get("result_glb_url") or result.get("supabase_glb_url"),
                    "stl_url": result.get("supabase_stl_url"),
                    "thumbnail_url": result.get("supabase_thumbnail_url"),
                    "prompt": prompt
                }
            )

        except ImportError as e:
            logger.error(f"modelling_api import failed: {e}")
            return ToolResult(
                tool_name="modelling_image",
                success=False,
                error="3D 모델링 서비스를 사용할 수 없습니다."
            )
        except Exception as e:
            logger.error(f"Image-to-3D failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="modelling_image",
                success=False,
                error=str(e)
            )

    async def _execute_general_qa(
        self,
        message: str,
        conversation_history: Optional[List[ConversationHistoryItem]] = None
    ) -> ToolResult:
        """일반 질문 답변 (웹 검색 포함)"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        from ..llm.client import get_llm_by_model
        from ..troubleshoot.web_searcher import FreeSearchProvider

        # 1. 웹 검색 수행
        search_results_text = ""
        references = []

        try:
            free_search = FreeSearchProvider()

            # 3D 프린팅 관련 검색어로 변환
            search_query = f"3D printing {message}"
            search_results = await free_search.search(search_query)

            if search_results:
                search_results_text = "\n\n## 검색 결과\n"
                for i, ref in enumerate(search_results[:10], 1):
                    search_results_text += f"\n### [{i}] {ref.title}\n"
                    search_results_text += f"URL: {ref.url}\n"
                    if ref.snippet:
                        search_results_text += f"내용: {ref.snippet}\n"
                    references.append({
                        "title": ref.title,
                        "url": ref.url,
                        "source": ref.source,
                        "snippet": ref.snippet
                    })

                logger.info(f"General QA: Found {len(search_results)} search results")
            else:
                logger.info("General QA: No search results found")

        except Exception as e:
            logger.warning(f"General QA search failed: {e}")
            search_results_text = "\n\n(검색 결과를 가져오지 못했습니다)\n"

        # 2. LLM으로 답변 생성
        model_name = self.selected_model or "gemini-2.5-flash-lite"
        llm = get_llm_by_model(
            model_name=model_name,
            temperature=0.3,
            max_output_tokens=2048
        )

        system_prompt = f"""당신은 3D 프린팅 전문가입니다.
사용자의 질문에 친절하고 정확하게 답변해주세요.
답변은 간결하면서도 실용적인 정보를 포함해야 합니다.

{search_results_text}

## 중요 원칙
- 위 검색 결과를 참고하여 답변하세요.
- 검색 결과에 있는 정보를 우선적으로 활용하세요.
- 검색 결과에 없는 정보는 일반적인 3D 프린팅 지식으로 보완할 수 있습니다.
- 가격, 재고 등 실시간 정보는 검색 결과에 있는 경우에만 언급하세요.

## 마크다운 포맷팅 규칙 (반드시 준수)

1. **번호 리스트는 한 줄로 작성**
   - ❌ 잘못된 예: "1.\n\n**항목**"
   - ✅ 올바른 예: "1. **항목** - 설명"

2. **볼드 텍스트 안에 따옴표 넣지 않기**
   - ❌ 잘못된 예: **'습기 제거'**
   - ✅ 올바른 예: **습기 제거** 또는 '**습기 제거**'

3. **섹션 제목은 ### 사용 (볼드 대신)**
   - ❌ 잘못된 예: **왜 중요할까요?**
   - ✅ 올바른 예: ### 왜 중요할까요?

4. **섹션 사이에 구분선(---) 사용**

5. **리스트 항목은 줄바꿈 없이 한 줄로**
   - ❌ 잘못된 예: "- **장점:**\n\n매우 저렴한 가격..."
   - ✅ 올바른 예: "- **장점:** 매우 저렴한 가격..."

6. **권장 응답 구조**
```
# 제목

간단한 소개 문장.

### 섹션 1 제목

내용 설명...

- **항목 1:** 설명
- **항목 2:** 설명

---

### 섹션 2 제목

1. **첫 번째 추천** - 설명
2. **두 번째 추천** - 설명

---

> **Tip:** 추가 팁 내용
```"""

        try:
            # 메시지 리스트 구성
            messages = [SystemMessage(content=system_prompt)]

            # 대화 히스토리 추가 (있는 경우)
            if conversation_history:
                for item in conversation_history:
                    if item.role == "user":
                        messages.append(HumanMessage(content=item.content))
                    elif item.role == "assistant":
                        messages.append(AIMessage(content=item.content))

            # 현재 메시지 추가
            messages.append(HumanMessage(content=message))

            response = await llm.ainvoke(messages)

            return ToolResult(
                tool_name="general_qa",
                success=True,
                data={
                    "answer": response.content,
                    "references": references[:5] if references else None
                }
            )

        except Exception as e:
            logger.error(f"General QA failed: {e}")
            return ToolResult(
                tool_name="general_qa",
                success=False,
                error=str(e)
            )

    async def _execute_issue_resolve(
        self,
        analysis_id: Optional[str],
        issue: Optional[Dict[str, Any]]
    ) -> ToolResult:
        """
        G-code 이슈 해결 (AI 해결하기)

        Args:
            analysis_id: G-code 분석 ID
            issue: 해결할 이슈 정보

        Returns:
            ToolResult: 해결 방법 포함
        """
        if not issue:
            return ToolResult(
                tool_name="issue_resolve",
                success=False,
                error="해결할 이슈 정보가 없습니다."
            )

        try:
            from gcode_analyzer.llm.issue_resolver import resolve_issue, extract_gcode_context
            from gcode_analyzer.api.file_store import get_analysis, exists

            gcode_context = "(G-code 컨텍스트 없음)"
            summary_info = {}

            # analysis_id가 있으면 G-code 컨텍스트 추출
            if analysis_id and exists(analysis_id):
                data = get_analysis(analysis_id)
                if data:
                    # G-code 파일 읽기
                    temp_file = data.get("temp_file")
                    if temp_file:
                        try:
                            with open(temp_file, 'r', encoding='utf-8') as f:
                                gcode_content = f.read()
                            line_number = issue.get("line", 1)
                            gcode_context = extract_gcode_context(gcode_content, line_number, context_lines=15)
                        except Exception as e:
                            logger.warning(f"Failed to read G-code file: {e}")

                    # 요약 정보 추출
                    result_data = data.get("result", {})
                    summary_info = {
                        "temperature": result_data.get("summary", {}).get("temperature", {}),
                        "feed_rate": result_data.get("summary", {}).get("feed_rate", {}),
                        "filament_type": data.get("filament_type"),
                        "slicer_info": result_data.get("summary", {}).get("slicer_info", {})
                    }

            # LLM으로 이슈 해결
            resolution = await resolve_issue(
                issue=issue,
                gcode_context=gcode_context,
                summary_info=summary_info,
                language=self.language
            )

            return ToolResult(
                tool_name="issue_resolve",
                success=True,
                data={
                    "analysis_id": analysis_id,
                    "issue_line": issue.get("line"),
                    "issue_type": issue.get("type"),
                    "resolution": resolution
                }
            )

        except Exception as e:
            logger.error(f"Issue resolve failed: {e}", exc_info=True)
            return ToolResult(
                tool_name="issue_resolve",
                success=False,
                error=f"이슈 해결 실패: {str(e)}"
            )
