"""
GPT Vision API Service for 3D Print Failure Analysis

This module provides real-time AI-powered analysis of print failures using OpenAI's GPT-4 Vision.
When a failure is detected, it analyzes the failure image and provides:
- Detailed description (30-50+ characters in Korean)
- Root cause analysis
- Suggested immediate action
- Prevention tips for future prints
"""

import os
import base64
import logging
from typing import Dict, Optional, Any
from pathlib import Path
import asyncio
from datetime import datetime

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("WARNING: openai package not installed. Run: pip install openai")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class GPTVisionAnalyzer:
    """
    Analyzes 3D print failure images using GPT-4 Vision API.

    Provides detailed Korean descriptions and actionable insights for detected failures.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        max_tokens: int = 500,
        temperature: float = 0.3
    ):
        """
        Initialize GPT Vision Analyzer.

        Args:
            api_key: OpenAI API key (defaults to env OPENAI_API_KEY)
            model: GPT model to use (gpt-4o, gpt-4-vision-preview, etc.)
            max_tokens: Maximum tokens for response
            temperature: Sampling temperature (0.0-1.0, lower = more focused)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package is required. Install with: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file")

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.max_tokens = max_tokens or int(os.getenv("OPENAI_MAX_TOKENS", "500"))
        self.temperature = temperature or float(os.getenv("OPENAI_TEMPERATURE", "0.3"))

        self.client = AsyncOpenAI(api_key=self.api_key)

        logger.info(f"[GPT Vision] Initialized with model={self.model}, max_tokens={self.max_tokens}")

    def _encode_image_to_base64(self, image_path: str) -> str:
        """
        Encode image file to base64 string.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _build_analysis_prompt(
        self,
        failure_type: str,
        confidence: float,
        print_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build optimized Korean prompt for failure analysis.

        Args:
            failure_type: Detected failure type (e.g., 'spaghetti', 'layer_shift')
            confidence: Detection confidence (0.0-1.0)
            print_context: Optional print parameters (temp, layer, speed, etc.)

        Returns:
            Korean prompt string
        """
        # Print context formatting
        context_info = ""
        if print_context:
            context_parts = []
            if print_context.get("layer_number"):
                context_parts.append(f"레이어: {print_context['layer_number']}")
            if print_context.get("print_progress"):
                context_parts.append(f"진행률: {print_context['print_progress']:.1f}%")
            if print_context.get("nozzle_temp"):
                context_parts.append(f"노즐 온도: {print_context['nozzle_temp']}°C")
            if print_context.get("bed_temp"):
                context_parts.append(f"베드 온도: {print_context['bed_temp']}°C")
            if print_context.get("print_speed"):
                context_parts.append(f"출력 속도: {print_context['print_speed']}mm/s")

            if context_parts:
                context_info = f"\n\n**출력 상태 정보:**\n" + "\n".join(f"- {p}" for p in context_parts)

        prompt = f"""당신은 3D 프린터 전문가입니다. 아래 이미지를 분석하여 출력 불량 상황을 진단해주세요.

**감지된 불량 유형:** {failure_type} (신뢰도: {confidence*100:.1f}%)
{context_info}

다음 형식으로 **한국어**로 답변해주세요:

1. **상황 설명** (30-50자 이상): 이미지에서 관찰되는 불량 현상을 구체적으로 설명
2. **원인 분석** (20-40자): 불량이 발생한 가능성이 높은 근본 원인
3. **즉시 조치** (15-30자): 지금 당장 취해야 할 조치 (출력 중지, 일시정지, 계속 등)
4. **예방 방법** (30-50자): 향후 같은 문제를 방지하기 위한 구체적인 팁

**중요:** 각 항목은 명확하고 실행 가능한 내용으로 작성하되, 최소 글자 수를 반드시 지켜주세요.
출력물의 품질과 사용자의 비용 절감을 위해 정확하고 구체적인 조언을 제공해주세요."""

        return prompt

    async def analyze_failure_image(
        self,
        image_path: str,
        failure_type: str,
        confidence: float,
        print_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Analyze failure image and return detailed Korean analysis.

        Args:
            image_path: Path to failure image file
            failure_type: Detected failure type
            confidence: Detection confidence (0.0-1.0)
            print_context: Optional print parameters

        Returns:
            Dictionary with:
                - description: 상황 설명 (30-50+ chars)
                - root_cause: 원인 분석 (20-40 chars)
                - suggested_action: 즉시 조치 (15-30 chars)
                - prevention_tips: 예방 방법 (30-50+ chars)
                - raw_response: Full GPT response

        Raises:
            FileNotFoundError: If image file doesn't exist
            Exception: If API call fails
        """
        start_time = datetime.now()

        # Validate image file
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        logger.info(f"[GPT Vision] Analyzing failure: {failure_type} (confidence={confidence:.2f})")

        try:
            # Encode image
            base64_image = self._encode_image_to_base64(image_path)

            # Build prompt
            prompt = self._build_analysis_prompt(failure_type, confidence, print_context)

            # Call GPT-4 Vision API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"  # High detail for better analysis
                                }
                            }
                        ]
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            # Extract response
            raw_response = response.choices[0].message.content

            # Parse structured response
            parsed = self._parse_gpt_response(raw_response)
            parsed["raw_response"] = raw_response

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"[GPT Vision] Analysis completed in {elapsed:.2f}s")

            return parsed

        except Exception as e:
            logger.error(f"[GPT Vision] Analysis failed: {e}")
            raise

    def _parse_gpt_response(self, response: str) -> Dict[str, str]:
        """
        Parse GPT response into structured fields.

        Args:
            response: Raw GPT response text

        Returns:
            Dictionary with description, root_cause, suggested_action, prevention_tips
        """
        result = {
            "description": "",
            "root_cause": "",
            "suggested_action": "",
            "prevention_tips": ""
        }

        lines = response.strip().split('\n')
        current_key = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect section headers
            if "상황 설명" in line or "1." in line:
                current_key = "description"
                # Extract content after colon if present
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        result[current_key] = content
                continue
            elif "원인 분석" in line or "2." in line:
                current_key = "root_cause"
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        result[current_key] = content
                continue
            elif "즉시 조치" in line or "3." in line:
                current_key = "suggested_action"
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        result[current_key] = content
                continue
            elif "예방 방법" in line or "4." in line:
                current_key = "prevention_tips"
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        result[current_key] = content
                continue

            # Append content to current section
            if current_key and line:
                # Remove markdown formatting and bullet points
                clean_line = line.lstrip('-*•').strip()
                if clean_line:
                    if result[current_key]:
                        result[current_key] += " " + clean_line
                    else:
                        result[current_key] = clean_line

        # Fallback: if parsing failed, use entire response as description
        if not result["description"] and response:
            result["description"] = response[:200]  # First 200 chars

        return result

    async def analyze_failure_from_url(
        self,
        image_url: str,
        failure_type: str,
        confidence: float,
        print_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Analyze failure image from URL (Supabase Storage, etc.).

        Args:
            image_url: Public URL to failure image
            failure_type: Detected failure type
            confidence: Detection confidence (0.0-1.0)
            print_context: Optional print parameters

        Returns:
            Dictionary with analysis results
        """
        start_time = datetime.now()

        logger.info(f"[GPT Vision] Analyzing failure from URL: {failure_type}")

        try:
            # Build prompt
            prompt = self._build_analysis_prompt(failure_type, confidence, print_context)

            # Call GPT-4 Vision API with URL
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            # Extract and parse response
            raw_response = response.choices[0].message.content
            parsed = self._parse_gpt_response(raw_response)
            parsed["raw_response"] = raw_response

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"[GPT Vision] Analysis completed in {elapsed:.2f}s")

            return parsed

        except Exception as e:
            logger.error(f"[GPT Vision] Analysis failed: {e}")
            raise


