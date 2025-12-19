"""
이미지 분석기 - Vision LLM을 사용한 3D 프린터 문제 이미지 분석 + 질문 증강 + Gate 판단

주요 기능:
1. 이미지에서 문제 감지 (detected_problems)
2. 검색용 증강 쿼리 생성 (augmented_query)
3. 추가 질문 생성 (follow_up_questions)
4. 검색 필요 여부 판단 (needs_search) - Gate 역할
"""
import json
import re
from typing import List, Optional

from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client, get_llm_by_model
from .models import ImageAnalysisResult, ProblemType, SearchDecision
from .prompts.image_analysis import IMAGE_ANALYSIS_PROMPT, IMAGE_ANALYSIS_PROMPT_KO


class ImageAnalyzer:
    """
    Vision LLM을 사용한 3D 프린터 문제 이미지 분석기 + 질문 증강

    사용자가 "이거 왜 이래요?" 같은 모호한 질문을 해도
    이미지 분석을 통해 검색에 적합한 상세 쿼리를 생성합니다.
    """

    def __init__(self, language: str = "ko", model_name: Optional[str] = None):
        """
        Args:
            language: 응답 언어 (ko, en)
            model_name: 사용할 LLM 모델명 (None이면 기본 모델 사용)
        """
        self.language = language
        self.model_name = model_name

        # 사용자 지정 모델 또는 기본 모델 사용
        if model_name:
            self.llm = get_llm_by_model(model_name, temperature=0.0, max_output_tokens=2048)
        else:
            self.llm = get_llm_client(temperature=0.0, max_output_tokens=2048)

    async def analyze_images(
        self,
        images: List[str],
        additional_context: Optional[str] = None,
        symptom_text: Optional[str] = None
    ) -> ImageAnalysisResult:
        """
        이미지 분석 + 질문 증강 실행

        Args:
            images: base64 인코딩된 이미지 리스트 (최대 5장)
            additional_context: 추가 컨텍스트 정보
            symptom_text: 사용자가 입력한 증상 텍스트 (모호한 질문 포함)

        Returns:
            ImageAnalysisResult: 분석 결과 (augmented_query, follow_up_questions 포함)
        """
        if not images:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description="이미지가 제공되지 않았습니다.",
                visual_evidence=[],
                tokens_used=0,
                augmented_query="",
                follow_up_questions=[],
                specific_symptoms=[]
            )

        # 프롬프트 선택
        prompt = IMAGE_ANALYSIS_PROMPT_KO if self.language == "ko" else IMAGE_ANALYSIS_PROMPT

        # 사용자 증상 텍스트 추가 (모호한 질문도 컨텍스트로 활용)
        if symptom_text:
            prompt += f"\n\n사용자 설명: {symptom_text}"

        if additional_context:
            prompt += f"\n\n추가 정보: {additional_context}"

        # 멀티모달 메시지 구성
        content = [{"type": "text", "text": prompt}]

        for i, img_base64 in enumerate(images[:5]):  # 최대 5장으로 확장
            # base64 데이터 정리
            img_data = self._clean_base64(img_base64)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
            })

        message = HumanMessage(content=content)

        try:
            response = await self.llm.ainvoke([message])
            return self._parse_response(response.content)
        except Exception as e:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description=f"이미지 분석 중 오류 발생: {str(e)}",
                visual_evidence=[],
                tokens_used=0,
                augmented_query="",
                follow_up_questions=[],
                specific_symptoms=[]
            )

    def analyze_images_sync(
        self,
        images: List[str],
        additional_context: Optional[str] = None,
        symptom_text: Optional[str] = None
    ) -> ImageAnalysisResult:
        """
        동기 버전의 이미지 분석 + 질문 증강

        Args:
            images: base64 인코딩된 이미지 리스트 (최대 5장)
            additional_context: 추가 컨텍스트 정보
            symptom_text: 사용자가 입력한 증상 텍스트

        Returns:
            ImageAnalysisResult: 분석 결과 (augmented_query, follow_up_questions 포함)
        """
        if not images:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description="이미지가 제공되지 않았습니다.",
                visual_evidence=[],
                tokens_used=0,
                augmented_query="",
                follow_up_questions=[],
                specific_symptoms=[]
            )

        # 프롬프트 선택
        prompt = IMAGE_ANALYSIS_PROMPT_KO if self.language == "ko" else IMAGE_ANALYSIS_PROMPT

        # 사용자 증상 텍스트 추가
        if symptom_text:
            prompt += f"\n\n사용자 설명: {symptom_text}"

        if additional_context:
            prompt += f"\n\n추가 정보: {additional_context}"

        # 멀티모달 메시지 구성
        content = [{"type": "text", "text": prompt}]

        for img_base64 in images[:5]:  # 최대 5장으로 확장
            img_data = self._clean_base64(img_base64)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
            })

        message = HumanMessage(content=content)

        try:
            response = self.llm.invoke([message])
            return self._parse_response(response.content)
        except Exception as e:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description=f"이미지 분석 중 오류 발생: {str(e)}",
                visual_evidence=[],
                tokens_used=0,
                augmented_query="",
                follow_up_questions=[],
                specific_symptoms=[]
            )

    def _clean_base64(self, img_base64: str) -> str:
        """base64 데이터 정리 (data URL prefix 제거)"""
        if "," in img_base64:
            return img_base64.split(",", 1)[1]
        return img_base64

    def _parse_response(self, content: str) -> ImageAnalysisResult:
        """LLM 응답 파싱 (질문 증강 필드 + Gate 필드 포함)"""
        try:
            # JSON 블록 추출
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 블록이 없으면 전체 내용 시도
                json_str = content

            data = json.loads(json_str)

            # 문제 유형 파싱
            detected_problems = []
            for prob in data.get("detected_problems", []):
                try:
                    detected_problems.append(ProblemType(prob))
                except ValueError:
                    # 알 수 없는 문제 유형은 UNKNOWN으로
                    detected_problems.append(ProblemType.UNKNOWN)

            # Gate 필드 파싱 (검색 필요 여부 판단)
            needs_search_str = data.get("needs_search", "recommended")
            try:
                needs_search = SearchDecision(needs_search_str)
            except ValueError:
                # 알 수 없는 값은 RECOMMENDED로 (안전하게 검색 수행)
                needs_search = SearchDecision.RECOMMENDED

            return ImageAnalysisResult(
                detected_problems=detected_problems,
                confidence_scores=data.get("confidence_scores", {}),
                description=data.get("description", ""),
                visual_evidence=data.get("visual_evidence", []),
                tokens_used=0,  # 토큰 사용량은 별도 추적 필요
                # 질문 증강 필드
                augmented_query=data.get("augmented_query", ""),
                follow_up_questions=data.get("follow_up_questions", []),
                specific_symptoms=data.get("specific_symptoms", []),
                # Gate 필드 (검색 필요 여부)
                needs_search=needs_search,
                search_skip_reason=data.get("search_skip_reason", ""),
                internal_solution=data.get("internal_solution", "")
            )

        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트에서 정보 추출 시도
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description=content[:500],  # 처음 500자
                visual_evidence=[],
                tokens_used=0,
                augmented_query="",
                follow_up_questions=[],
                specific_symptoms=[],
                # 파싱 실패 시 안전하게 검색 수행
                needs_search=SearchDecision.RECOMMENDED,
                search_skip_reason="",
                internal_solution=""
            )


async def analyze_problem_image(
    images: List[str],
    language: str = "ko",
    additional_context: Optional[str] = None,
    symptom_text: Optional[str] = None,
    model_name: Optional[str] = None
) -> ImageAnalysisResult:
    """
    편의 함수 - 이미지 분석 + 질문 증강 실행

    Args:
        images: base64 인코딩된 이미지 리스트 (최대 5장)
        language: 응답 언어 (ko, en)
        additional_context: 추가 컨텍스트
        symptom_text: 사용자 증상 텍스트 (모호한 질문 포함)
        model_name: 사용할 LLM 모델명 (None이면 기본 모델)

    Returns:
        ImageAnalysisResult: 분석 결과 (augmented_query, follow_up_questions 포함)
    """
    analyzer = ImageAnalyzer(language=language, model_name=model_name)
    return await analyzer.analyze_images(images, additional_context, symptom_text)
