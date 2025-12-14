"""
3D Printer Real-time Monitoring Test
=====================================
웹캠 스트림을 통한 3D 프린터 실시간 상태 모니터링 시스템

사용법:
    python printer_monitor_test.py --webcam-url "http://192.168.1.100/webcam/?action=snapshot"
    python printer_monitor_test.py --webcam-url "http://localhost:8080/shot.jpg" --interval 30
"""

import os
import sys
import asyncio
import base64
import time
import io
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

# Third-party imports
import dotenv
import httpx
from PIL import Image
from pydantic import BaseModel, Field

# LangChain/LangGraph imports
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage

# 기존 LLM 클라이언트 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcode_analyzer.llm.client import get_llm_client

# 환경변수 로드
dotenv.load_dotenv()


# =============================================================================
# 1. 데이터 모델 정의
# =============================================================================

class PrinterDecision(str, Enum):
    """프린터 상태 결정"""
    CONTINUE = "CONTINUE"  # 정상 진행
    WARNING = "WARNING"    # 경고 (사용자 확인 필요)
    STOP = "STOP"          # 즉시 중지 권장


class SensorData(BaseModel):
    """센서 데이터 (시뮬레이션)"""
    nozzle_temp: float = Field(description="노즐 온도 (°C)")
    bed_temp: float = Field(description="베드 온도 (°C)")
    ambient_temp: float = Field(description="주변 온도 (°C)")
    layer_current: int = Field(description="현재 레이어")
    layer_total: int = Field(description="총 레이어")
    print_progress: float = Field(description="프린트 진행률 (%)")
    filament_used: float = Field(description="사용된 필라멘트 (mm)")
    print_time_elapsed: int = Field(description="경과 시간 (초)")
    fan_speed: int = Field(description="팬 속도 (%)")


class IssueDetected(BaseModel):
    """감지된 이슈"""
    issue_type: str = Field(description="이슈 유형")
    severity: Literal["low", "medium", "high", "critical"] = Field(description="심각도")
    description: str = Field(description="이슈 설명")
    confidence: float = Field(description="신뢰도 (0-1)")


class MonitorResult(BaseModel):
    """모니터링 결과"""
    timestamp: str = Field(description="분석 시간")
    decision: PrinterDecision = Field(description="결정")
    confidence: float = Field(description="결정 신뢰도")
    issues_detected: List[IssueDetected] = Field(default_factory=list, description="감지된 이슈들")
    summary: str = Field(description="상황 요약")
    recommended_action: str = Field(description="권장 조치")
    analysis_details: Dict[str, Any] = Field(default_factory=dict, description="분석 세부사항")


# =============================================================================
# 2. LangGraph 상태 정의
# =============================================================================

class MonitorState(TypedDict):
    """모니터링 워크플로우 상태"""
    # 입력
    webcam_url: str
    cycle_number: int

    # 수집된 데이터
    captured_image: Optional[bytes]  # 캡처된 이미지 (바이트)
    image_base64: Optional[str]       # Base64 인코딩된 이미지
    sensor_data: Optional[Dict[str, Any]]
    capture_timestamp: str

    # 분석 결과
    vision_analysis: Optional[Dict[str, Any]]
    state_synthesis: Optional[Dict[str, Any]]

    # 최종 결과
    decision: Optional[str]
    confidence: float
    issues: List[Dict[str, Any]]
    summary: str
    recommended_action: str

    # 메타
    error: Optional[str]
    processing_time: float


# =============================================================================
# 3. 이미지 캡처 모듈
# =============================================================================

