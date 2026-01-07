"""
응답 생성기 - 도구 결과를 자연어 응답으로 변환
"""
import logging
from typing import List

from .models import ChatIntent, ToolResult, SuggestedAction

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    도구 결과를 사용자 친화적인 응답으로 변환
    """

    def __init__(self, language: str = "ko"):
        self.language = language
        self._init_labels()

    def _init_labels(self):
        """언어별 레이블 초기화"""
        if self.language == "en":
            self.labels = {
                # 공통
                "error_sorry": "Sorry, there was a problem processing your request.",
                "retry": "Retry",
                "what_can_i_help": "How can I help you?",

                # G-code 분석
                "gcode_analysis_started": "G-code Analysis Started!",
                "file": "File",
                "status": "Status",
                "segments_ready_llm_analyzing": "Segments extracted, LLM analysis in progress...",
                "detected_info": "Detected Information",
                "total_layers": "Total layers",
                "extrusion_paths": "Extrusion paths",
                "travel_paths": "Travel paths",
                "viewer_hint": "You can view layers in the 3D viewer.",
                "analysis_complete_hint": "Once the detailed analysis is complete, I'll show you the quality score and issues!",
                "check_status": "Check Analysis Status",
                "explore_layers": "Explore Layers",

                # G-code 동기 분석
                "gcode_analysis_complete": "G-code Analysis Complete!",
                "quality_score": "Quality Score",
                "basic_info": "Basic Information",
                "estimated_print_time": "Estimated print time",
                "filament_usage": "Filament usage",
                "layer_height": "Layer height",
                "temperature_settings": "Temperature Settings",
                "nozzle": "Nozzle",
                "bed": "Bed",
                "issues_found": "Issues Found",
                "and_more": "... and {count} more",
                "view_detail": "View Detailed Analysis",
                "download_patched": "Download Patched G-code",
                "unknown": "Unknown",

                # 문제 진단
                "problem_analysis_result": "Problem Analysis Result",
                "detected_problem": "Detected Problem",
                "confidence": "Confidence",
                "recommended_solutions": "Recommended Solutions",
                "difficulty": "Difficulty",
                "estimated_time": "Est. time",
                "source": "Source",
                "expert_opinion": "Expert Opinion",
                "prevention_tips": "Prevention Tips",
                "references": "References",
                "detailed_diagnosis": "More Detailed Diagnosis",
                "new_troubleshoot": "Troubleshoot Another Issue",

                # 문제 유형
                "problem_types": {
                    "bed_adhesion": "First Layer Adhesion Issue",
                    "stringing": "Stringing/Oozing",
                    "warping": "Warping/Curling",
                    "layer_shifting": "Layer Shifting",
                    "under_extrusion": "Under-extrusion",
                    "over_extrusion": "Over-extrusion",
                    "clogging": "Nozzle Clogging",
                    "surface_quality": "Surface Quality Issue",
                    "ghosting": "Ghosting/Ringing",
                    "z_banding": "Z-Banding",
                    "blob": "Blobs/Zits",
                    "layer_separation": "Layer Separation",
                    "elephant_foot": "Elephant Foot",
                    "bridging_issue": "Bridging Issue",
                    "overhang_issue": "Overhang Issue",
                    "bed_leveling": "Bed Leveling Issue",
                    "nozzle_damage": "Nozzle Damage",
                    "extruder_skip": "Extruder Skipping",
                    "belt_tension": "Belt Tension Issue",
                    "heating_failure": "Heating Failure",
                    "unknown": "Unidentified Issue"
                },

                # 3D 모델링
                "model_generation_complete": "3D Model Generation Complete!",
                "model_generation_started": "3D Model Generation Started!",
                "type": "Type",
                "prompt": "Prompt",
                "model_success": "Model has been successfully generated!",
                "model_generating": "Generating your model... (takes about 2-3 minutes)",
                "model_notify": "I'll notify you when it's done!",
                "download_glb": "Download GLB",
                "download_stl": "Download STL",
                "convert_to_gcode": "Convert to G-code",
                "check_progress": "Check Progress",

                # 이슈 해결
                "no_issue": "No Issue",
                "false_positive": "false positive",
                "analysis_result": "Analysis Result",
                "reason": "Reason",
                "code_normal": "This code is working correctly. It's likely intended behavior by the slicer.",
                "dismiss_issue": "Dismiss Issue",
                "issue_resolution": "Issue Resolution",
                "severity": "Severity",
                "severity_levels": {
                    "low": "Low",
                    "medium": "Medium",
                    "high": "High",
                    "info": "Info"
                },
                "problem_cause": "Problem Cause",
                "print_impact": "Print Impact",
                "quality": "Quality",
                "failure_risk": "Failure risk",
                "solution_method": "Solution Method",
                "code_fix": "Code Fix",
                "original": "Original",
                "fixed": "Fixed",
                "copy_fix": "Copy Fixed Code",
                "view_other_issues": "View Other Issues",

                # 인사 & 도움말
                "greeting": "Hello! I'm your 3D printing assistant.",
                "how_can_i_help": "How can I help you?",
                "capabilities_title": "What I can help with:",
                "cap_gcode": "**G-code Analysis** - Analyze G-code files and find issues",
                "cap_troubleshoot": "**Printer Troubleshooting** - Analyze failed print images or symptoms and suggest solutions",
                "cap_modelling": "**3D Modelling** - Create 3D models from text or images",
                "cap_qa": "**Q&A** - Answer questions about 3D printing",
                "gcode_analysis": "G-code Analysis",
                "troubleshoot": "Troubleshoot",
                "modelling_3d": "3D Modelling",

                "help_title": "How to Use",
                "help_gcode_title": "1. G-code Analysis",
                "help_gcode_desc": "- Attach a G-code file and say \"analyze this\"\n- I'll analyze print time, filament usage, and potential issues",
                "help_troubleshoot_title": "2. Printer Troubleshooting",
                "help_troubleshoot_desc": "- Attach a photo of a failed print or describe the symptoms\n- AI will analyze the problem and suggest solutions",
                "help_modelling_title": "3. 3D Modelling",
                "help_modelling_desc": "- **Text-to-3D:** \"Create a cute cat figurine\"\n- **Image-to-3D:** Attach an image and say \"make a 3D model from this\"",
                "help_general_title": "4. General Questions",
                "help_general_desc": "- Ask anything about 3D printing like PLA vs PETG differences, optimal temperatures, etc.!",
                "start_gcode": "Start G-code Analysis",
                "start_troubleshoot": "Start Troubleshooting",
                "start_modelling": "Start 3D Modelling",

                # 일반 응답
                "follow_up": "Ask a Follow-up Question",
                "select_tool_gcode": "Do Detailed Analysis",
                "modelling_hint_title": "Looking for FACTOR 3D modelling feature?",
                "modelling_hint_steps": "To create 3D models from text or images:\n1. **Log in**\n2. Select **3D Modelling** from **Tool Selection** on the left\n3. Describe or attach an image of the model you want!",
                "analyzing": "Analyzing...",

                # 가격비교
                "price_comparison_result": "Price Comparison Results",
                "search_query": "Search",
                "total_results": "Total results",
                "markets_searched": "Markets searched",
                "price_summary": "Price Summary",
                "lowest_price": "Lowest",
                "average_price": "Average",
                "highest_price": "Highest",
                "product_list": "Product List",
                "marketplace": "Marketplace",
                "rating": "Rating",
                "reviews": "reviews",
                "in_stock": "In Stock",
                "out_of_stock": "Out of Stock",
                "view_product": "View",
                "no_results": "No products found. Try different keywords.",
                "search_again": "Search Again",
                "price_comparison": "Price Comparison",
            }
        else:
            self.labels = {
                # 공통
                "error_sorry": "죄송합니다, 요청을 처리하는 중 문제가 발생했습니다.",
                "retry": "다시 시도",
                "what_can_i_help": "무엇을 도와드릴까요?",

                # G-code 분석
                "gcode_analysis_started": "G-code 분석 시작!",
                "file": "파일",
                "status": "상태",
                "segments_ready_llm_analyzing": "세그먼트 추출 완료, LLM 분석 진행 중...",
                "detected_info": "감지된 정보",
                "total_layers": "총 레이어",
                "extrusion_paths": "압출 경로",
                "travel_paths": "이동 경로",
                "viewer_hint": "3D 뷰어에서 레이어를 확인할 수 있습니다.",
                "analysis_complete_hint": "상세 분석이 완료되면 품질 점수와 이슈를 알려드릴게요!",
                "check_status": "분석 상태 확인",
                "explore_layers": "레이어 탐색",

                # G-code 동기 분석
                "gcode_analysis_complete": "G-code 분석 완료!",
                "quality_score": "품질 점수",
                "basic_info": "기본 정보",
                "estimated_print_time": "예상 출력 시간",
                "filament_usage": "필라멘트 사용량",
                "layer_height": "레이어 높이",
                "temperature_settings": "온도 설정",
                "nozzle": "노즐",
                "bed": "베드",
                "issues_found": "발견된 이슈",
                "and_more": "... 외 {count}개",
                "view_detail": "상세 분석 보기",
                "download_patched": "수정된 G-code 다운로드",
                "unknown": "알 수 없음",

                # 문제 진단
                "problem_analysis_result": "문제 분석 결과",
                "detected_problem": "감지된 문제",
                "confidence": "확신도",
                "recommended_solutions": "추천 해결 방법",
                "difficulty": "난이도",
                "estimated_time": "예상 시간",
                "source": "출처",
                "expert_opinion": "전문가 의견",
                "prevention_tips": "예방 팁",
                "references": "참고 자료",
                "detailed_diagnosis": "더 자세한 진단",
                "new_troubleshoot": "다른 문제 상담",

                # 문제 유형
                "problem_types": {
                    "bed_adhesion": "첫 레이어 접착 불량",
                    "stringing": "스트링/거미줄",
                    "warping": "뒤틀림/휨",
                    "layer_shifting": "레이어 쉬프트",
                    "under_extrusion": "압출 부족",
                    "over_extrusion": "과압출",
                    "clogging": "노즐 막힘",
                    "surface_quality": "표면 품질 문제",
                    "ghosting": "고스팅/링잉",
                    "z_banding": "Z 밴딩",
                    "blob": "블롭/점",
                    "layer_separation": "레이어 분리",
                    "elephant_foot": "코끼리 발",
                    "bridging_issue": "브리징 문제",
                    "overhang_issue": "오버행 문제",
                    "bed_leveling": "베드 레벨링 문제",
                    "nozzle_damage": "노즐 손상",
                    "extruder_skip": "익스트루더 스킵",
                    "belt_tension": "벨트 텐션 문제",
                    "heating_failure": "예열 실패",
                    "unknown": "미확인 문제"
                },

                # 3D 모델링
                "model_generation_complete": "3D 모델 생성 완료!",
                "model_generation_started": "3D 모델 생성 시작!",
                "type": "타입",
                "prompt": "프롬프트",
                "model_success": "모델이 성공적으로 생성되었습니다!",
                "model_generating": "모델을 생성 중입니다... (약 2-3분 소요)",
                "model_notify": "완료되면 알려드릴게요!",
                "download_glb": "GLB 다운로드",
                "download_stl": "STL 다운로드",
                "convert_to_gcode": "G-code로 변환",
                "check_progress": "진행 상황 확인",

                # 이슈 해결
                "no_issue": "문제 없음",
                "false_positive": "오탐(False Positive)",
                "analysis_result": "분석 결과",
                "reason": "이유",
                "code_normal": "이 코드는 정상적으로 작동합니다. 슬라이서가 의도한 동작일 가능성이 높습니다.",
                "dismiss_issue": "이슈 무시하기",
                "issue_resolution": "이슈 해결 방법",
                "severity": "심각도",
                "severity_levels": {
                    "low": "낮음",
                    "medium": "보통",
                    "high": "높음",
                    "info": "참고"
                },
                "problem_cause": "문제 원인",
                "print_impact": "출력 영향",
                "quality": "품질",
                "failure_risk": "실패 위험",
                "solution_method": "해결 방법",
                "code_fix": "코드 수정",
                "original": "원본",
                "fixed": "수정",
                "copy_fix": "수정 코드 복사",
                "view_other_issues": "다른 이슈 확인",

                # 인사 & 도움말
                "greeting": "안녕하세요! 3D 프린팅 어시스턴트입니다.",
                "how_can_i_help": "무엇을 도와드릴까요?",
                "capabilities_title": "제가 도와드릴 수 있는 것들:",
                "cap_gcode": "🔍 **G-code 분석** - G-code 파일을 분석하고 문제점을 찾아드려요",
                "cap_troubleshoot": "🔧 **프린터 문제 진단** - 출력 실패 이미지나 증상을 분석해 해결책을 제안해요",
                "cap_modelling": "🎨 **3D 모델링** - 텍스트나 이미지로 3D 모델을 만들어드려요",
                "cap_qa": "❓ **질문 답변** - 3D 프린팅 관련 질문에 답변해드려요",
                "gcode_analysis": "G-code 분석",
                "troubleshoot": "문제 진단",
                "modelling_3d": "3D 모델링",

                "help_title": "사용 방법",
                "help_gcode_title": "1. G-code 분석",
                "help_gcode_desc": "- G-code 파일을 첨부하고 \"분석해줘\"라고 말씀해주세요\n- 출력 시간, 필라멘트 사용량, 잠재적 문제점을 분석해드려요",
                "help_troubleshoot_title": "2. 프린터 문제 진단",
                "help_troubleshoot_desc": "- 실패한 출력물 사진을 첨부하거나 증상을 설명해주세요\n- AI가 문제를 분석하고 해결책을 제안해드려요",
                "help_modelling_title": "3. 3D 모델링",
                "help_modelling_desc": "- **Text-to-3D:** \"귀여운 고양이 피규어 만들어줘\"\n- **Image-to-3D:** 이미지를 첨부하고 \"이걸로 3D 모델 만들어줘\"",
                "help_general_title": "4. 일반 질문",
                "help_general_desc": "- PLA vs PETG 차이, 최적 온도 설정 등 무엇이든 물어보세요!",
                "start_gcode": "G-code 분석 시작",
                "start_troubleshoot": "문제 진단 시작",
                "start_modelling": "3D 모델링 시작",

                # 일반 응답
                "follow_up": "관련 질문하기",
                "select_tool_gcode": "상세 분석하기",
                "modelling_hint_title": "혹시 FACTOR 3D 모델링 기능을 찾고 계신가요?",
                "modelling_hint_steps": "텍스트나 이미지로 3D 모델을 생성하려면:\n1. **로그인** 후\n2. 좌측 **도구 선택**에서 **3D 모델링** 선택\n3. 원하는 모델을 설명하거나 이미지를 첨부해주세요!",
                "analyzing": "분석 중...",

                # 가격비교
                "price_comparison_result": "가격비교 결과",
                "search_query": "검색어",
                "total_results": "검색 결과",
                "markets_searched": "검색한 마켓",
                "price_summary": "가격 요약",
                "lowest_price": "최저가",
                "average_price": "평균가",
                "highest_price": "최고가",
                "product_list": "상품 목록",
                "marketplace": "판매처",
                "rating": "평점",
                "reviews": "리뷰",
                "in_stock": "재고 있음",
                "out_of_stock": "품절",
                "view_product": "보기",
                "no_results": "검색 결과가 없습니다. 다른 키워드로 검색해보세요.",
                "search_again": "다시 검색",
                "price_comparison": "가격비교",
            }

    def generate(
        self,
        intent: ChatIntent,
        tool_result: ToolResult,
        original_message: str
    ) -> tuple[str, List[SuggestedAction]]:
        """
        응답 생성

        Args:
            intent: 분류된 의도
            tool_result: 도구 실행 결과
            original_message: 원본 사용자 메시지

        Returns:
            tuple[str, List[SuggestedAction]]: (응답 텍스트, 추천 액션)
        """
        if not tool_result.success:
            return self._generate_error_response(intent, tool_result)

        if intent == ChatIntent.GCODE_ANALYSIS:
            return self._generate_gcode_response(tool_result)

        elif intent == ChatIntent.GCODE_GENERAL:
            return self._generate_gcode_general_response(tool_result)

        elif intent == ChatIntent.GCODE_ISSUE_RESOLVE:
            return self._generate_issue_resolve_response(tool_result)

        elif intent == ChatIntent.TROUBLESHOOT:
            return self._generate_troubleshoot_response(tool_result)

        elif intent in [ChatIntent.MODELLING_TEXT, ChatIntent.MODELLING_IMAGE]:
            return self._generate_modelling_response(tool_result, intent)

        elif intent == ChatIntent.GENERAL_QUESTION:
            return self._generate_general_response(tool_result, original_message)

        elif intent == ChatIntent.PRICE_COMPARISON:
            return self._generate_price_comparison_response(tool_result)

        elif intent == ChatIntent.GREETING:
            return self._generate_greeting_response()

        elif intent == ChatIntent.HELP:
            return self._generate_help_response()

        else:
            return self.labels["what_can_i_help"], []

    def _generate_error_response(
        self,
        intent: ChatIntent,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """에러 응답 생성"""
        default_error = "Unable to process your request. Please try again later." if self.language == "en" else "요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."
        error_msg = tool_result.error or default_error

        response = f"{self.labels['error_sorry']}\n\n{error_msg}"

        actions = [
            SuggestedAction(
                label=self.labels["retry"],
                action="retry",
                data={"intent": intent.value}
            )
        ]

        return response, actions

    def _generate_gcode_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """
        G-code 분석 응답 생성 (Chat API 통합)

        세그먼트 추출이 완료되고 LLM 분석이 백그라운드에서 진행 중인 상태를 응답합니다.
        클라이언트는 GET /analysis/{analysis_id} 폴링으로 진행률을 확인할 수 있습니다.
        """
        data = tool_result.data or {}

        # Chat API 통합 흐름 (세그먼트 + 스트리밍)
        status = data.get("status")
        if status == "segments_ready":
            return self._generate_gcode_streaming_response(tool_result)

        # 기존 동기 분석 응답 (하위 호환)
        return self._generate_gcode_sync_response(tool_result)

    def _generate_gcode_streaming_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """
        G-code 스트리밍 분석 응답 (세그먼트 즉시 반환 + LLM 백그라운드)

        클라이언트가 세그먼트를 즉시 렌더링하고 폴링으로 진행률을 추적할 수 있도록 합니다.
        """
        data = tool_result.data or {}
        L = self.labels

        filename = data.get("filename", "G-code")
        layer_count = data.get("layer_count", 0)
        analysis_id = data.get("analysis_id", "")

        # 세그먼트 데이터에서 경로 수 계산
        segments = data.get("segments", {})
        layers_data = segments.get("layers", [])

        # 각 레이어의 경로 수 합산
        total_extrusions = sum(layer.get("extrusionCount", 0) for layer in layers_data)
        total_travels = sum(layer.get("travelCount", 0) for layer in layers_data)

        response = f"""**{L['gcode_analysis_started']}**

