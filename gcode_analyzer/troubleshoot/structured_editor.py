"""
구조화 편집기 - Evidence 기반 응답 편집

Perplexity 검색 결과(Evidence)를 사용자 친화적인 구조로 편집합니다.
새로운 추론 없이 근거만 재구성하는 역할입니다.

핵심 규칙:
- 새로운 원인 추론 금지
- 근거 없는 정보 추가 금지
- Evidence만 재구성하여 출력
"""
import json
import re
import logging
from typing import List, Optional, Dict, Any

from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client, get_llm_by_model
from .models import (
    ImageAnalysisResult, PerplexitySearchResult, Evidence,
    StructuredDiagnosis, Problem, Solution, ExpertOpinion,
    ProblemType, Difficulty
)

logger = logging.getLogger(__name__)


# 구조화 편집기 프롬프트
STRUCTURED_EDITOR_PROMPT_KO = """당신은 3D 프린터 문제 해결 정보 편집기입니다.

## 엄격한 규칙
❌ 새로운 원인 추론 금지
❌ 근거 없는 정보 추가 금지
❌ 검색 결과에 없는 내용 작성 금지
✅ 제공된 Evidence만 재구성
✅ 사용자가 이해하기 쉽게 정리
✅ 모든 정보에 출처 명시

## 입력 정보
- 관찰된 증상: {observed_symptoms}
- 문제 유형: {problem_type}
- 수집된 근거:
{evidence_list}

## 출력 형식 (이 구조만 사용)
```json
{{
    "observed": "이미지에서 관찰된 증상 요약 (1-2문장)",
    "likely_causes": [
        {{"cause": "원인 설명", "source": "출처URL"}},
        {{"cause": "원인 설명", "source": "출처URL"}}
    ],
    "immediate_checks": [
        "지금 바로 확인할 것 1",
        "지금 바로 확인할 것 2",
        "지금 바로 확인할 것 3"
    ],
    "solutions": [
        {{
            "title": "해결책 제목",
            "steps": ["단계1", "단계2", "단계3"],
            "difficulty": "easy|medium|hard",
            "source": "출처URL"
        }}
    ],
    "need_more_info": [
        "더 정확한 진단을 위해 필요한 정보 1",
        "더 정확한 진단을 위해 필요한 정보 2"
    ]
}}
```

## 주의사항
1. likely_causes의 각 원인은 반드시 Evidence에 있는 내용만 사용
2. solutions의 각 단계도 Evidence 기반으로만 작성
3. 출처가 없는 정보는 절대 포함하지 않음
4. need_more_info는 follow_up_questions를 참고

Evidence만 재구성하여 응답하세요:"""

STRUCTURED_EDITOR_PROMPT_EN = """You are a 3D printer troubleshooting information editor.

## Strict Rules
❌ No new inference allowed
❌ No information without evidence
❌ Nothing outside search results
✅ Only restructure provided Evidence
✅ Make it user-friendly
✅ Cite source for all information

## Input Information
- Observed symptoms: {observed_symptoms}
- Problem type: {problem_type}
- Collected evidence:
{evidence_list}

## Output Format (use this structure only)
```json
{{
    "observed": "Summary of observed symptoms (1-2 sentences)",
    "likely_causes": [
        {{"cause": "Cause description", "source": "sourceURL"}},
        {{"cause": "Cause description", "source": "sourceURL"}}
    ],
    "immediate_checks": [
        "Check this immediately 1",
        "Check this immediately 2",
        "Check this immediately 3"
    ],
    "solutions": [
        {{
            "title": "Solution title",
            "steps": ["Step 1", "Step 2", "Step 3"],
            "difficulty": "easy|medium|hard",
            "source": "sourceURL"
        }}
    ],
    "need_more_info": [
        "Information needed for accurate diagnosis 1",
        "Information needed for accurate diagnosis 2"
    ]
}}
```

## Important
1. Each cause in likely_causes must come from Evidence only
2. Each step in solutions must be Evidence-based only
3. Never include information without source
4. need_more_info should reference follow_up_questions

Restructure Evidence only:"""


