"""
응답 생성기 - 도구 결과를 자연어 응답으로 변환
"""
import logging
from typing import List, Optional, Dict, Any

from .models import ChatIntent, ToolResult, SuggestedAction

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    도구 결과를 사용자 친화적인 응답으로 변환
    """

    def __init__(self, language: str = "ko"):
        self.language = language

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

        elif intent == ChatIntent.GREETING:
            return self._generate_greeting_response()

        elif intent == ChatIntent.HELP:
            return self._generate_help_response()

        else:
            return "무엇을 도와드릴까요?", []

    def _generate_error_response(
        self,
        intent: ChatIntent,
        tool_result: ToolResult
    ) -> tuple[str, List[SuggestedAction]]:
        """에러 응답 생성"""
        error_msg = tool_result.error or "요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."

        # "오류:" 접두사 없이 친절한 메시지로 표시
        response = f"죄송합니다, 요청을 처리하는 중 문제가 발생했습니다.\n\n{error_msg}"

        actions = [
            SuggestedAction(
                label="다시 시도",
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

        filename = data.get("filename", "G-code")
        layer_count = data.get("layer_count", 0)
        analysis_id = data.get("analysis_id", "")

        # 세그먼트 데이터에서 경로 수 계산
        segments = data.get("segments", {})
        layers_data = segments.get("layers", [])

        # 각 레이어의 경로 수 합산
        total_extrusions = sum(layer.get("extrusionCount", 0) for layer in layers_data)
        total_travels = sum(layer.get("travelCount", 0) for layer in layers_data)

        response = f"""**G-code 분석 시작!**

**파일:** {filename}
**상태:** 세그먼트 추출 완료, LLM 분석 진행 중...

**감지된 정보:**
- 총 레이어: **{layer_count}개**
- 압출 경로: {total_extrusions:,}개
- 이동 경로: {total_travels:,}개

3D 뷰어에서 레이어를 확인할 수 있습니다.
상세 분석이 완료되면 품질 점수와 이슈를 알려드릴게요!"""

        actions = [
            SuggestedAction(
                label="분석 상태 확인",
                action="check_status",
                data={"analysis_id": analysis_id}
            ),
            SuggestedAction(
                label="레이어 탐색",
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
        print_time = time_info.get("formatted", "알 수 없음")

        # 이슈 정보
        issues = data.get("issues", [])

        response = f"""**G-code 분석 완료!** 📊

**파일:** {filename}
**품질 점수:** {quality_score}/100

**📋 기본 정보:**
- 예상 출력 시간: {print_time}
- 필라멘트 사용량: {extrusion_m:.1f}m
- 총 레이어: {layers.get('total_layers', 0)}개
- 레이어 높이: {layers.get('layer_height_mm', 0)}mm

**🌡️ 온도 설정:**
- 노즐: {nozzle.get('max', 0)}°C
- 베드: {bed.get('max', 0)}°C
"""

        if issues:
            response += f"\n**⚠️ 발견된 이슈 ({len(issues)}개):**\n"
            for i, issue in enumerate(issues[:3], 1):
                issue_desc = issue.get("description", issue.get("message", ""))
                response += f"{i}. {issue_desc}\n"

            if len(issues) > 3:
                response += f"... 외 {len(issues) - 3}개\n"

        actions = [
            SuggestedAction(
                label="상세 분석 보기",
                action="view_analysis_detail",
                data={"analysis_id": data.get("analysis_id")}
            )
        ]

        if issues:
            actions.append(SuggestedAction(
                label="수정된 G-code 다운로드",
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

        problem = data.get("problem", {})
        solutions = data.get("solutions", [])
        expert = data.get("expert_opinion", {})
        references = data.get("references", [])

        # 문제 유형 한글 매핑
        problem_type_ko = {
            "bed_adhesion": "첫 레이어 접착 불량",
            "stringing": "스트링/거미줄",
            "warping": "뒤틀림/휨",
            "layer_shifting": "레이어 쉬프트",
            "under_extrusion": "압출 부족",
            "over_extrusion": "과압출",
            "clogging": "노즐 막힘",
            "unknown": "미확인 문제"
        }

        problem_type = problem.get("type", "unknown")
        problem_name = problem_type_ko.get(problem_type, problem_type)
        confidence = problem.get("confidence", 0) * 100

        response = f"""**문제 분석 결과** 🔍

**감지된 문제:** {problem_name} (확신도: {confidence:.0f}%)
{problem.get('description', '')}