**{L['file']}:** {filename}
**{L['status']}:** {L['segments_ready_llm_analyzing']}

**{L['detected_info']}:**
- {L['total_layers']}: **{layer_count}**
- {L['extrusion_paths']}: {total_extrusions:,}
- {L['travel_paths']}: {total_travels:,}

{L['viewer_hint']}
{L['analysis_complete_hint']}"""

        actions = [
            SuggestedAction(
                label=L["check_status"],
                action="check_status",
                data={"analysis_id": analysis_id}
            ),
            SuggestedAction(
                label=L["explore_layers"],
                action="explore_layers",
                data={"analysis_id": analysis_id}
            )
        ]

        return response, actions

    def _generate_gcode_sync_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """G-code 동기 분석 응답 (하위 호환용)"""
        data = tool_result.data or {}
        summary = data.get("summary", {})
        L = self.labels

        # 기본 정보 추출
        filename = data.get("filename", "G-code")
        quality_score = data.get("quality_score", 0)

        # 온도 정보
        temp = summary.get("temperature", {})
        nozzle = temp.get("nozzle", {})
        bed = temp.get("bed", {})

        # 필라멘트 정보
        filament = summary.get("filament", {})
        extrusion_m = filament.get("total_extrusion_mm", 0) / 1000

        # 레이어 정보
        layers = summary.get("layers", {})

        # 출력 시간
        time_info = summary.get("print_time", {})
        print_time = time_info.get("formatted", L["unknown"])

        # 이슈 정보
        issues = data.get("issues", [])

        response = f"""**{L['gcode_analysis_complete']}** 📊