async def capture_webcam_image(url: str, timeout: float = 10.0) -> tuple[Optional[bytes], Optional[str]]:
    """
    웹캠 URL에서 이미지 캡처

    Args:
        url: 웹캠 스냅샷 URL
        timeout: 타임아웃 (초)

    Returns:
        (image_bytes, error_message)
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Content-Type 확인
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type.lower():
                # MJPEG 스트림에서 단일 프레임 추출 시도
                if response.content[:2] == b'\xff\xd8':  # JPEG SOI marker
                    return response.content, None
                return None, f"Invalid content type: {content_type}"

            return response.content, None

    except httpx.TimeoutException:
        return None, f"Timeout connecting to webcam: {url}"
    except httpx.HTTPStatusError as e:
        return None, f"HTTP error {e.response.status_code}: {url}"
    except Exception as e:
        return None, f"Failed to capture image: {str(e)}"


def image_to_base64(image_bytes: bytes) -> str:
    """이미지 바이트를 base64로 인코딩"""
    return base64.b64encode(image_bytes).decode("utf-8")


def resize_image_if_needed(image_bytes: bytes, max_size: int = 1024) -> bytes:
    """이미지가 너무 크면 리사이즈"""
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # 이미 작으면 그대로 반환
        if img.width <= max_size and img.height <= max_size:
            return image_bytes

        # 비율 유지하며 리사이즈
        ratio = min(max_size / img.width, max_size / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)

        # 바이트로 변환
        buffer = io.BytesIO()
        img_resized.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    except Exception:
        return image_bytes


# =============================================================================
# 4. 센서 시뮬레이터
# =============================================================================

class SensorSimulator:
    """센서 데이터 시뮬레이터 (테스트용)"""

    def __init__(self, total_layers: int = 100):
        self.total_layers = total_layers
        self.current_layer = 0
        self.start_time = time.time()
        self.print_started = False

    def start_print(self):
        """프린트 시작"""
        self.print_started = True
        self.start_time = time.time()
        self.current_layer = 0

    def get_sensor_data(self) -> SensorData:
        """현재 센서 데이터 반환"""
        import random

        elapsed = int(time.time() - self.start_time) if self.print_started else 0

        # 프린트 진행에 따른 레이어 증가 (시뮬레이션)
        if self.print_started:
            self.current_layer = min(
                self.current_layer + random.randint(0, 2),
                self.total_layers
            )

        progress = (self.current_layer / self.total_layers * 100) if self.total_layers > 0 else 0

        # 랜덤 변동을 포함한 센서값 시뮬레이션
        return SensorData(
            nozzle_temp=200.0 + random.uniform(-5, 5),
            bed_temp=60.0 + random.uniform(-3, 3),
            ambient_temp=25.0 + random.uniform(-2, 2),
            layer_current=self.current_layer,
            layer_total=self.total_layers,
            print_progress=round(progress, 1),
            filament_used=round(self.current_layer * 15.5, 1),  # 대략적 추정
            print_time_elapsed=elapsed,
            fan_speed=100 if self.current_layer > 2 else 0
        )

    def inject_anomaly(self, anomaly_type: str):
        """테스트용 이상 상황 주입"""
        # 추후 구현: 온도 급등, 필라멘트 부족 등
        pass


# =============================================================================
# 5. LangGraph 노드 구현
# =============================================================================

async def capture_data_node(state: MonitorState) -> Dict[str, Any]:
    """
    데이터 수집 노드: 이미지 캡처 + 센서 데이터 수집
    """
    webcam_url = state.get("webcam_url", "")
    timestamp = datetime.now().isoformat()

    # 이미지 캡처
    image_bytes, error = await capture_webcam_image(webcam_url)

    if error:
        return {
            "captured_image": None,
            "image_base64": None,
            "capture_timestamp": timestamp,
            "error": error
        }

    # 이미지 리사이즈 및 Base64 인코딩
    image_bytes = resize_image_if_needed(image_bytes)
    image_b64 = image_to_base64(image_bytes)

    return {
        "captured_image": image_bytes,
        "image_base64": image_b64,
        "capture_timestamp": timestamp,
        "error": None
    }


async def vision_analysis_node(state: MonitorState) -> Dict[str, Any]:
    """
    비전 분석 노드: LLM을 통한 이미지 분석
    """
    image_b64 = state.get("image_base64")
    sensor_data = state.get("sensor_data", {})

    if not image_b64:
        return {
            "vision_analysis": {
                "status": "skipped",
                "reason": "No image captured"
            }
        }

    # LLM 클라이언트 가져오기
    llm = get_llm_client(temperature=0.1, max_output_tokens=2048)

    # 비전 분석 프롬프트
    system_prompt = """You are an expert 3D printer monitoring system.
Analyze the provided image of a 3D printer in operation and identify any issues.

Focus on detecting:
1. Print Quality Issues: Layer shifting, warping, stringing, under-extrusion, over-extrusion
2. Mechanical Issues: Bed adhesion problems, nozzle clogs, belt issues
3. Safety Concerns: Smoke, fire, unusual debris, filament tangles
4. Print Progress: Whether the print appears normal and progressing

Respond in JSON format:
{
    "print_status": "normal|warning|critical",
    "issues_detected": [
        {
            "type": "issue_type",
            "severity": "low|medium|high|critical",
            "description": "detailed description",
            "confidence": 0.0-1.0
        }
    ],
    "print_quality_score": 0-100,
    "observations": "general observations about the print",
    "immediate_action_needed": true|false
}
"""

    sensor_context = ""
    if sensor_data:
        sensor_context = f"""