"""

        if solutions:
            response += "**🔧 추천 해결 방법:**\n\n"
            for i, sol in enumerate(solutions[:3], 1):
                response += f"**{i}. {sol.get('title', '')}**\n"
                difficulty = sol.get('difficulty', 'medium')
                time_est = sol.get('estimated_time', '')

                response += f"   난이도: {difficulty}"
                if time_est:
                    response += f" | 예상 시간: {time_est}"
                response += "\n"

                steps = sol.get('steps', [])
                for j, step in enumerate(steps[:5], 1):
                    response += f"   {j}. {step}\n"

                # 솔루션 출처 표시
                source_refs = sol.get('source_refs', [])
                if source_refs:
                    ref_links = [f"[{r.get('title', '')}]({r.get('url', '')})" for r in source_refs if r.get('url')]
                    if ref_links:
                        response += f"   📎 출처: {', '.join(ref_links[:2])}\n"

                response += "\n"

        if expert.get("summary"):
            response += f"**💡 전문가 의견:**\n{expert['summary']}\n"
            # 전문가 의견 출처 표시
            expert_refs = expert.get('source_refs', [])
            if expert_refs:
                ref_links = [f"[{r.get('title', '')}]({r.get('url', '')})" for r in expert_refs if r.get('url')]
                if ref_links:
                    response += f"📎 출처: {', '.join(ref_links[:3])}\n"
            response += "\n"

        if expert.get("prevention_tips"):
            response += "**예방 팁:**\n"
            for tip in expert["prevention_tips"][:3]:
                response += f"- {tip}\n"
            response += "\n"

        if references:
            response += "**📚 참고 자료:**\n"
            for ref in references[:10]:
                response += f"- [{ref.get('title', '')}]({ref.get('url', '')})\n"

        actions = [
            SuggestedAction(
                label="더 자세한 진단",
                action="detailed_diagnosis",
                data={"problem_type": problem_type}
            ),
            SuggestedAction(
                label="다른 문제 상담",
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

        task_type = "Image-to-3D" if intent == ChatIntent.MODELLING_IMAGE else "Text-to-3D"
        prompt = data.get("prompt", "")
        status = data.get("status", "processing")

        if status == "completed" or data.get("glb_url"):
            response = f"""**3D 모델 생성 완료!** 🎨

**타입:** {task_type}
**프롬프트:** {prompt}

모델이 성공적으로 생성되었습니다!
"""

            actions = [
                SuggestedAction(
                    label="GLB 다운로드",
                    action="download_glb",
                    data={"url": data.get("glb_url")}
                )
            ]

            if data.get("stl_url"):
                actions.append(SuggestedAction(
                    label="STL 다운로드",
                    action="download_stl",
                    data={"url": data.get("stl_url")}
                ))

            actions.append(SuggestedAction(
                label="G-code로 변환",
                action="convert_to_gcode",
                data={"model_id": data.get("model_id")}
            ))

        else:
            response = f"""**3D 모델 생성 시작!** 🎨

**타입:** {task_type}
**프롬프트:** {prompt}

모델을 생성 중입니다... (약 2-3분 소요)

완료되면 알려드릴게요!
"""

            actions = [
                SuggestedAction(
                    label="진행 상황 확인",
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
        answer = data.get("answer", "죄송합니다, 답변을 생성할 수 없습니다.")

        # 3D 모델링 관련 키워드 감지 시 안내 추가
        modelling_keywords = ["만들어", "생성해", "모델링", "3d", "create", "generate", "model"]
        if any(kw in original_message.lower() for kw in modelling_keywords):
            modelling_guide = """

---

💡 **혹시 FACTOR 3D 모델링 기능을 찾고 계신가요?**

텍스트나 이미지로 3D 모델을 생성하려면:
1. **로그인** 후
2. 좌측 **도구 선택**에서 **3D 모델링** 선택
3. 원하는 모델을 설명하거나 이미지를 첨부해주세요!"""
            answer += modelling_guide

        actions = [
            SuggestedAction(
                label="관련 질문하기",
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
        answer = data.get("answer", "G-code 분석 결과를 생성할 수 없습니다.")

        actions = [
            SuggestedAction(
                label="상세 분석하기",
                action="select_tool",
                data={"tool": "gcode"}
            ),
            SuggestedAction(
                label="다른 질문하기",
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
            response = f"""**✅ 문제 없음** (라인 {issue_line})

**분석 결과:** 이 이슈는 **오탐(False Positive)**으로 판단됩니다.

**이유:** {problem.get('false_positive_reason', problem.get('cause', ''))}