**{L['file']}:** {filename}
**{L['quality_score']}:** {quality_score}/100

**📋 {L['basic_info']}:**
- {L['estimated_print_time']}: {print_time}
- {L['filament_usage']}: {extrusion_m:.1f}m
- {L['total_layers']}: {layers.get('total_layers', 0)}
- {L['layer_height']}: {layers.get('layer_height_mm', 0)}mm

**🌡️ {L['temperature_settings']}:**
- {L['nozzle']}: {nozzle.get('max', 0)}°C
- {L['bed']}: {bed.get('max', 0)}°C
"""

        if issues:
            response += f"\n**⚠️ {L['issues_found']} ({len(issues)}):**\n"
            for i, issue in enumerate(issues[:3], 1):
                issue_desc = issue.get("description", issue.get("message", ""))
                response += f"{i}. {issue_desc}\n"

            if len(issues) > 3:
                response += L["and_more"].format(count=len(issues) - 3) + "\n"

        actions = [
            SuggestedAction(
                label=L["view_detail"],
                action="view_analysis_detail",
                data={"analysis_id": data.get("analysis_id")}
            )
        ]

        if issues:
            actions.append(SuggestedAction(
                label=L["download_patched"],
                action="download_patched_gcode",
                data={"analysis_id": data.get("analysis_id")}
            ))

        return response, actions

    def _generate_troubleshoot_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """문제 진단 응답 생성"""
        data = tool_result.data or {}
        L = self.labels

        problem = data.get("problem", {})
        solutions = data.get("solutions", [])
        expert = data.get("expert_opinion", {})

        # 문제 유형 매핑
        problem_type = problem.get("type", "unknown")
        problem_name = L["problem_types"].get(problem_type, problem_type)
        confidence = problem.get("confidence", 0) * 100

        response = f"""**{L['problem_analysis_result']}** 🔍