# ============================================================================
# Standalone Test Function
# ============================================================================

async def test_gpt_vision_analyzer():
    """Test GPT Vision analyzer with a sample image."""
    print("=" * 80)
    print("GPT Vision Analyzer Test")
    print("=" * 80)

    # Initialize analyzer
    try:
        analyzer = GPTVisionAnalyzer()
        print(f"✅ Analyzer initialized: model={analyzer.model}")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # Test with sample failure
    test_image = "./output/test_failure.jpg"  # Replace with actual test image

    if not os.path.exists(test_image):
        print(f"⚠️  Test image not found: {test_image}")
        print("   Please provide a test failure image to run this test")
        return

    print(f"\n📸 Analyzing image: {test_image}")

    try:
        result = await analyzer.analyze_failure_image(
            image_path=test_image,
            failure_type="spaghetti",
            confidence=0.87,
            print_context={
                "layer_number": 152,
                "print_progress": 45.3,
                "nozzle_temp": 210,
                "bed_temp": 60,
                "print_speed": 50
            }
        )

        print("\n" + "=" * 80)
        print("📊 ANALYSIS RESULTS")
        print("=" * 80)
        print(f"\n1️⃣ 상황 설명 ({len(result['description'])}자):")
        print(f"   {result['description']}")
        print(f"\n2️⃣ 원인 분석 ({len(result['root_cause'])}자):")
        print(f"   {result['root_cause']}")
        print(f"\n3️⃣ 즉시 조치 ({len(result['suggested_action'])}자):")
        print(f"   {result['suggested_action']}")
        print(f"\n4️⃣ 예방 방법 ({len(result['prevention_tips'])}자):")
        print(f"   {result['prevention_tips']}")
        print("\n" + "=" * 80)
        print("✅ Test completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_gpt_vision_analyzer())