> 💡 이 코드는 정상적으로 작동합니다. 슬라이서가 의도한 동작일 가능성이 높습니다.
"""
            actions = [
                SuggestedAction(
                    label="이슈 무시하기",
                    action="dismiss_issue",
                    data={"line": issue_line, "type": issue_type}
                )
            ]
            return response, actions

        # 실제 문제인 경우
        severity_emoji = {"low": "🟡", "medium": "🟠", "high": "🔴", "info": "ℹ️"}.get(severity, "⚠️")
        severity_ko = {"low": "낮음", "medium": "보통", "high": "높음", "info": "참고"}.get(severity, severity)

        response = f"""**🔧 이슈 해결 방법** (라인 {issue_line})

**{severity_emoji} 심각도:** {severity_ko}

---

**📋 문제 원인**
{problem.get('cause', '분석 중...')}

**⚠️ 출력 영향**
- 품질: {impact.get('print_quality', '-')}
- 실패 위험: {impact.get('failure_risk', '-')}

---

**🛠️ 해결 방법** (난이도: {solution.get('difficulty', 'medium')})
"""

        for i, step in enumerate(steps[:5], 1):
            response += f"{i}. {step}\n"

        # 코드 수정이 있는 경우
        if has_fix:
            response += f"""
---

**💻 코드 수정**
```gcode
# 원본
{code_fix.get('original_line', '')}

# 수정
{code_fix.get('fixed_line', '')}
```
> {code_fix.get('explanation', '')}
"""

        # 예방 팁
        tips = prevention.get("tips", [])
        if tips:
            response += "\n---\n\n**💡 예방 팁**\n"
            for tip in tips[:3]:
                response += f"- {tip}\n"

        if prevention.get("slicer_settings"):
            response += f"\n> 슬라이서 설정: {prevention['slicer_settings']}"

        actions = []

        if has_fix:
            actions.append(SuggestedAction(
                label="수정 코드 복사",
                action="copy_fix",
                data={
                    "line": issue_line,
                    "fixed_line": code_fix.get("fixed_line", "")
                }
            ))

        actions.append(SuggestedAction(
            label="다른 이슈 확인",
            action="view_issues",
            data={"analysis_id": data.get("analysis_id")}
        ))

        return response, actions

    def _generate_greeting_response(self) -> tuple[str, List[SuggestedAction]]:
        """인사 응답"""
        response = """안녕하세요! 3D 프린팅 어시스턴트입니다. 👋

무엇을 도와드릴까요?

**제가 도와드릴 수 있는 것들:**
- 🔍 **G-code 분석** - G-code 파일을 분석하고 문제점을 찾아드려요
- 🔧 **프린터 문제 진단** - 출력 실패 이미지나 증상을 분석해 해결책을 제안해요
- 🎨 **3D 모델링** - 텍스트나 이미지로 3D 모델을 만들어드려요
- ❓ **질문 답변** - 3D 프린팅 관련 질문에 답변해드려요
"""

        actions = [
            SuggestedAction(label="G-code 분석", action="select_tool", data={"tool": "gcode"}),
            SuggestedAction(label="문제 진단", action="select_tool", data={"tool": "troubleshoot"}),
            SuggestedAction(label="3D 모델링", action="select_tool", data={"tool": "modelling"}),
        ]

        return response, actions

    def _generate_help_response(self) -> tuple[str, List[SuggestedAction]]:
        """도움말 응답"""
        response = """**사용 방법** 📖

**1. G-code 분석** 📊
- G-code 파일을 첨부하고 "분석해줘"라고 말씀해주세요
- 출력 시간, 필라멘트 사용량, 잠재적 문제점을 분석해드려요

**2. 프린터 문제 진단** 🔧
- 실패한 출력물 사진을 첨부하거나 증상을 설명해주세요
- AI가 문제를 분석하고 해결책을 제안해드려요

**3. 3D 모델링** 🎨
- **Text-to-3D:** "귀여운 고양이 피규어 만들어줘"
- **Image-to-3D:** 이미지를 첨부하고 "이걸로 3D 모델 만들어줘"

**4. 일반 질문** ❓
- PLA vs PETG 차이, 최적 온도 설정 등 무엇이든 물어보세요!
"""

        actions = [
            SuggestedAction(label="G-code 분석 시작", action="select_tool", data={"tool": "gcode"}),
            SuggestedAction(label="문제 진단 시작", action="select_tool", data={"tool": "troubleshoot"}),
            SuggestedAction(label="3D 모델링 시작", action="select_tool", data={"tool": "modelling"}),
        ]

        return response, actions