**{L['detected_problem']}:** {problem_name} ({L['confidence']}: {confidence:.0f}%)
{problem.get('description', '')}

"""

        if solutions:
            response += f"**🔧 {L['recommended_solutions']}:**"
            response += "\n\n"
            for i, sol in enumerate(solutions[:3], 1):
                difficulty = sol.get('difficulty', 'medium')
                time_est = sol.get('estimated_time', '')

                # 제목과 난이도/시간
                response += f"**{i}. {sol.get('title', '')}** {L['difficulty']}: {difficulty}"
                if time_est:
                    response += f" | {L['estimated_time']}: {time_est}"
                response += "\n\n"

                steps = sol.get('steps', [])
                for j, step in enumerate(steps[:5], 1):
                    response += f"{j}. {step}\n"

                # 솔루션 출처 표시
                source_refs = sol.get('source_refs', [])
                if source_refs:
                    ref_links = [f"[{r.get('title', '')}]({r.get('url', '')})" for r in source_refs if r.get('url')]
                    if ref_links:
                        response += f"\n📎 {L['source']}: {', '.join(ref_links[:2])}"

                response += "\n\n"

        if expert.get("summary"):
            response += f"**💡 {L['expert_opinion']}:**\n{expert['summary']}\n"
            # 전문가 의견 출처 표시
            expert_refs = expert.get('source_refs', [])
            if expert_refs:
                ref_links = [f"[{r.get('title', '')}]({r.get('url', '')})" for r in expert_refs if r.get('url')]
                if ref_links:
                    response += f"📎 {L['source']}: {', '.join(ref_links[:3])}\n"
            response += "\n"

        if expert.get("prevention_tips"):
            response += f"**{L['prevention_tips']}:**\n"
            for tip in expert["prevention_tips"][:3]:
                response += f"- {tip}\n"
            response += "\n"

        # references는 프론트엔드에서 별도 UI 컴포넌트로 렌더링하므로 본문에서 제외

        actions = [
            SuggestedAction(
                label=L["detailed_diagnosis"],
                action="detailed_diagnosis",
                data={"problem_type": problem_type}
            ),
            SuggestedAction(
                label=L["new_troubleshoot"],
                action="new_troubleshoot",
                data={}
            )
        ]

        return response, actions

    def _generate_modelling_response(
        self,
        tool_result: ToolResult,
        intent: ChatIntent
    ) -> tuple[str, List[SuggestedAction]]:
        """3D 모델링 응답 생성"""
        data = tool_result.data or {}
        L = self.labels

        task_type = "Image-to-3D" if intent == ChatIntent.MODELLING_IMAGE else "Text-to-3D"
        prompt = data.get("prompt", "")
        status = data.get("status", "processing")

        if status == "completed" or data.get("glb_url"):
            response = f"""**{L['model_generation_complete']}** 🎨