class StructuredEditor:
    """
    구조화 편집기 - Evidence 기반 응답 생성

    역할: 편집만 (추론 금지)
    - Perplexity 결과를 사용자 친화적 구조로 변환
    - 모든 정보에 출처 명시
    - GPT-3.5 / Gemini Flash급으로 충분
    """

    def __init__(self, language: str = "ko", model_name: Optional[str] = None):
        """
        Args:
            language: 응답 언어 (ko, en)
            model_name: 사용할 LLM 모델명 (None이면 기본 모델)
        """
        self.language = language
        self.model_name = model_name

        # 사용자 지정 모델 또는 기본 모델 사용
        if model_name:
            self.llm = get_llm_by_model(model_name, temperature=0.1, max_output_tokens=1500)
        else:
            self.llm = get_llm_client(temperature=0.1, max_output_tokens=1500)

    async def edit(
        self,
        image_analysis: Optional[ImageAnalysisResult],
        search_result: PerplexitySearchResult,
        symptom_text: str,
        problem_type: ProblemType = ProblemType.UNKNOWN
    ) -> StructuredDiagnosis:
        """
        Evidence 기반 구조화 응답 생성

        Args:
            image_analysis: 이미지 분석 결과
            search_result: Perplexity 검색 결과
            symptom_text: 사용자 증상 설명
            problem_type: 문제 유형

        Returns:
            StructuredDiagnosis: 구조화된 진단 결과
        """
        # 관찰된 증상 구성
        observed_symptoms = self._build_observed_symptoms(image_analysis, symptom_text)

        # Evidence 목록 구성 (검색 스킵 시 internal_solution 활용)
        evidence_list = self._build_evidence_list(search_result, image_analysis)

        # 프롬프트 구성
        prompt_template = (
            STRUCTURED_EDITOR_PROMPT_KO if self.language == "ko"
            else STRUCTURED_EDITOR_PROMPT_EN
        )

        prompt = prompt_template.format(
            observed_symptoms=observed_symptoms,
            problem_type=problem_type.value,
            evidence_list=evidence_list
        )

        # follow_up_questions 추가
        if image_analysis and image_analysis.follow_up_questions:
            prompt += f"\n\n참고할 추가 질문: {', '.join(image_analysis.follow_up_questions)}"

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return self._parse_response(response.content, image_analysis, search_result)
        except Exception as e:
            logger.error(f"Structured editing failed: {e}")
            return self._get_fallback_response(image_analysis, search_result, symptom_text)

    def _build_observed_symptoms(
        self,
        image_analysis: Optional[ImageAnalysisResult],
        symptom_text: str
    ) -> str:
        """관찰된 증상 텍스트 구성"""
        parts = []

        if image_analysis:
            if image_analysis.description:
                parts.append(f"[이미지 분석] {image_analysis.description}")
            if image_analysis.visual_evidence:
                parts.append(f"[시각적 증거] {', '.join(image_analysis.visual_evidence[:3])}")

        if symptom_text:
            parts.append(f"[사용자 설명] {symptom_text}")

        return "\n".join(parts) if parts else "증상 정보 없음"

    def _build_evidence_list(
        self,
        search_result: PerplexitySearchResult,
        image_analysis: Optional[ImageAnalysisResult] = None
    ) -> str:
        """Evidence 목록 텍스트 구성"""
        lines = []

        # 검색 스킵된 경우 (내부 KB 솔루션 사용)
        if image_analysis and image_analysis.internal_solution:
            lines.append(f"[내부 지식] {image_analysis.internal_solution}")
            lines.append("   출처: 내부 KB (일반적인 3D 프린팅 문제)")
            return "\n".join(lines)

        for i, evidence in enumerate(search_result.findings[:10], 1):  # 최대 10개
            if evidence.fact:
                lines.append(f"{i}. {evidence.fact}")
                lines.append(f"   출처: {evidence.source_url}")
            else:
                lines.append(f"{i}. [참조] {evidence.source_url}")

        if search_result.summary and not lines:
            lines.append(f"요약: {search_result.summary[:500]}")

        return "\n".join(lines) if lines else "검색 결과 없음"

    def _parse_response(
        self,
        content: str,
        image_analysis: Optional[ImageAnalysisResult],
        search_result: PerplexitySearchResult
    ) -> StructuredDiagnosis:
        """LLM 응답 파싱"""
        try:
            # JSON 블록 추출
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            data = json.loads(json_str)

            return StructuredDiagnosis(
                observed=data.get("observed", ""),
                likely_causes=data.get("likely_causes", []),
                immediate_checks=data.get("immediate_checks", []),
                solutions=data.get("solutions", []),
                need_more_info=data.get("need_more_info", [])
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse structured response: {e}")
            return self._get_fallback_response(image_analysis, search_result, "")

    def _get_fallback_response(
        self,
        image_analysis: Optional[ImageAnalysisResult],
        search_result: PerplexitySearchResult,
        symptom_text: str
    ) -> StructuredDiagnosis:
        """폴백 응답 생성"""
        observed = symptom_text
        if image_analysis and image_analysis.description:
            observed = image_analysis.description

        # Evidence에서 원인 추출
        likely_causes = []
        for evidence in search_result.findings[:3]:
            if evidence.fact:
                likely_causes.append({
                    "cause": evidence.fact[:200],
                    "source": evidence.source_url
                })

        # 기본 체크 항목
        immediate_checks = [
            "프린터 설정 확인",
            "필라멘트 상태 점검",
            "노즐 및 베드 상태 확인"
        ]

        # need_more_info
        need_more_info = []
        if image_analysis and image_analysis.follow_up_questions:
            need_more_info = image_analysis.follow_up_questions[:3]

        return StructuredDiagnosis(
            observed=observed,
            likely_causes=likely_causes,
            immediate_checks=immediate_checks,
            solutions=[],
            need_more_info=need_more_info
        )

    def to_legacy_format(
        self,
        diagnosis: StructuredDiagnosis,
        problem_type: ProblemType,
        search_result: PerplexitySearchResult
    ) -> Dict[str, Any]:
        """
        기존 응답 형식으로 변환 (하위 호환성)

        Returns:
            Dict with Problem, Solutions, ExpertOpinion
        """
        # Problem 생성
        problem = Problem(
            type=problem_type,
            confidence=0.8,
            description=diagnosis.observed,
            detected_from="analysis"
        )

        # Solutions 생성
        solutions = []
        for i, sol_data in enumerate(diagnosis.solutions, 1):
            difficulty_str = sol_data.get("difficulty", "medium")
            try:
                difficulty = Difficulty(difficulty_str)
            except ValueError:
                difficulty = Difficulty.MEDIUM

            solutions.append(Solution(
                priority=i,
                title=sol_data.get("title", f"해결책 {i}"),
                steps=sol_data.get("steps", []),
                difficulty=difficulty,
                estimated_time=None,
                tools_needed=None,
                warnings=None,
                source_refs=[sol_data.get("source", "")]
            ))

        # 솔루션이 없으면 기본 솔루션 추가
        if not solutions:
            solutions.append(Solution(
                priority=1,
                title="기본 점검 사항",
                steps=diagnosis.immediate_checks or ["프린터 상태 확인"],
                difficulty=Difficulty.EASY,
                estimated_time="10분",
                tools_needed=None,
                warnings=None,
                source_refs=None
            ))

        # ExpertOpinion 생성
        prevention_tips = []
        for cause in diagnosis.likely_causes[:2]:
            if isinstance(cause, dict) and cause.get("cause"):
                prevention_tips.append(f"주의: {cause['cause'][:100]}")

        expert_opinion = ExpertOpinion(
            summary=diagnosis.observed,
            prevention_tips=prevention_tips or ["정기적인 프린터 점검 권장"],
            when_to_seek_help="위 방법으로 해결되지 않을 경우",
            related_issues=None,
            source_refs=search_result.citations[:3] if search_result.citations else None
        )

        return {
            "problem": problem,
            "solutions": solutions,
            "expert_opinion": expert_opinion
        }


async def edit_with_evidence(
    image_analysis: Optional[ImageAnalysisResult],
    search_result: PerplexitySearchResult,
    symptom_text: str,
    problem_type: ProblemType = ProblemType.UNKNOWN,
    language: str = "ko",
    model_name: Optional[str] = None
) -> StructuredDiagnosis:
    """
    편의 함수 - Evidence 기반 구조화 편집

    Args:
        image_analysis: 이미지 분석 결과
        search_result: Perplexity 검색 결과
        symptom_text: 사용자 증상 설명
        problem_type: 문제 유형
        language: 응답 언어
        model_name: 사용할 LLM 모델명

    Returns:
        StructuredDiagnosis: 구조화된 진단 결과
    """
    editor = StructuredEditor(language=language, model_name=model_name)
    return await editor.edit(image_analysis, search_result, symptom_text, problem_type)
