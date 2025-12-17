"""
이미지 분석기 - Gemini Vision을 사용한 3D 프린터 문제 이미지 분석
"""
import base64
import json
import re
from typing import List, Optional

from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client
from .models import ImageAnalysisResult, ProblemType
from .prompts.image_analysis import IMAGE_ANALYSIS_PROMPT, IMAGE_ANALYSIS_PROMPT_KO


class ImageAnalyzer:
    """
    Gemini Vision을 사용한 3D 프린터 문제 이미지 분석기
    """

    def __init__(self, language: str = "ko"):
        """
        Args:
            language: 응답 언어 (ko, en)
        """
        self.language = language
        self.llm = get_llm_client(temperature=0.0, max_output_tokens=2048)

    async def analyze_images(
        self,
        images: List[str],
        additional_context: Optional[str] = None
    ) -> ImageAnalysisResult:
        """
        이미지 분석 실행

        Args:
            images: base64 인코딩된 이미지 리스트
            additional_context: 추가 컨텍스트 정보

        Returns:
            ImageAnalysisResult: 분석 결과
        """
        if not images:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description="이미지가 제공되지 않았습니다.",
                visual_evidence=[],
                tokens_used=0
            )

        # 프롬프트 선택
        prompt = IMAGE_ANALYSIS_PROMPT_KO if self.language == "ko" else IMAGE_ANALYSIS_PROMPT

        if additional_context:
            prompt += f"\n\n추가 정보: {additional_context}"

        # 멀티모달 메시지 구성
        content = [{"type": "text", "text": prompt}]

        for i, img_base64 in enumerate(images[:3]):  # 최대 3장
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
                tokens_used=0
            )

    def analyze_images_sync(
        self,
        images: List[str],
        additional_context: Optional[str] = None
    ) -> ImageAnalysisResult:
        """
        동기 버전의 이미지 분석

        Args:
            images: base64 인코딩된 이미지 리스트
            additional_context: 추가 컨텍스트 정보

        Returns:
            ImageAnalysisResult: 분석 결과
        """
        if not images:
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description="이미지가 제공되지 않았습니다.",
                visual_evidence=[],
                tokens_used=0
            )

        # 프롬프트 선택
        prompt = IMAGE_ANALYSIS_PROMPT_KO if self.language == "ko" else IMAGE_ANALYSIS_PROMPT

        if additional_context:
            prompt += f"\n\n추가 정보: {additional_context}"

        # 멀티모달 메시지 구성
        content = [{"type": "text", "text": prompt}]

        for img_base64 in images[:3]:  # 최대 3장
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
                tokens_used=0
            )

    def _clean_base64(self, img_base64: str) -> str:
        """base64 데이터 정리 (data URL prefix 제거)"""
        if "," in img_base64:
            return img_base64.split(",", 1)[1]
        return img_base64

    def _parse_response(self, content: str) -> ImageAnalysisResult:
        """LLM 응답 파싱"""
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

            return ImageAnalysisResult(
                detected_problems=detected_problems,
                confidence_scores=data.get("confidence_scores", {}),
                description=data.get("description", ""),
                visual_evidence=data.get("visual_evidence", []),
                tokens_used=0  # 토큰 사용량은 별도 추적 필요
            )

        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트에서 정보 추출 시도
            return ImageAnalysisResult(
                detected_problems=[],
                confidence_scores={},
                description=content[:500],  # 처음 500자
                visual_evidence=[],
                tokens_used=0
            )


async def analyze_problem_image(
    images: List[str],
    language: str = "ko",
    additional_context: Optional[str] = None
) -> ImageAnalysisResult:
    """
    편의 함수 - 이미지 분석 실행

    Args:
        images: base64 인코딩된 이미지 리스트
        language: 응답 언어
        additional_context: 추가 컨텍스트

    Returns:
        ImageAnalysisResult: 분석 결과
    """
    analyzer = ImageAnalyzer(language=language)
    return await analyzer.analyze_images(images, additional_context)