**{L['type']}:** {task_type}
**{L['prompt']}:** {prompt}

{L['model_success']}
"""

            actions = [
                SuggestedAction(
                    label=L["download_glb"],
                    action="download_glb",
                    data={"url": data.get("glb_url")}
                )
            ]

            if data.get("stl_url"):
                actions.append(SuggestedAction(
                    label=L["download_stl"],
                    action="download_stl",
                    data={"url": data.get("stl_url")}
                ))

            actions.append(SuggestedAction(
                label=L["convert_to_gcode"],
                action="convert_to_gcode",
                data={"model_id": data.get("model_id")}
            ))

        else:
            response = f"""**{L['model_generation_started']}** 🎨

**{L['type']}:** {task_type}
**{L['prompt']}:** {prompt}

{L['model_generating']}

{L['model_notify']}
"""

            actions = [
                SuggestedAction(
                    label=L["check_progress"],
                    action="check_modelling_status",
                    data={"task_id": data.get("task_id")}
                )
            ]

        return response, actions

    def _generate_general_response(
        self,
        tool_result: ToolResult,
        original_message: str = ""
    ) -> tuple[str, List[SuggestedAction]]:
        """일반 질문 응답 (LLM 답변만, 참조 없음)"""
        data = tool_result.data or {}
        L = self.labels
        default_error = "Sorry, I couldn't generate a response." if self.language == "en" else "죄송합니다, 답변을 생성할 수 없습니다."
        answer = data.get("answer", default_error)

        # 3D 모델링 관련 키워드 감지 시 안내 추가
        modelling_keywords = ["만들어", "생성해", "모델링", "3d", "create", "generate", "model"]
        if any(kw in original_message.lower() for kw in modelling_keywords):
            modelling_guide = f"""

