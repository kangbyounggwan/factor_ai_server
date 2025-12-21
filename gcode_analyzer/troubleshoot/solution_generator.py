"""
솔루션 생성기 - LLM을 사용한 3D 프린터 문제 해결책 생성
"""
import json
import re
from typing import List, Optional, Dict, Any

from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client
from .models import (
    Problem, Solution, ExpertOpinion, Reference,
    SearchResult, ImageAnalysisResult, ProblemType, Difficulty,
    Verdict, VerdictAction
)
from .printer_database import get_search_context
from .prompts.solution import SOLUTION_GENERATION_PROMPT, SOLUTION_GENERATION_PROMPT_KO


class SolutionGenerator:
    """
    LLM 기반 솔루션 생성기

    이미지 분석 결과와 검색 결과를 종합하여 최종 해결책 생성
    """

    def __init__(self, language: str = "ko"):
        """
        Args:
            language: 응답 언어 (ko, en)
        """
        self.language = language
        self.llm = get_llm_client(temperature=0.1, max_output_tokens=4096)

    async def generate_solution(
        self,
        manufacturer: Optional[str],
        model: Optional[str],
        symptom_text: str,
        image_analysis: Optional[ImageAnalysisResult],
        search_results: List[SearchResult],
        filament_type: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        종합 솔루션 생성

        Args:
            manufacturer: 프린터 제조사
            model: 프린터 모델
            symptom_text: 사용자 증상 설명
            image_analysis: 이미지 분석 결과
            search_results: 웹 검색 결과
            filament_type: 필라멘트 종류
            conversation_history: 이전 대화 히스토리

        Returns:
            Dict containing Problem, Solutions, ExpertOpinion
        """
        # 문제 유형 결정
        problem_type = self._determine_problem_type(symptom_text, image_analysis)

        # 프린터 컨텍스트 가져오기
        printer_context = get_search_context(manufacturer, model) if manufacturer else {}

        # 검색 결과 요약 생성
        search_summary = self._summarize_search_results(search_results)

        # 대화 히스토리 요약 생성
        conversation_context = ""
        if conversation_history:
            conversation_context = "\n\n## 이전 대화 컨텍스트\n"
            for item in conversation_history[-6:]:  # 최근 6개만
                role = "사용자" if item.get("role") == "user" else "어시스턴트"
                content = item.get("content", "")[:200]  # 200자 제한
                conversation_context += f"- {role}: {content}\n"

        # 프롬프트 구성
        prompt_template = SOLUTION_GENERATION_PROMPT_KO if self.language == "ko" else SOLUTION_GENERATION_PROMPT

        prompt = prompt_template.format(
            manufacturer=manufacturer or "알 수 없음",
            model=model or "알 수 없음",
            firmware_type=printer_context.get("firmware_type", "unknown"),
            problem_type=problem_type.value,
            problem_description=image_analysis.description if image_analysis else symptom_text,
            symptom_text=symptom_text,
            filament_type=filament_type or "PLA",
            search_results_summary=search_summary
        )

        # 대화 컨텍스트 추가
        if conversation_context:
            prompt = prompt + conversation_context

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return self._parse_solution_response(response.content, problem_type)
        except Exception as e:
            # 기본 솔루션 반환
            return self._get_default_solution(problem_type, symptom_text)

    def _determine_problem_type(
        self,
        symptom_text: str,
        image_analysis: Optional[ImageAnalysisResult]
    ) -> ProblemType:
        """문제 유형 결정"""
        # 이미지 분석 결과 우선
        if image_analysis and image_analysis.detected_problems:
            return image_analysis.detected_problems[0]

        # 텍스트 기반 키워드 매칭
        symptom_lower = symptom_text.lower()
        keyword_mapping = {
            ProblemType.BED_ADHESION: ["접착", "붙지", "떨어", "first layer", "adhesion", "stick"],
            ProblemType.STRINGING: ["스트링", "거미줄", "실", "string", "ooze"],
            ProblemType.WARPING: ["뒤틀", "휨", "들림", "warp", "curl", "lift"],
            ProblemType.LAYER_SHIFTING: ["레이어 쉬프트", "layer shift", "어긋", "밀림"],
            ProblemType.UNDER_EXTRUSION: ["압출 부족", "under extrusion", "빈틈", "gap"],
            ProblemType.OVER_EXTRUSION: ["과압출", "over extrusion", "두꺼", "blob"],
            ProblemType.GHOSTING: ["고스팅", "링잉", "물결", "ghost", "ring"],
            ProblemType.Z_BANDING: ["z 밴딩", "줄무늬", "z band", "horizontal line"],
            ProblemType.CLOGGING: ["막힘", "노즐", "clog", "jam"],
            ProblemType.BED_LEVELING: ["레벨링", "level", "수평"],
            ProblemType.HEATING_FAILURE: ["예열", "온도", "heat", "temp"],
        }

        for problem_type, keywords in keyword_mapping.items():
            for keyword in keywords:
                if keyword in symptom_lower:
                    return problem_type

        return ProblemType.UNKNOWN

    def _summarize_search_results(self, search_results: List[SearchResult]) -> str:
        """검색 결과 요약"""
        summaries = []

        for result in search_results:
            for ref in result.results[:3]:  # 각 검색당 상위 3개
                if ref.snippet:
                    summaries.append(f"- [{ref.source}] {ref.title}: {ref.snippet}")

        if not summaries:
            return "검색 결과 없음"

        return "\n".join(summaries[:10])  # 최대 10개

    def _parse_solution_response(self, content: str, default_problem_type: ProblemType) -> Dict[str, Any]:
        """솔루션 응답 파싱"""
        try:
            # JSON 블록 추출
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            data = json.loads(json_str)

            # Verdict 파싱 (한 줄 결론)
            verdict = None
            verdict_data = data.get("verdict", {})
            if verdict_data:
                try:
                    action = VerdictAction(verdict_data.get("action", "continue"))
                except ValueError:
                    action = VerdictAction.CONTINUE

                verdict = Verdict(
                    action=action,
                    headline=verdict_data.get("headline", ""),
                    reason=verdict_data.get("reason", "")
                )

            # Problem 파싱
            problem_data = data.get("problem", {})
            try:
                problem_type = ProblemType(problem_data.get("type", default_problem_type.value))
            except ValueError:
                problem_type = default_problem_type

            problem = Problem(
                type=problem_type,
                confidence=problem_data.get("confidence", 0.7),
                description=problem_data.get("description", ""),
                detected_from="analysis"
            )

            # Solutions 파싱
            solutions = []
            for sol_data in data.get("solutions", []):
                try:
                    difficulty = Difficulty(sol_data.get("difficulty", "medium"))
                except ValueError:
                    difficulty = Difficulty.MEDIUM

                solutions.append(Solution(
                    priority=sol_data.get("priority", len(solutions) + 1),
                    title=sol_data.get("title", ""),
                    steps=sol_data.get("steps", []),
                    difficulty=difficulty,
                    estimated_time=sol_data.get("estimated_time"),
                    tools_needed=sol_data.get("tools_needed"),
                    warnings=sol_data.get("warnings"),
                    source_refs=sol_data.get("source_refs")
                ))

            # Expert Opinion 파싱
            expert_data = data.get("expert_opinion", {})
            expert_opinion = ExpertOpinion(
                summary=expert_data.get("summary", ""),
                prevention_tips=expert_data.get("prevention_tips", []),
                when_to_seek_help=expert_data.get("when_to_seek_help"),
                related_issues=expert_data.get("related_issues"),
                source_refs=expert_data.get("source_refs")
            )

            return {
                "verdict": verdict,
                "problem": problem,
                "solutions": solutions,
                "expert_opinion": expert_opinion
            }

        except (json.JSONDecodeError, Exception) as e:
            return self._get_default_solution(default_problem_type, str(e))

    def _get_default_solution(self, problem_type: ProblemType, context: str) -> Dict[str, Any]:
        """기본 솔루션 반환"""
        default_solutions = {
            ProblemType.BED_ADHESION: {
                "title": "베드 레벨링 및 접착력 개선",
                "steps": [
                    "프린터를 예열합니다 (베드 60°C, 노즐 200°C)",
                    "Auto Home 실행 후 각 코너에서 레벨링 확인",
                    "종이 한 장이 살짝 끌리는 정도로 Z 높이 조정",
                    "베드를 IPA로 깨끗이 청소",
                    "첫 레이어 속도를 20-25mm/s로 낮춤",
                    "베드 온도를 65-70°C로 상향 시도"
                ],
                "difficulty": Difficulty.EASY
            },
            ProblemType.STRINGING: {
                "title": "리트랙션 설정 최적화",
                "steps": [
                    "리트랙션 거리를 5-6mm로 설정 (Direct Drive는 1-2mm)",
                    "리트랙션 속도를 40-60mm/s로 설정",
                    "노즐 온도를 5-10°C 낮춤",
                    "이동 속도(Travel Speed)를 150-200mm/s로 높임",
                    "스트링 테스트 모델로 설정 확인"
                ],
                "difficulty": Difficulty.MEDIUM
            },
            ProblemType.CLOGGING: {
                "title": "노즐 막힘 해결",
                "steps": [
                    "노즐을 출력 온도 + 10°C로 예열",
                    "필라멘트를 빠르게 빼서 Cold Pull 시도",
                    "니들 또는 청소용 와이어로 노즐 청소",
                    "막힘이 심하면 노즐 교체 고려",
                    "PTFE 튜브 상태 확인"
                ],
                "difficulty": Difficulty.MEDIUM
            },
        }

        default_info = default_solutions.get(problem_type, {
            "title": "일반 문제 해결",
            "steps": [
                "프린터 상태 점검",
                "슬라이서 설정 확인",
                "필라멘트 품질 확인"
            ],
            "difficulty": Difficulty.MEDIUM
        })

        return {
            "verdict": Verdict(
                action=VerdictAction.CONTINUE,
                headline="추가 정보가 필요해 보입니다.",
                reason="정확한 진단을 위해 증상을 더 자세히 설명해 주시면 좋겠습니다."
            ),
            "problem": Problem(
                type=problem_type,
                confidence=0.5,
                description=f"감지된 문제: {problem_type.value}",
                detected_from="text"
            ),
            "solutions": [
                Solution(
                    priority=1,
                    title=default_info["title"],
                    steps=default_info["steps"],
                    difficulty=default_info["difficulty"],
                    estimated_time="10-30분",
                    tools_needed=None,
                    warnings=None
                )
            ],
            "expert_opinion": ExpertOpinion(
                summary="기본 해결책을 제공합니다. 문제가 지속되면 추가 정보를 제공해주세요.",
                prevention_tips=["정기적인 프린터 점검", "양질의 필라멘트 사용"],
                when_to_seek_help="위 방법으로 해결되지 않을 경우",
                related_issues=None
            )
        }


async def generate_troubleshooting_solution(
    manufacturer: Optional[str],
    model: Optional[str],
    symptom_text: str,
    image_analysis: Optional[ImageAnalysisResult] = None,
    search_results: List[SearchResult] = None,
    filament_type: Optional[str] = None,
    language: str = "ko"
) -> Dict[str, Any]:
    """
    편의 함수 - 트러블슈팅 솔루션 생성

    Args:
        manufacturer: 프린터 제조사
        model: 프린터 모델
        symptom_text: 증상 설명
        image_analysis: 이미지 분석 결과
        search_results: 검색 결과
        filament_type: 필라멘트 종류
        language: 언어

    Returns:
        솔루션 딕셔너리
    """
    generator = SolutionGenerator(language=language)
    return await generator.generate_solution(
        manufacturer=manufacturer,
        model=model,
        symptom_text=symptom_text,
        image_analysis=image_analysis,
        search_results=search_results or [],
        filament_type=filament_type
    )