Current Sensor Data:
- Nozzle Temp: {sensor_data.get('nozzle_temp', 'N/A')}°C
- Bed Temp: {sensor_data.get('bed_temp', 'N/A')}°C
- Layer: {sensor_data.get('layer_current', 'N/A')}/{sensor_data.get('layer_total', 'N/A')}
- Progress: {sensor_data.get('print_progress', 'N/A')}%
- Fan Speed: {sensor_data.get('fan_speed', 'N/A')}%
"""

    # Gemini Vision API 호출
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=[
                {"type": "text", "text": f"Analyze this 3D printer image:{sensor_context}"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }
                }
            ])
        ]

        response = await llm.ainvoke(messages)

        # JSON 파싱 시도
        import json
        content = response.content

        # JSON 블록 추출
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        try:
            analysis = json.loads(content.strip())
        except json.JSONDecodeError:
            analysis = {
                "print_status": "unknown",
                "raw_response": response.content,
                "parse_error": True
            }

        return {"vision_analysis": analysis}

    except Exception as e:
        return {
            "vision_analysis": {
                "status": "error",
                "error": str(e)
            }
        }


async def state_synthesis_node(state: MonitorState) -> Dict[str, Any]:
    """
    상태 종합 노드: 비전 분석 + 센서 데이터 종합
    """
    vision = state.get("vision_analysis", {})
    sensor = state.get("sensor_data", {})

    # 종합 점수 계산
    vision_score = vision.get("print_quality_score", 50) if isinstance(vision.get("print_quality_score"), (int, float)) else 50

    # 센서 기반 점수 조정
    sensor_score = 100
    if sensor:
        nozzle_temp = sensor.get("nozzle_temp", 200)
        bed_temp = sensor.get("bed_temp", 60)

        # 온도 이상 체크
        if nozzle_temp < 180 or nozzle_temp > 260:
            sensor_score -= 30
        if bed_temp < 40 or bed_temp > 100:
            sensor_score -= 20

    # 종합 점수
    combined_score = (vision_score * 0.7 + sensor_score * 0.3)

    # 이슈 통합
    all_issues = vision.get("issues_detected", [])

    # 센서 기반 이슈 추가
    if sensor:
        if sensor.get("nozzle_temp", 200) > 250:
            all_issues.append({
                "type": "temperature_high",
                "severity": "high",
                "description": f"노즐 온도가 너무 높음: {sensor.get('nozzle_temp')}°C",
                "confidence": 0.95,
                "source": "sensor"
            })

    return {
        "state_synthesis": {
            "combined_score": round(combined_score, 1),
            "vision_score": vision_score,
            "sensor_score": sensor_score,
            "total_issues": len(all_issues),
            "critical_issues": sum(1 for i in all_issues if i.get("severity") == "critical"),
            "high_issues": sum(1 for i in all_issues if i.get("severity") == "high"),
            "all_issues": all_issues
        }
    }


async def decision_node(state: MonitorState) -> Dict[str, Any]:
    """
    결정 노드: 최종 판단 (CONTINUE/WARNING/STOP)
    """
    synthesis = state.get("state_synthesis", {})
    vision = state.get("vision_analysis", {})

    score = synthesis.get("combined_score", 50)
    critical = synthesis.get("critical_issues", 0)
    high = synthesis.get("high_issues", 0)

    # 결정 로직
    if critical > 0 or vision.get("immediate_action_needed", False):
        decision = PrinterDecision.STOP
        confidence = 0.95
        recommended = "즉시 프린트를 중지하고 프린터를 점검하세요."
    elif high > 0 or score < 60:
        decision = PrinterDecision.WARNING
        confidence = 0.8
        recommended = "프린터 상태를 확인하고, 문제가 지속되면 중지를 고려하세요."
    else:
        decision = PrinterDecision.CONTINUE
        confidence = min(score / 100, 0.95)
        recommended = "프린트가 정상적으로 진행 중입니다. 계속 모니터링합니다."

    # 요약 생성
    issues = synthesis.get("all_issues", [])
    if issues:
        issue_summary = ", ".join([f"{i.get('type', 'unknown')}({i.get('severity', 'unknown')})" for i in issues[:3]])
        summary = f"감지된 이슈: {issue_summary}. 종합 점수: {score}/100"
    else:
        summary = f"정상 작동 중. 종합 점수: {score}/100"

    return {
        "decision": decision.value,
        "confidence": confidence,
        "issues": issues,
        "summary": summary,
        "recommended_action": recommended
    }


# =============================================================================
# 6. LangGraph 워크플로우 정의
# =============================================================================

def create_monitor_workflow() -> StateGraph:
    """모니터링 워크플로우 생성"""
    workflow = StateGraph(MonitorState)

    # 노드 추가
    workflow.add_node("capture_data", capture_data_node)
    workflow.add_node("vision_analysis", vision_analysis_node)
    workflow.add_node("state_synthesis", state_synthesis_node)
    workflow.add_node("decision", decision_node)

    # 엣지 연결
    workflow.set_entry_point("capture_data")

    # 캡처 실패 시 분기
    def check_capture(state: MonitorState) -> str:
        if state.get("error"):
            return "decision"  # 에러 시 바로 결정으로
        return "vision_analysis"

    workflow.add_conditional_edges(
        "capture_data",
        check_capture,
        {
            "vision_analysis": "vision_analysis",
            "decision": "decision"
        }
    )

    workflow.add_edge("vision_analysis", "state_synthesis")
    workflow.add_edge("state_synthesis", "decision")
    workflow.add_edge("decision", END)

    return workflow


def compile_monitor_workflow():
    """워크플로우 컴파일"""
    workflow = create_monitor_workflow()
    return workflow.compile()


# =============================================================================
# 7. 메인 모니터링 루프
# =============================================================================

class PrinterMonitor:
    """3D 프린터 모니터링 클래스"""

    def __init__(self, webcam_url: str, interval_seconds: int = 60):
        self.webcam_url = webcam_url
        self.interval = interval_seconds
        self.workflow = compile_monitor_workflow()
        self.sensor_sim = SensorSimulator(total_layers=100)
        self.is_running = False
        self.cycle_count = 0
        self.history: List[MonitorResult] = []

    async def run_single_cycle(self) -> MonitorResult:
        """단일 모니터링 사이클 실행"""
        self.cycle_count += 1
        start_time = time.time()

        # 센서 데이터 수집
        sensor_data = self.sensor_sim.get_sensor_data()

        # 초기 상태
        initial_state: MonitorState = {
            "webcam_url": self.webcam_url,
            "cycle_number": self.cycle_count,
            "captured_image": None,
            "image_base64": None,
            "sensor_data": sensor_data.model_dump(),
            "capture_timestamp": "",
            "vision_analysis": None,
            "state_synthesis": None,
            "decision": None,
            "confidence": 0.0,
            "issues": [],
            "summary": "",
            "recommended_action": "",
            "error": None,
            "processing_time": 0.0
        }

        # 워크플로우 실행
        result = await self.workflow.ainvoke(initial_state)

        processing_time = time.time() - start_time

        # 결과 구성
        monitor_result = MonitorResult(
            timestamp=result.get("capture_timestamp", datetime.now().isoformat()),
            decision=PrinterDecision(result.get("decision", "CONTINUE")),
            confidence=result.get("confidence", 0.0),
            issues_detected=[
                IssueDetected(**i) for i in result.get("issues", [])
                if all(k in i for k in ["issue_type", "severity", "description", "confidence"]) or
                   all(k in i for k in ["type", "severity", "description", "confidence"])
            ],
            summary=result.get("summary", ""),
            recommended_action=result.get("recommended_action", ""),
            analysis_details={
                "cycle": self.cycle_count,
                "processing_time": round(processing_time, 2),
                "sensor_data": sensor_data.model_dump(),
                "vision_analysis": result.get("vision_analysis"),
                "error": result.get("error")
            }
        )

        self.history.append(monitor_result)
        return monitor_result

    async def start(self, max_cycles: Optional[int] = None):
        """모니터링 시작"""
        self.is_running = True
        self.sensor_sim.start_print()

        print("\n" + "="*60)
        print("🖨️  3D Printer Monitor Started")
        print("="*60)
        print(f"📷 Webcam URL: {self.webcam_url}")
        print(f"⏱️  Interval: {self.interval} seconds")
        print(f"🔄 Max cycles: {max_cycles or 'Unlimited'}")
        print("="*60)
        print("\nPress Ctrl+C to stop\n")

        try:
            cycle = 0
            while self.is_running:
                if max_cycles and cycle >= max_cycles:
                    break

                print(f"\n--- Cycle {cycle + 1} ---")
                print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                result = await self.run_single_cycle()

                # 결과 출력
                self._print_result(result)

                # STOP 결정 시 자동 중지
                if result.decision == PrinterDecision.STOP:
                    print("\n🛑 STOP decision received. Monitoring paused.")
                    user_input = input("Continue monitoring? (y/n): ")
                    if user_input.lower() != 'y':
                        break

                cycle += 1

                if self.is_running and (max_cycles is None or cycle < max_cycles):
                    print(f"\n⏳ Next check in {self.interval} seconds...")
                    await asyncio.sleep(self.interval)

        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped by user")
        finally:
            self.is_running = False
            self._print_summary()

    def stop(self):
        """모니터링 중지"""
        self.is_running = False

    def _print_result(self, result: MonitorResult):
        """결과 출력"""
        # 결정에 따른 이모지
        decision_emoji = {
            PrinterDecision.CONTINUE: "✅",
            PrinterDecision.WARNING: "⚠️",
            PrinterDecision.STOP: "🛑"
        }

        emoji = decision_emoji.get(result.decision, "❓")

        print(f"\n{emoji} Decision: {result.decision.value} (confidence: {result.confidence:.1%})")
        print(f"📝 Summary: {result.summary}")
        print(f"💡 Action: {result.recommended_action}")

        if result.issues_detected:
            print(f"\n⚠️  Issues ({len(result.issues_detected)}):")
            for issue in result.issues_detected:
                print(f"   - [{issue.severity.upper()}] {issue.issue_type}: {issue.description}")

        # 센서 데이터
        sensor = result.analysis_details.get("sensor_data", {})
        if sensor:
            print(f"\n📊 Sensor Data:")
            print(f"   🌡️  Nozzle: {sensor.get('nozzle_temp', 'N/A'):.1f}°C | Bed: {sensor.get('bed_temp', 'N/A'):.1f}°C")
            print(f"   📈 Layer: {sensor.get('layer_current', 0)}/{sensor.get('layer_total', 0)} ({sensor.get('print_progress', 0):.1f}%)")

        if result.analysis_details.get("error"):
            print(f"\n❌ Error: {result.analysis_details['error']}")

    def _print_summary(self):
        """최종 요약 출력"""
        if not self.history:
            return

        print("\n" + "="*60)
        print("📊 Monitoring Session Summary")
        print("="*60)
        print(f"Total cycles: {len(self.history)}")

        decisions = [r.decision.value for r in self.history]
        print(f"CONTINUE: {decisions.count('CONTINUE')}")
        print(f"WARNING: {decisions.count('WARNING')}")
        print(f"STOP: {decisions.count('STOP')}")

        total_issues = sum(len(r.issues_detected) for r in self.history)
        print(f"Total issues detected: {total_issues}")
        print("="*60)


# =============================================================================
# 8. CLI 인터페이스
# =============================================================================

async def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="3D Printer Real-time Monitoring System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with webcam URL
  python printer_monitor_test.py --webcam-url "http://192.168.1.100/webcam/?action=snapshot"

  # Custom interval (30 seconds)
  python printer_monitor_test.py --webcam-url "http://localhost:8080/shot.jpg" --interval 30

  # Run only 5 cycles
  python printer_monitor_test.py --webcam-url "http://example.com/cam.jpg" --max-cycles 5

  # Test mode (simulated image)
  python printer_monitor_test.py --test-mode
        """
    )

    parser.add_argument(
        "--webcam-url",
        type=str,
        default="",
        help="Webcam snapshot URL (e.g., http://192.168.1.100/webcam/?action=snapshot)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Monitoring interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Maximum number of monitoring cycles (default: unlimited)"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode with simulated data"
    )

    args = parser.parse_args()

    # 테스트 모드
    if args.test_mode:
        print("\n🧪 Running in TEST MODE (simulated data)\n")
        args.webcam_url = "http://localhost:9999/test.jpg"  # 가상 URL
        args.max_cycles = 3
        args.interval = 5

    if not args.webcam_url:
        parser.print_help()
        print("\n❌ Error: --webcam-url is required (or use --test-mode)")
        sys.exit(1)

    # 모니터 시작
    monitor = PrinterMonitor(
        webcam_url=args.webcam_url,
        interval_seconds=args.interval
    )

    await monitor.start(max_cycles=args.max_cycles)


if __name__ == "__main__":
    asyncio.run(main())