---

💡 **{L['modelling_hint_title']}**

{L['modelling_hint_steps']}"""
            answer += modelling_guide

        actions = [
            SuggestedAction(
                label=L["follow_up"],
                action="follow_up",
                data={}
            )
        ]

        return answer, actions

    def _generate_gcode_general_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """
        G-code 제너럴 모드 응답 (텍스트 답변만, 리포트 없음)

        도구 선택 없이 G-code 첨부 시 LLM 텍스트 답변만 반환
        """
        data = tool_result.data or {}
        L = self.labels
        default_error = "Unable to generate G-code analysis results." if self.language == "en" else "G-code 분석 결과를 생성할 수 없습니다."
        answer = data.get("answer", default_error)

        actions = [
            SuggestedAction(
                label=L["select_tool_gcode"],
                action="select_tool",
                data={"tool": "gcode"}
            ),
            SuggestedAction(
                label=L["follow_up"],
                action="follow_up",
                data={}
            )
        ]

        return answer, actions

    def _generate_issue_resolve_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """이슈 해결 응답 생성 (AI 해결하기)"""
        data = tool_result.data or {}
        L = self.labels
        resolution = data.get("resolution", {})
        issue_line = data.get("issue_line", 0)
        issue_type = data.get("issue_type", "unknown")

        # 문제 분석
        problem = resolution.get("problem_analysis", {})
        is_false_positive = problem.get("is_false_positive", False)

        # 영향
        impact = resolution.get("impact", {})
        severity = impact.get("severity", "medium")

        # 해결 방법
        solution = resolution.get("solution", {})
        steps = solution.get("steps", [])

        # 코드 수정
        code_fix = resolution.get("code_fix", {})
        has_fix = code_fix.get("has_fix", False)

        # 예방
        prevention = resolution.get("prevention", {})

        # 오탐인 경우
        if is_false_positive:
            line_label = "Line" if self.language == "en" else "라인"
            response = f"""**✅ {L['no_issue']}** ({line_label} {issue_line})

**{L['analysis_result']}:** {L['false_positive']}

**{L['reason']}:** {problem.get('false_positive_reason', problem.get('cause', ''))}

> 💡 {L['code_normal']}
"""
            actions = [
                SuggestedAction(
                    label=L["dismiss_issue"],
                    action="dismiss_issue",
                    data={"line": issue_line, "type": issue_type}
                )
            ]
            return response, actions

        # 실제 문제인 경우
        severity_emoji = {"low": "🟡", "medium": "🟠", "high": "🔴", "info": "ℹ️"}.get(severity, "⚠️")
        severity_label = L["severity_levels"].get(severity, severity)
        line_label = "Line" if self.language == "en" else "라인"
        analyzing_label = "Analyzing..." if self.language == "en" else "분석 중..."

        response = f"""**🔧 {L['issue_resolution']}** ({line_label} {issue_line})

**{severity_emoji} {L['severity']}:** {severity_label}

---

**📋 {L['problem_cause']}**
{problem.get('cause', analyzing_label)}

**⚠️ {L['print_impact']}**
- {L['quality']}: {impact.get('print_quality', '-')}
- {L['failure_risk']}: {impact.get('failure_risk', '-')}

---

**🛠️ {L['solution_method']}** ({L['difficulty']}: {solution.get('difficulty', 'medium')})
"""

        for i, step in enumerate(steps[:5], 1):
            response += f"{i}. {step}\n"

        # 코드 수정이 있는 경우
        if has_fix:
            response += f"""
---

**💻 {L['code_fix']}**
```gcode
# {L['original']}
{code_fix.get('original_line', '')}

# {L['fixed']}
{code_fix.get('fixed_line', '')}
```
> {code_fix.get('explanation', '')}
"""

        # 예방 팁
        tips = prevention.get("tips", [])
        if tips:
            response += f"\n---\n\n**💡 {L['prevention_tips']}**\n"
            for tip in tips[:3]:
                response += f"- {tip}\n"

        if prevention.get("slicer_settings"):
            slicer_label = "Slicer settings" if self.language == "en" else "슬라이서 설정"
            response += f"\n> {slicer_label}: {prevention['slicer_settings']}"

        actions = []

        if has_fix:
            actions.append(SuggestedAction(
                label=L["copy_fix"],
                action="copy_fix",
                data={
                    "line": issue_line,
                    "fixed_line": code_fix.get("fixed_line", "")
                }
            ))

        actions.append(SuggestedAction(
            label=L["view_other_issues"],
            action="view_issues",
            data={"analysis_id": data.get("analysis_id")}
        ))

        return response, actions

    def _generate_greeting_response(self) -> tuple[str, List[SuggestedAction]]:
        """인사 응답"""
        L = self.labels
        response = f"""{L['greeting']} 👋

{L['how_can_i_help']}

**{L['capabilities_title']}**
- {L['cap_gcode']}
- {L['cap_troubleshoot']}
- {L['cap_modelling']}
- {L['cap_qa']}
"""

        actions = [
            SuggestedAction(label=L["gcode_analysis"], action="select_tool", data={"tool": "gcode"}),
            SuggestedAction(label=L["troubleshoot"], action="select_tool", data={"tool": "troubleshoot"}),
            SuggestedAction(label=L["modelling_3d"], action="select_tool", data={"tool": "modelling"}),
        ]

        return response, actions

    def _generate_help_response(self) -> tuple[str, List[SuggestedAction]]:
        """도움말 응답"""
        L = self.labels
        response = f"""**{L['help_title']}** 📖

**{L['help_gcode_title']}** 📊
{L['help_gcode_desc']}

**{L['help_troubleshoot_title']}** 🔧
{L['help_troubleshoot_desc']}

**{L['help_modelling_title']}** 🎨
{L['help_modelling_desc']}

**{L['help_general_title']}** ❓
{L['help_general_desc']}
"""

        actions = [
            SuggestedAction(label=L["start_gcode"], action="select_tool", data={"tool": "gcode"}),
            SuggestedAction(label=L["start_troubleshoot"], action="select_tool", data={"tool": "troubleshoot"}),
            SuggestedAction(label=L["start_modelling"], action="select_tool", data={"tool": "modelling"}),
        ]

        return response, actions

    def _generate_price_comparison_response(
        self,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """가격비교 응답 생성"""
        data = tool_result.data or {}
        L = self.labels

        query = data.get("query", "")
        results_count = data.get("results_count", 0)
        markets = data.get("markets_searched", [])
        price_summary = data.get("price_summary", {})

        # 결과가 없는 경우
        if results_count == 0:
            response = f"""**{L['price_comparison_result']}** 🛒

**{L['search_query']}:** {query}

{L['no_results']}
"""
            actions = [
                SuggestedAction(
                    label=L["search_again"],
                    action="price_comparison",
                    data={}
                )
            ]
            return response, actions

        # 마켓 이름 포맷팅
        markets_str = ", ".join(markets) if markets else "-"

        # 가격 포맷팅 (원화)
        def format_price(price: int) -> str:
            return f"₩{price:,}"

        response = f"""**{L['price_comparison_result']}** 🛒

**{L['search_query']}:** {query}
**{L['total_results']}:** {results_count}개
**{L['markets_searched']}:** {markets_str}

"""

        # 가격 요약
        if price_summary:
            min_price = price_summary.get("min", 0)
            avg_price = price_summary.get("avg", 0)
            max_price = price_summary.get("max", 0)

            response += f"""**📊 {L['price_summary']}**
| {L['lowest_price']} | {L['average_price']} | {L['highest_price']} |
|---------|---------|---------|
| {format_price(min_price)} | {format_price(avg_price)} | {format_price(max_price)} |

---

"""

        # AI 리뷰 (상품 목록 대신)
        ai_review = data.get("ai_review", "")
        if ai_review:
            ai_analysis_label = "AI Analysis" if self.language == "en" else "AI 분석"
            response += f"**🤖 {ai_analysis_label}**\n\n"
            response += ai_review + "\n"

        actions = [
            SuggestedAction(
                label=L["search_again"],
                action="price_comparison",
                data={}
            ),
            SuggestedAction(
                label=L["follow_up"],
                action="follow_up",
                data={}
            )
        ]

        return response, actions
