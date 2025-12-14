"""
3D 프린터 실시간 모니터링 테스트
=================================
- 실행 시 웹캠 화면 표시
- CLI에서 'start' 입력 시 LLM 분석 시작
- 'q' 또는 'quit'로 종료

사용법:
    python test_monitor_local.py --source webcam
    python test_monitor_local.py --source "C:/path/to/images"
    python test_monitor_local.py --source "http://192.168.1.100/webcam/?action=stream"
"""
import asyncio
import base64
import json
import sys
import os
import io
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from queue import Queue
from enum import Enum

# Windows 콘솔 UTF-8 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 환경 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dotenv
dotenv.load_dotenv()

import cv2
import numpy as np
import httpx
from PIL import Image, ImageDraw, ImageFont
from langchain_core.messages import HumanMessage, SystemMessage

# 한글 폰트 설정
def get_korean_font(size: int = 14):
    """한글 지원 폰트 로드"""
    font_paths = [
        "C:/Windows/Fonts/malgun.ttf",      # 맑은 고딕
        "C:/Windows/Fonts/gulim.ttc",        # 굴림
        "C:/Windows/Fonts/NanumGothic.ttf",  # 나눔고딕
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()

# 전역 폰트 캐시
_font_cache = {}

def get_cached_font(size: int = 14):
    if size not in _font_cache:
        _font_cache[size] = get_korean_font(size)
    return _font_cache[size]

def put_korean_text(frame: np.ndarray, text: str, position: tuple,
                    font_size: int = 14, color: tuple = (255, 255, 255)) -> np.ndarray:
    """OpenCV 프레임에 한글 텍스트 그리기"""
    # BGR -> RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(frame_rgb)
    draw = ImageDraw.Draw(pil_image)

    font = get_cached_font(font_size)
    # OpenCV BGR -> PIL RGB 색상 변환
    rgb_color = (color[2], color[1], color[0])
    draw.text(position, text, font=font, fill=rgb_color)

    # RGB -> BGR
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from gcode_analyzer.llm.client import get_llm_client


# =============================================================================
# 프린터 API 설정
# =============================================================================

class PrinterAPIConfig:
    """프린터 API 설정"""
    BASE_URL = "http://localhost:5000"
    DEVICE_UUID = "2a89b98c-983d-487d-9250-b59b32f66866"
    TIMEOUT = 10.0


# =============================================================================
# 프린터 API 클라이언트
# =============================================================================

class PrinterAPIClient:
    """프린터 제어 API 클라이언트"""

    def __init__(self, base_url: str = None, device_uuid: str = None):
        self.base_url = base_url or PrinterAPIConfig.BASE_URL
        self.device_uuid = device_uuid or PrinterAPIConfig.DEVICE_UUID

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/api/printer/{self.device_uuid}/{endpoint}"

    async def _get(self, endpoint: str) -> dict:
        async with httpx.AsyncClient(timeout=PrinterAPIConfig.TIMEOUT) as client:
            response = await client.get(self._url(endpoint))
            response.raise_for_status()
            return response.json()

    async def _post(self, endpoint: str, data: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=PrinterAPIConfig.TIMEOUT) as client:
            response = await client.post(self._url(endpoint), json=data or {})
            response.raise_for_status()
            return response.json()

    # 상태 조회
    async def get_status(self) -> dict:
        """프린터 상태 조회"""
        return await self._get("status")

    # 온도 제어
    async def set_temperature(self, nozzle: float = None, bed: float = None) -> dict:
        """노즐 + 베드 온도 동시 설정"""
        data = {}
        if nozzle is not None: data["nozzle"] = nozzle
        if bed is not None: data["bed"] = bed
        return await self._post("temperature", data)

    async def set_nozzle_temp(self, temperature: float) -> dict:
        """노즐 온도 설정"""
        return await self._post("nozzle-temp", {"temperature": temperature})

    async def set_bed_temp(self, temperature: float) -> dict:
        """베드 온도 설정"""
        return await self._post("bed-temp", {"temperature": temperature})

    # 속도 제어
    async def set_feed_rate(self, rate: int) -> dict:
        """피드레이트 설정 (10-500%)"""
        return await self._post("feed-rate", {"rate": max(10, min(500, rate))})

    async def set_flow_rate(self, rate: int) -> dict:
        """플로우레이트 설정 (10-200%)"""
        return await self._post("flow-rate", {"rate": max(10, min(200, rate))})

    # 프린팅 제어
    async def pause(self) -> dict:
        return await self._post("pause")

    async def resume(self) -> dict:
        return await self._post("resume")

    async def cancel(self) -> dict:
        return await self._post("cancel")

    async def home(self, axes: str = "XYZ") -> dict:
        return await self._post("home", {"axes": axes})

    # 이동 및 G-code
    async def move(self, x: float = None, y: float = None, z: float = None,
                   e: float = None, feedrate: float = None, mode: str = "relative") -> dict:
        data = {"mode": mode}
        if x is not None: data["x"] = x
        if y is not None: data["y"] = y
        if z is not None: data["z"] = z
        if e is not None: data["e"] = e
        if feedrate is not None: data["feedrate"] = feedrate
        return await self._post("move", data)

    async def send_gcode(self, commands: list) -> dict:
        """G-code 명령 전송 (여러 명령 가능)"""
        if isinstance(commands, str):
            commands = [commands]
        return await self._post("gcode", {"commands": commands})


# 전역 프린터 클라이언트
printer_client = PrinterAPIClient()


# =============================================================================
# LangChain 툴 정의
# =============================================================================

@tool
async def get_printer_status() -> str:
    """
    프린터의 현재 상태를 조회합니다.
    온도, 진행률, 프린트 상태 등의 정보를 반환합니다.
    """
    try:
        status = await printer_client.get_status()
        return json.dumps(status, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def pause_print() -> str:
    """
    현재 프린트를 일시정지합니다.
    """
    try:
        result = await printer_client.pause()
        return f"프린트 일시정지 완료: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def resume_print() -> str:
    """
    일시정지된 프린트를 재개합니다.
    """
    try:
        result = await printer_client.resume()
        return f"프린트 재개 완료: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def cancel_print() -> str:
    """
    현재 프린트를 취소합니다. 주의: 이 작업은 되돌릴 수 없습니다.
    """
    try:
        result = await printer_client.cancel()
        return f"프린트 취소 완료: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def set_nozzle_temperature(temperature: float) -> str:
    """
    노즐 온도를 설정합니다.

    Args:
        temperature: 목표 온도 (°C). 일반적으로 PLA는 190-210, ABS는 230-250
    """
    try:
        result = await printer_client.set_nozzle_temp(temperature)
        return f"노즐 온도 {temperature}°C로 설정: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def set_bed_temperature(temperature: float) -> str:
    """
    베드 온도를 설정합니다.

    Args:
        temperature: 목표 온도 (°C). 일반적으로 PLA는 50-60, ABS는 80-100
    """
    try:
        result = await printer_client.set_bed_temp(temperature)
        return f"베드 온도 {temperature}°C로 설정: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def set_print_speed(rate: int) -> str:
    """
    프린트 속도(피드레이트)를 조절합니다.

    Args:
        rate: 속도 비율 (10-500%). 100이 기본 속도입니다.
    """
    try:
        result = await printer_client.set_feed_rate(rate)
        return f"프린트 속도 {rate}%로 설정: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def set_extrusion_flow(rate: int) -> str:
    """
    압출량(플로우레이트)을 조절합니다.

    Args:
        rate: 압출량 비율 (10-200%). 100이 기본 압출량입니다.
    """
    try:
        result = await printer_client.set_flow_rate(rate)
        return f"압출량 {rate}%로 설정: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def home_printer(axes: str = "XYZ") -> str:
    """
    프린터를 홈 위치로 이동합니다.

    Args:
        axes: 홈으로 이동할 축. "X", "Y", "Z", "XY", "XYZ" 등 조합 가능. 기본값은 "XYZ"
    """
    try:
        result = await printer_client.home(axes)
        return f"홈 이동 완료 ({axes}): {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def send_gcode_command(command: str) -> str:
    """
    G-code 명령을 직접 프린터로 전송합니다.

    Args:
        command: G-code 명령어 (예: "G28", "M104 S200", "G1 X10 Y10 F3000")
    """
    try:
        result = await printer_client.send_gcode(command)
        return f"G-code '{command}' 전송 완료: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
async def move_axis(x: float = None, y: float = None, z: float = None,
                    feedrate: float = 3000, relative: bool = True) -> str:
    """
    프린터 헤드를 이동합니다.

    Args:
        x: X축 이동량 (mm)
        y: Y축 이동량 (mm)
        z: Z축 이동량 (mm)
        feedrate: 이동 속도 (mm/min). 기본값 3000
        relative: True면 상대 이동, False면 절대 좌표. 기본값 True
    """
    try:
        mode = "relative" if relative else "absolute"
        result = await printer_client.move(x=x, y=y, z=z, feedrate=feedrate, mode=mode)
        move_desc = []
        if x is not None: move_desc.append(f"X:{x}")
        if y is not None: move_desc.append(f"Y:{y}")
        if z is not None: move_desc.append(f"Z:{z}")
        return f"이동 완료 ({', '.join(move_desc)}, {mode}): {result}"
    except Exception as e:
        return f"Error: {str(e)}"


# 사용 가능한 모든 툴 목록
PRINTER_TOOLS = [
    get_printer_status,
    pause_print,
    resume_print,
    cancel_print,
    set_nozzle_temperature,
    set_bed_temperature,
    set_print_speed,
    set_extrusion_flow,
    home_printer,
    send_gcode_command,
    move_axis,
]


# =============================================================================
# 상수 및 설정
# =============================================================================

class MonitorState(Enum):
    IDLE = "idle"           # 대기 중 (웹캠만 표시)
    MONITORING = "monitoring"  # 모니터링 중 (주기적 분석)
    STOPPED = "stopped"     # 종료


class Config:
    """설정"""
    # 데이터 수집 주기
    STATUS_POLL_INTERVAL = 5     # API 상태 폴링 간격 (초)
    IMAGE_CAPTURE_INTERVAL = 15  # 이미지 캡처 간격 (초) - 15초
    LLM_ANALYSIS_INTERVAL = 60   # LLM 분석 간격 (초) = 1분

    # 수집 버퍼 크기 (1분 기준)
    MAX_STATUS_HISTORY = 12      # 12개 = 1분/5초
    MAX_IMAGE_HISTORY = 4        # 4장 = 1분/15초

    WINDOW_NAME = "3D Printer Monitor"
    DEFAULT_CAMERA = 0

    # 언어 설정 (ko, en, ja, zh)
    LANGUAGE = "ko"


# =============================================================================
# 이미지 소스 관리
# =============================================================================

class ImageSource:
    """이미지 소스 추상 클래스"""
    def get_frame(self) -> Optional[np.ndarray]:
        raise NotImplementedError

    def release(self):
        pass


class WebcamSource(ImageSource):
    """웹캠 소스"""
    def __init__(self, camera_id: int = 0):
        self.cap = cv2.VideoCapture(camera_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"웹캠을 열 수 없습니다: {camera_id}")
        print(f"[INFO] 웹캠 연결됨: {camera_id}")

    def get_frame(self) -> Optional[np.ndarray]:
        ret, frame = self.cap.read()
        return frame if ret else None

    def release(self):
        self.cap.release()


class URLStreamSource(ImageSource):
    """URL 스트림 소스 (MJPEG 등)"""
    def __init__(self, url: str):
        self.cap = cv2.VideoCapture(url)
        if not self.cap.isOpened():
            raise RuntimeError(f"스트림을 열 수 없습니다: {url}")
        print(f"[INFO] 스트림 연결됨: {url}")

    def get_frame(self) -> Optional[np.ndarray]:
        ret, frame = self.cap.read()
        return frame if ret else None

    def release(self):
        self.cap.release()


class SnapshotURLSource(ImageSource):
    """스냅샷 URL 소스 (단일 이미지 URL을 주기적으로 가져옴)"""
    def __init__(self, url: str, fetch_interval: float = 0.1):
        import urllib.request
        self.url = url
        self.last_frame = None
        self.last_fetch = 0
        self.fetch_interval = fetch_interval  # 기본 0.1초 (10fps)

        # 연결 테스트
        try:
            self._fetch_frame()
            print(f"[INFO] 스냅샷 URL 연결됨: {url} (interval: {fetch_interval}s)")
        except Exception as e:
            raise RuntimeError(f"스냅샷 URL 연결 실패: {url} - {e}")

    def _fetch_frame(self) -> Optional[np.ndarray]:
        """URL에서 이미지 가져오기"""
        import urllib.request
        try:
            with urllib.request.urlopen(self.url, timeout=5) as response:
                img_array = np.asarray(bytearray(response.read()), dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                return frame
        except Exception as e:
            print(f"[WARN] 이미지 가져오기 실패: {e}")
            return None

    def get_frame(self) -> Optional[np.ndarray]:
        now = time.time()
        if now - self.last_fetch >= self.fetch_interval:
            frame = self._fetch_frame()
            if frame is not None:
                self.last_frame = frame
            self.last_fetch = now
        return self.last_frame


class FolderSource(ImageSource):
    """폴더 이미지 소스 (테스트용)"""
    def __init__(self, folder_path: str):
        self.folder = Path(folder_path)
        self.images = sorted(self.folder.glob("*.jpg")) + sorted(self.folder.glob("*.png"))
        if not self.images:
            raise RuntimeError(f"이미지를 찾을 수 없습니다: {folder_path}")
        self.index = 0
        print(f"[INFO] 폴더 소스: {len(self.images)}개 이미지")

    def get_frame(self) -> Optional[np.ndarray]:
        if not self.images:
            return None
        img_path = self.images[self.index]
        frame = cv2.imread(str(img_path))
        return frame

    def next_image(self):
        """다음 이미지로 이동"""
        self.index = (self.index + 1) % len(self.images)
        return self.images[self.index].name

    def prev_image(self):
        """이전 이미지로 이동"""
        self.index = (self.index - 1) % len(self.images)
        return self.images[self.index].name

    def current_name(self) -> str:
        return self.images[self.index].name if self.images else "N/A"


def create_source(source_arg: str) -> ImageSource:
    """소스 문자열로부터 ImageSource 생성"""
    if source_arg.lower() == "webcam":
        return WebcamSource(Config.DEFAULT_CAMERA)
    elif source_arg.startswith("http"):
        # snapshot URL인지 stream URL인지 판단
        if "snapshot" in source_arg.lower() or source_arg.endswith(('.jpg', '.jpeg', '.png')):
            return SnapshotURLSource(source_arg)
        else:
            # MJPEG 스트림 시도, 실패하면 스냅샷으로 폴백
            try:
                return URLStreamSource(source_arg)
            except RuntimeError:
                print("[INFO] 스트림 연결 실패, 스냅샷 모드로 전환...")
                return SnapshotURLSource(source_arg)
    elif os.path.isdir(source_arg):
        return FolderSource(source_arg)
    elif os.path.isfile(source_arg):
        # 단일 파일 -> 폴더로 처리
        return FolderSource(os.path.dirname(source_arg))
    else:
        # 숫자면 웹캠 ID
        try:
            cam_id = int(source_arg)
            return WebcamSource(cam_id)
        except ValueError:
            raise RuntimeError(f"알 수 없는 소스: {source_arg}")


# =============================================================================
# LLM 분석
# =============================================================================

def frame_to_base64(frame: np.ndarray) -> str:
    """OpenCV 프레임을 Base64로 변환"""
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode('utf-8')


async def analyze_frame_with_llm(frame: np.ndarray, sensor_data: dict = None) -> dict:
    """단일 프레임 LLM 분석 (호환성 유지)"""
    return await analyze_with_history(
        images=[{"timestamp": datetime.now(), "frame": frame}],
        status_history=[sensor_data] if sensor_data else []
    )


def get_image_analysis_prompt(lang: str = "ko") -> tuple:
    """언어별 이미지 분석 프롬프트 반환"""
    if lang == "en":
        system = """You are an expert evaluating **visual quality** of 3D prints.
Ignore sensor data. Judge only what you see in the images.

## Visual Issues to Check
1. **Layer Quality**: layer shift, layer separation, uneven layers
2. **Extrusion Issues**: over-extrusion, under-extrusion, stringing
3. **Surface Quality**: rough surface, blobs, drooping
4. **Structural Issues**: warping, lifting, bed adhesion failure
5. **Speed Issues**: vibration patterns, wobbling from high speed
6. **Other**: filament tangle, nozzle clog signs

## Important
- Report any visible issues regardless of sensor status
- Compare images chronologically for problem progression

JSON Response:
{
    "visual_status": "good|warning|critical",
    "visual_score": 0-100,
    "visual_issues": [
        {"type": "issue name", "severity": "low|medium|high|critical", "description": "details", "confidence": 0.0-1.0}
    ],
    "print_progression": "normal|slow|stalled|abnormal",
    "visual_observations": "what you observed",
    "visual_recommendation": "recommended action"
}"""
        user_prefix = f"## Image Quality Analysis\nAnalyze these images (visual only, no sensor data):"
    else:  # ko (default)
        system = """당신은 3D 프린터 출력물의 **시각적 품질**만 평가하는 전문가입니다.
센서 데이터는 무시하고, 오직 이미지에서 보이는 것만 판단하세요.

## 반드시 확인할 시각적 문제들
1. **레이어 품질**: 레이어 쉬프트, 레이어 분리, 불균일한 레이어
2. **압출 문제**: 과압출(뭉침), 압출부족(빈틈), 스트링잉(실타래)
3. **표면 품질**: 거친 표면, 블롭(덩어리), 흘러내림
4. **구조 문제**: 휨(warping), 들뜸, 베드 접착 불량
5. **속도 문제**: 너무 빠른 속도로 인한 진동 패턴, 흔들림
6. **기타**: 필라멘트 꼬임, 노즐 막힘 징후

## 중요
- 이미지에서 보이는 문제는 반드시 보고하세요
- 시간순 이미지 비교로 문제 발생/악화 여부 확인

JSON 응답:
{
    "visual_status": "good|warning|critical",
    "visual_score": 0-100,
    "visual_issues": [
        {"type": "이슈명", "severity": "low|medium|high|critical", "description": "상세설명", "confidence": 0.0-1.0}
    ],
    "print_progression": "normal|slow|stalled|abnormal",
    "visual_observations": "이미지에서 관찰된 내용",
    "visual_recommendation": "시각적 문제 기반 권장사항"
}"""
        user_prefix = f"## 이미지 품질 분석\n센서 데이터 없이 순수하게 이미지만 분석해주세요:"
    return system, user_prefix


async def analyze_images_only(images: List[dict]) -> dict:
    """
    이미지만 분석 (센서 데이터 무시) - 순수 시각적 품질 평가
    """
    if not images:
        return {"status": "error", "error": "No images"}

    llm = get_llm_client(temperature=0.1, max_output_tokens=2048)

    system_prompt, user_prefix = get_image_analysis_prompt(Config.LANGUAGE)

    content_parts = [{"type": "text", "text": f"{user_prefix} ({len(images)} images)"}]

    for i, img_data in enumerate(images):
        timestamp = img_data["timestamp"]
        frame = img_data["frame"]
        image_b64 = frame_to_base64(frame)
        time_str = timestamp.strftime("%H:%M:%S") if isinstance(timestamp, datetime) else str(timestamp)
        content_parts.append({"type": "text", "text": f"\n[이미지 {i+1}/{len(images)}] {time_str}"})
        content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})

    try:
        # 60초 timeout 설정
        response = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=content_parts)]),
            timeout=60.0
        )
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except asyncio.TimeoutError:
        return {"visual_status": "error", "error": "LLM timeout (60s)"}
    except Exception as e:
        return {"visual_status": "error", "error": str(e)}


def get_sensor_analysis_prompt(lang: str = "ko") -> str:
    """언어별 센서 분석 프롬프트 반환"""
    if lang == "en":
        return """You are a 3D printer sensor data analyst.
Evaluate printer status using only temperature, position, and progress data.

## Analysis Items
1. **Temperature Stability**: Is nozzle/bed temp stable at target?
2. **Temperature Anomalies**: Sudden changes, below target, overheating
3. **Progress**: Is printing progressing normally?
4. **Position Changes**: Is Z-axis rising normally?

JSON Response:
{
    "sensor_status": "normal|warning|critical",
    "temperature_analysis": {
        "nozzle_stable": true|false,
        "bed_stable": true|false,
        "anomaly_detected": true|false,
        "notes": "temperature analysis"
    },
    "progress_analysis": {
        "is_progressing": true|false,
        "estimated_health": "good|degrading|stalled",
        "notes": "progress analysis"
    },
    "sensor_issues": [
        {"type": "issue name", "severity": "low|medium|high", "description": "details"}
    ],
    "sensor_observations": "sensor data observations"
}"""
    else:  # ko
        return """당신은 3D 프린터 센서 데이터 분석 전문가입니다.
온도, 위치, 진행률 등 센서 데이터만으로 프린터 상태를 평가하세요.

## 분석 항목
1. **온도 안정성**: 노즐/베드 온도가 목표치에 안정적인지
2. **온도 이상**: 급격한 변화, 목표 미달, 과열
3. **진행률**: 정상적으로 진행 중인지
4. **위치 변화**: Z축 상승이 정상적인지

JSON 응답:
{
    "sensor_status": "normal|warning|critical",
    "temperature_analysis": {
        "nozzle_stable": true|false,
        "bed_stable": true|false,
        "anomaly_detected": true|false,
        "notes": "온도 분석"
    },
    "progress_analysis": {
        "is_progressing": true|false,
        "estimated_health": "good|degrading|stalled",
        "notes": "진행 분석"
    },
    "sensor_issues": [
        {"type": "이슈명", "severity": "low|medium|high", "description": "설명"}
    ],
    "sensor_observations": "센서 데이터 관찰 내용"
}"""


async def analyze_sensor_only(status_history: List[dict]) -> dict:
    """
    센서 데이터만 분석 (이미지 무시)
    """
    if not status_history:
        return {"status": "error", "error": "No sensor data"}

    llm = get_llm_client(temperature=0.0, max_output_tokens=1024)

    status_summary = _summarize_status_history(status_history)
    system_prompt = get_sensor_analysis_prompt(Config.LANGUAGE)

    try:
        # 30초 timeout 설정
        response = await asyncio.wait_for(
            llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"## 센서 데이터 분석\n\n{status_summary}")
            ]),
            timeout=30.0
        )
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except asyncio.TimeoutError:
        return {"sensor_status": "error", "error": "LLM timeout (30s)"}
    except Exception as e:
        return {"sensor_status": "error", "error": str(e)}


async def analyze_with_history(images: List[dict], status_history: List[dict]) -> dict:
    """
    분리 분석 후 종합 (이미지 분석 + 센서 분석 → 종합 판단)
    """
    if not images:
        return {"print_status": "error", "error": "No images to analyze"}

    # 1. 병렬로 이미지/센서 분석 실행
    async def empty_result():
        return {}

    image_task = analyze_images_only(images)
    sensor_task = analyze_sensor_only(status_history) if status_history else empty_result()

    image_result, sensor_result = await asyncio.gather(image_task, sensor_task)

    # 2. 종합 판단 (이미지 우선)
    visual_status = image_result.get("visual_status", "unknown")
    sensor_status = sensor_result.get("sensor_status", "unknown") if sensor_result else "unknown"

    # 최종 상태 결정 (이미지가 더 중요)
    status_priority = {"critical": 3, "warning": 2, "good": 1, "normal": 1, "unknown": 0, "error": 0}
    visual_priority = status_priority.get(visual_status, 0)
    sensor_priority = status_priority.get(sensor_status, 0)

    # 이미지에서 문제가 있으면 센서가 정상이어도 경고
    if visual_priority >= 2:  # warning 이상
        final_status = visual_status
    elif sensor_priority >= 3:  # sensor critical
        final_status = "critical"
    elif visual_priority >= 1 and sensor_priority >= 2:
        final_status = "warning"
    else:
        final_status = "normal" if visual_status in ["good", "normal"] else visual_status

    # 점수 계산 (이미지 70%, 센서 30%)
    visual_score = image_result.get("visual_score", 50)
    sensor_score = 100 if sensor_status == "normal" else (70 if sensor_status == "warning" else 40)
    final_score = int(visual_score * 0.7 + sensor_score * 0.3)

    # 이슈 통합
    all_issues = []
    for issue in image_result.get("visual_issues", []):
        issue["source"] = "image"
        all_issues.append(issue)
    for issue in sensor_result.get("sensor_issues", []) if sensor_result else []:
        issue["source"] = "sensor"
        all_issues.append(issue)

    # 즉시 조치 필요 여부
    immediate_action = (
        final_status == "critical" or
        any(i.get("severity") in ["critical", "high"] for i in all_issues)
    )

    # 관찰 내용 통합
    observations = []
    if image_result.get("visual_observations"):
        observations.append(f"[이미지] {image_result['visual_observations']}")
    if sensor_result and sensor_result.get("sensor_observations"):
        observations.append(f"[센서] {sensor_result['sensor_observations']}")

    # 권장사항 통합
    recommendations = []
    if image_result.get("visual_recommendation"):
        recommendations.append(image_result["visual_recommendation"])

    return {
        "print_status": final_status,
        "print_quality_score": final_score,
        "issues_detected": all_issues,
        "temperature_analysis": sensor_result.get("temperature_analysis", {}) if sensor_result else {},
        "progress_analysis": sensor_result.get("progress_analysis", {}) if sensor_result else {},
        "observations": " | ".join(observations),
        "immediate_action_needed": immediate_action,
        "recommendation": " / ".join(recommendations) if recommendations else "계속 모니터링",
        # 상세 결과 보존
        "_image_analysis": image_result,
        "_sensor_analysis": sensor_result,
        "analyzed_images": len(images),
        "analyzed_samples": len(status_history)
    }


def _summarize_status_history(status_history: List[dict]) -> str:
    """상태 히스토리 요약 문자열 생성"""
    if not status_history:
        return "데이터 없음"

    # 온도 추출
    nozzle_temps = [s.get("nozzle_temp", 0) for s in status_history if s.get("nozzle_temp")]
    bed_temps = [s.get("bed_temp", 0) for s in status_history if s.get("bed_temp")]
    progress_vals = [s.get("print_progress", 0) for s in status_history if s.get("print_progress") is not None]

    lines = []

    # 프린터 상태
    states = [s.get("state", "Unknown") for s in status_history]
    state_counts = {}
    for st in states:
        state_counts[st] = state_counts.get(st, 0) + 1
    lines.append(f"- 프린터 상태: {state_counts}")

    # 노즐 온도
    if nozzle_temps:
        lines.append(f"- 노즐 온도: {min(nozzle_temps):.1f}~{max(nozzle_temps):.1f}°C (평균 {sum(nozzle_temps)/len(nozzle_temps):.1f}°C)")
        nozzle_targets = [s.get("nozzle_target", 0) for s in status_history if s.get("nozzle_target")]
        if nozzle_targets:
            lines.append(f"- 노즐 목표: {nozzle_targets[-1]:.0f}°C")

    # 베드 온도
    if bed_temps:
        lines.append(f"- 베드 온도: {min(bed_temps):.1f}~{max(bed_temps):.1f}°C (평균 {sum(bed_temps)/len(bed_temps):.1f}°C)")
        bed_targets = [s.get("bed_target", 0) for s in status_history if s.get("bed_target")]
        if bed_targets:
            lines.append(f"- 베드 목표: {bed_targets[-1]:.0f}°C")

    # 진행률
    if progress_vals:
        start_progress = progress_vals[0]
        end_progress = progress_vals[-1]
        lines.append(f"- 진행률: {start_progress:.1f}% -> {end_progress:.1f}% (변화: +{end_progress - start_progress:.1f}%)")

    # 위치 변화
    positions = [s.get("position", {}) for s in status_history if s.get("position")]
    if positions and len(positions) > 1:
        first_pos = positions[0]
        last_pos = positions[-1]
        z_change = last_pos.get("z", 0) - first_pos.get("z", 0)
        lines.append(f"- Z 위치 변화: {first_pos.get('z', 0):.2f} -> {last_pos.get('z', 0):.2f}mm (+{z_change:.2f}mm)")

    return "\n".join(lines)


# =============================================================================
# 모니터 클래스
# =============================================================================

class PrinterMonitor:
    """3D 프린터 모니터"""

    def __init__(self, source: ImageSource):
        self.source = source
        self.state = MonitorState.IDLE
        self.current_frame: Optional[np.ndarray] = None
        self.last_analysis: Optional[dict] = None
        self.last_analysis_time: Optional[datetime] = None
        self.analysis_count = 0
        self.command_queue = Queue()
        self.running = True

        # 프린터 상태 데이터 (API에서 가져옴)
        self.sensor_data = {}
        self.printer_status_raw = {}

        # === 데이터 수집 버퍼 (3분 분량) ===
        # 상태/온도 히스토리 (5초마다, 최대 36개)
        self.status_history: List[dict] = []
        # 이미지 히스토리 (30초마다, 최대 6장)
        self.image_history: List[dict] = []  # {"timestamp": datetime, "frame": np.ndarray}

        # 수집 타이밍
        self.last_status_poll = 0
        self.last_image_capture = 0
        self.last_llm_analysis = 0

        # === 터미널 로그 버퍼 ===
        self.terminal_logs: List[dict] = []  # {"time": str, "type": str, "message": str}
        self.MAX_TERMINAL_LOGS = 30  # 최대 로그 라인 수 (줄바꿈 고려)
        self.LOG_LINE_WIDTH = 85    # 한 줄 최대 글자 수

    def add_log(self, message: str, log_type: str = "info"):
        """터미널 로그 추가 - 긴 메시지는 줄바꿈"""
        time_str = datetime.now().strftime("%H:%M:%S")

        # 긴 메시지는 여러 줄로 분할
        if len(message) <= self.LOG_LINE_WIDTH:
            lines = [message]
        else:
            lines = []
            while message:
                lines.append(message[:self.LOG_LINE_WIDTH])
                message = message[self.LOG_LINE_WIDTH:]

        # 첫 줄은 시간 포함, 나머지는 시간 없이 (들여쓰기)
        for i, line in enumerate(lines):
            log_entry = {
                "time": time_str if i == 0 else "",
                "type": log_type,
                "message": line
            }
            self.terminal_logs.append(log_entry)

        # 최대 개수 유지
        while len(self.terminal_logs) > self.MAX_TERMINAL_LOGS:
            self.terminal_logs.pop(0)

    async def fetch_printer_status(self) -> dict:
        """프린터 API에서 실시간 상태 가져오기"""
        try:
            response = await printer_client.get_status()
            self.printer_status_raw = response

            # API 응답 구조: {"success": true, "data": {...}}
            if response.get("success") and response.get("data"):
                data = response["data"]

                # 연결 상태 확인
                if not data.get("connected", False):
                    self.sensor_data = {
                        "state": "Disconnected",
                        "connected": False,
                        "message": data.get("message", "프린터 연결 안됨")
                    }
                    return response

                # 연결된 경우 - API 문서 구조에 맞게 파싱
                # temperature: { tool: {current, target}, bed: {current, target} }
                # printProgress: { completion, file_position, file_size, print_time, print_time_left, filament_used }
                temp = data.get("temperature", {})
                tool_temp = temp.get("tool", {})
                bed_temp = temp.get("bed", {})
                progress = data.get("printProgress", {})

                self.sensor_data = {
                    "connected": True,
                    "state": data.get("status", "Unknown"),
                    "printing": data.get("printing", False),
                    "error_message": data.get("error_message"),
                    # 온도
                    "nozzle_temp": tool_temp.get("current", 0),
                    "nozzle_target": tool_temp.get("target", 0),
                    "bed_temp": bed_temp.get("current", 0),
                    "bed_target": bed_temp.get("target", 0),
                    # 위치
                    "position": data.get("position", {}),
                    # 진행률
                    "print_progress": progress.get("completion", 0),
                    "print_time": progress.get("print_time", 0),
                    "print_time_left": progress.get("print_time_left", 0),
                    "filament_used": progress.get("filament_used", 0),
                    # 타임스탬프
                    "last_updated": data.get("lastUpdated"),
                }
            else:
                self.sensor_data = {
                    "state": "API Error",
                    "connected": False,
                    "message": response.get("message", "API 응답 오류")
                }

            return response
        except Exception as e:
            print(f"[WARN] 프린터 상태 조회 실패: {e}")
            self.sensor_data = {
                "state": "Error",
                "connected": False,
                "message": str(e)
            }
            return {}

    def collect_status(self):
        """상태/온도 데이터 수집 (히스토리에 추가)"""
        if not self.sensor_data:
            return

        record = {
            "timestamp": datetime.now().isoformat(),
            "state": self.sensor_data.get("state", "Unknown"),
            "connected": self.sensor_data.get("connected", False),
            "printing": self.sensor_data.get("printing", False),
            "nozzle_temp": self.sensor_data.get("nozzle_temp", 0),
            "nozzle_target": self.sensor_data.get("nozzle_target", 0),
            "bed_temp": self.sensor_data.get("bed_temp", 0),
            "bed_target": self.sensor_data.get("bed_target", 0),
            "position": self.sensor_data.get("position", {}),
            "print_progress": self.sensor_data.get("print_progress", 0),
        }

        self.status_history.append(record)

        # 최대 개수 유지
        if len(self.status_history) > Config.MAX_STATUS_HISTORY:
            self.status_history.pop(0)

    def crop_center(self, frame: np.ndarray, crop_ratio: float = 0.6) -> np.ndarray:
        """
        이미지 중앙 크롭 (출력물이 보통 중앙에 있음)

        crop_ratio: 원본 대비 크롭 비율 (0.6 = 60%)
        """
        h, w = frame.shape[:2]

        # 중앙 기준 크롭
        new_w = int(w * crop_ratio)
        new_h = int(h * crop_ratio)

        x1 = (w - new_w) // 2
        y1 = (h - new_h) // 2
        x2 = x1 + new_w
        y2 = y1 + new_h

        return frame[y1:y2, x1:x2]

    def capture_image(self):
        """이미지 캡처 (히스토리에 추가) - 중앙 60% 크롭"""
        if self.current_frame is None:
            return

        # 중앙 60% 크롭 (출력물이 보통 중앙에 위치)
        cropped_frame = self.crop_center(self.current_frame, crop_ratio=0.6)

        record = {
            "timestamp": datetime.now(),
            "frame": cropped_frame
        }

        self.image_history.append(record)

        # 최대 개수 유지
        if len(self.image_history) > Config.MAX_IMAGE_HISTORY:
            self.image_history.pop(0)

        h, w = cropped_frame.shape[:2]
        print(f"[CAPTURE] 중앙 크롭 #{len(self.image_history)} ({w}x{h})")
        self.add_log(f"Center crop #{len(self.image_history)}/{Config.MAX_IMAGE_HISTORY} ({w}x{h})", "info")

    def get_collected_data(self) -> dict:
        """수집된 데이터 반환 (LLM 분석용)"""
        return {
            "status_history": self.status_history.copy(),
            "image_count": len(self.image_history),
            "images": self.image_history.copy(),
            "collection_period": {
                "start": self.status_history[0]["timestamp"] if self.status_history else None,
                "end": self.status_history[-1]["timestamp"] if self.status_history else None,
                "status_count": len(self.status_history),
                "image_count": len(self.image_history),
            }
        }

    def clear_history(self):
        """수집 버퍼 초기화"""
        self.status_history.clear()
        self.image_history.clear()

    def draw_terminal_panel(self, frame: np.ndarray) -> np.ndarray:
        """오른쪽 하단에 터미널 패널 그리기 (한글 지원)"""
        h, w = frame.shape[:2]
        overlay = frame.copy()

        # 터미널 패널 설정 (폰트 크게, 줄바꿈으로 긴 텍스트 지원)
        panel_width = 700
        panel_height = 520
        panel_x = w - panel_width - 10
        panel_y = h - panel_height - 10
        line_height = 17
        font_size = 12

        # 패널 배경 (반투명 검정)
        cv2.rectangle(overlay, (panel_x, panel_y), (panel_x + panel_width, panel_y + panel_height), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

        # 테두리
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_width, panel_y + panel_height), (80, 80, 80), 1)

        # 타이틀 바
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_width, panel_y + 22), (40, 40, 40), -1)

        # PIL로 한글 텍스트 렌더링
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_image)
        font = get_cached_font(font_size)
        font_small = get_cached_font(11)

        # 타이틀
        draw.text((panel_x + 10, panel_y + 4), ">> Analysis Terminal", font=font, fill=(0, 255, 0))

        # 로그 출력
        log_start_y = panel_y + 30
        max_lines = (panel_height - 40) // line_height

        # 최근 로그만 표시
        recent_logs = self.terminal_logs[-max_lines:]

        type_colors = {
            "info": (200, 200, 200),      # 흰색
            "warn": (255, 200, 0),         # 주황색
            "error": (255, 80, 80),         # 빨간색
            "result": (0, 255, 0),         # 녹색
            "issue": (255, 150, 100),      # 연주황
            "score": (0, 255, 255),        # 청록
        }

        for i, log in enumerate(recent_logs):
            y = log_start_y + i * line_height
            color = type_colors.get(log["type"], (200, 200, 200))

            # 시간 표시
            draw.text((panel_x + 5, y), log["time"], font=font_small, fill=(100, 100, 100))

            # 메시지 표시 (영어 텍스트용 길이 제한 늘림)
            msg = log["message"][:120]
            draw.text((panel_x + 70, y), msg, font=font, fill=color)

        # 커서 깜빡임 효과
        if len(recent_logs) < max_lines:
            cursor_y = log_start_y + len(recent_logs) * line_height
            if int(time.time() * 2) % 2 == 0:
                draw.text((panel_x + 5, cursor_y), ">_", font=font, fill=(0, 255, 0))

        # PIL -> OpenCV
        frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return frame

    def draw_overlay(self, frame: np.ndarray) -> np.ndarray:
        """프레임에 오버레이 그리기"""
        overlay = frame.copy()
        h, w = frame.shape[:2]

        # 상단 상태바 배경 (더 넓게)
        cv2.rectangle(overlay, (0, 0), (w, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        # 모니터 상태 표시
        state_text = f"Monitor: {self.state.value.upper()}"
        state_color = {
            MonitorState.IDLE: (200, 200, 200),
            MonitorState.MONITORING: (0, 255, 0),
            MonitorState.STOPPED: (0, 0, 255)
        }.get(self.state, (255, 255, 255))

        cv2.putText(frame, state_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, state_color, 2)

        # 시간 표시
        time_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, time_text, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 프린터 상태 표시 (실시간)
        if self.sensor_data:
            printer_state = self.sensor_data.get("state", "Unknown")
            connected = self.sensor_data.get("connected", False)

            # 프린터 상태 색상
            if connected:
                state_color = (0, 255, 0)  # 녹색
            elif printer_state == "Disconnected":
                state_color = (0, 165, 255)  # 주황색
            else:
                state_color = (0, 0, 255)  # 빨간색

            cv2.putText(frame, f"Printer: {printer_state}", (10, 75),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, state_color, 1)

            if connected:
                # 연결됨 - 온도/진행률 표시
                nozzle = self.sensor_data.get("nozzle_temp", 0) or 0
                nozzle_target = self.sensor_data.get("nozzle_target", 0) or 0
                bed = self.sensor_data.get("bed_temp", 0) or 0
                bed_target = self.sensor_data.get("bed_target", 0) or 0
                progress = self.sensor_data.get("print_progress", 0) or 0

                temp_text = f"Nozzle: {nozzle:.1f}/{nozzle_target:.0f}C | Bed: {bed:.1f}/{bed_target:.0f}C"
                cv2.putText(frame, temp_text, (10, 95),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                progress_text = f"Progress: {progress:.1f}%"
                cv2.putText(frame, progress_text, (w - 200, 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                # 연결 안됨 - 메시지 표시
                msg = self.sensor_data.get("message", "연결 대기중...")
                cv2.putText(frame, msg[:40], (10, 95),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        # 분석 횟수 및 수집 현황
        if self.state == MonitorState.MONITORING:
            analysis_text = f"Analysis: #{self.analysis_count}"
            cv2.putText(frame, analysis_text, (w - 200, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

            # 수집 현황 표시
            collect_text = f"Collected: {len(self.status_history)}/{Config.MAX_STATUS_HISTORY} status, {len(self.image_history)}/{Config.MAX_IMAGE_HISTORY} img"
            cv2.putText(frame, collect_text, (w - 400, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # 다음 LLM 분석까지 남은 시간
            time_since_analysis = time.time() - self.last_llm_analysis
            time_to_next = max(0, Config.LLM_ANALYSIS_INTERVAL - time_since_analysis)
            next_text = f"Next LLM: {int(time_to_next)}s"
            cv2.putText(frame, next_text, (w - 200, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)

        # 왼쪽 하단: 마지막 분석 요약 (간단히)
        if self.last_analysis:
            status = self.last_analysis.get("print_status", "unknown")
            score = self.last_analysis.get("print_quality_score", "N/A")

            status_colors = {
                "normal": (0, 255, 0),
                "warning": (0, 255, 255),
                "critical": (0, 0, 255),
            }
            color = status_colors.get(status, (200, 200, 200))

            # 왼쪽 하단에 간단 상태만
            cv2.putText(frame, f"[{status.upper()}] Score:{score}", (10, h - 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            if self.last_analysis_time:
                elapsed = (datetime.now() - self.last_analysis_time).seconds
                cv2.putText(frame, f"Last analysis: {elapsed}s ago", (10, h - 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

        # 도움말
        help_text = "[S]tart | [P]ause | [A]nalyze | [Q]uit"
        if isinstance(self.source, FolderSource):
            help_text += " | [<][>] Prev/Next"
        cv2.putText(frame, help_text, (10, h - 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

        # 오른쪽 하단: 터미널 패널
        frame = self.draw_terminal_panel(frame)

        return frame

    async def run_analysis(self, force_single: bool = False):
        """
        분석 실행

        Args:
            force_single: True면 현재 프레임만 분석 (즉시 분석용)
        """
        self.analysis_count += 1
        print(f"\n{'='*70}")
        print(f"[{self.analysis_count}] LLM 분석 시작...")
        print(f"{'='*70}")

        # 터미널 로그에 시작 표시
        self.add_log(f">>> Starting Analysis #{self.analysis_count}...", "score")

        start_time = time.time()

        if force_single or not self.image_history:
            # 즉시 분석 - 현재 프레임만 사용
            if self.current_frame is None:
                print("[WARN] 분석할 이미지가 없습니다")
                self.add_log("No image available for analysis", "error")
                return
            print(f"[MODE] 단일 프레임 분석")
            self.add_log("Mode: Single frame analysis", "info")
            result = await analyze_frame_with_llm(self.current_frame, self.sensor_data)
        else:
            # 수집된 데이터로 분석
            print(f"[MODE] 수집 데이터 분석: 이미지 {len(self.image_history)}장, 상태 {len(self.status_history)}개")
            self.add_log(f"Mode: Batch ({len(self.image_history)} imgs, {len(self.status_history)} samples)", "info")
            result = await analyze_with_history(
                images=self.image_history,
                status_history=self.status_history
            )
            # 분석 후 버퍼 초기화
            self.clear_history()

        elapsed = time.time() - start_time

        self.last_analysis = result
        self.last_analysis_time = datetime.now()

        # 결과 출력
        self._print_result(result, elapsed)

        return result

    def _print_result(self, result: dict, elapsed: float):
        """분석 결과 출력 (콘솔 + 터미널 패널) - 분리 분석 버전"""
        status = result.get("print_status", "unknown")
        score = result.get("print_quality_score", "N/A")

        # 분리 분석 결과 추출
        image_analysis = result.get("_image_analysis", {})
        sensor_analysis = result.get("_sensor_analysis", {})

        visual_status = image_analysis.get("visual_status", "?")
        visual_score = image_analysis.get("visual_score", "?")
        sensor_status = sensor_analysis.get("sensor_status", "?") if sensor_analysis else "N/A"

        status_emoji = {"normal": "[OK]", "warning": "[WARN]", "critical": "[CRIT]", "good": "[OK]", "error": "[ERR]"}
        emoji = status_emoji.get(status, "[?]")

        # 콘솔 출력
        print(f"\n{emoji} FINAL: {status.upper()} | Score: {score}/100 | Time: {elapsed:.1f}s")
        print(f"    [Image: {visual_status.upper()} ({visual_score}점)] [Sensor: {sensor_status.upper()}]")

        # 터미널 로그 추가
        self.add_log("=" * 50, "info")
        self.add_log(f"Analysis #{self.analysis_count} ({elapsed:.1f}s)", "score")

        # 분리 분석 결과 표시
        img_type = {"good": "result", "warning": "warn", "critical": "error"}.get(visual_status, "info")
        self.add_log(f"[IMAGE] {visual_status.upper()} Score:{visual_score}", img_type)

        sensor_type = {"normal": "result", "warning": "warn", "critical": "error"}.get(sensor_status, "info")
        self.add_log(f"[SENSOR] {sensor_status.upper()}", sensor_type)

        # 최종 상태
        log_type = {"normal": "result", "warning": "warn", "critical": "error"}.get(status, "info")
        self.add_log(f">>> FINAL: {status.upper()} | Score: {score}/100", log_type)

        # 이미지 이슈 (source로 구분)
        issues = result.get("issues_detected", [])
        image_issues = [i for i in issues if i.get("source") == "image"]
        sensor_issues = [i for i in issues if i.get("source") == "sensor"]

        if image_issues:
            print(f"\n[Image Issues] ({len(image_issues)}):")
            self.add_log(f"Image Issues: {len(image_issues)}", "issue")
            for issue in image_issues:
                sev = issue.get("severity", "?").upper()
                typ = issue.get("type", "unknown")
                desc = issue.get("description", "")
                print(f"  [{sev}] {typ}: {desc}")
                issue_type = {"HIGH": "error", "CRITICAL": "error", "MEDIUM": "warn"}.get(sev, "issue")
                self.add_log(f"  [{sev}] {typ}: {desc}", issue_type)

        if sensor_issues:
            print(f"\n[Sensor Issues] ({len(sensor_issues)}):")
            for issue in sensor_issues:
                sev = issue.get("severity", "?").upper()
                typ = issue.get("type", "unknown")
                desc = issue.get("description", "")
                print(f"  [{sev}] {typ}: {desc}")

        if not issues:
            self.add_log("No issues detected", "result")

        # 이미지 관찰 내용
        if image_analysis.get("visual_observations"):
            obs = image_analysis["visual_observations"]
            print(f"\n[Image Obs]: {obs}")
            self.add_log(f"Visual: {obs}", "info")

        # 온도/진행 분석 (센서)
        temp_analysis = result.get("temperature_analysis", {})
        if temp_analysis:
            nozzle_ok = "OK" if temp_analysis.get("nozzle_stable") else "UNSTABLE"
            bed_ok = "OK" if temp_analysis.get("bed_stable") else "UNSTABLE"
            temp_type = "result" if temp_analysis.get("nozzle_stable") and temp_analysis.get("bed_stable") else "warn"
            self.add_log(f"Temp: Nozzle {nozzle_ok}, Bed {bed_ok}", temp_type)

        # 권장 조치
        if result.get("recommendation"):
            rec = result['recommendation']
            print(f"\nRecommendation: {rec}")
            self.add_log(f"Rec: {rec}", "result")

        # 즉시 조치 필요
        if result.get("immediate_action_needed"):
            print("\n*** IMMEDIATE ACTION NEEDED! ***")
            self.add_log(">>> IMMEDIATE ACTION NEEDED! <<<", "error")

        self.add_log("-" * 50, "info")
        print(f"{'='*60}\n")

    async def monitoring_loop(self):
        """
        모니터링 루프 (백그라운드)

        타이밍:
        - 5초마다: API 폴링 → 상태/온도 저장 (최대 36개)
        - 30초마다: 이미지 캡처 (최대 6장)
        - 3분마다: 수집된 데이터로 LLM 분석
        """
        while self.running:
            now = time.time()

            # === 1. API 상태 폴링 (5초마다) ===
            if now - self.last_status_poll >= Config.STATUS_POLL_INTERVAL:
                await self.fetch_printer_status()
                if self.state == MonitorState.MONITORING:
                    self.collect_status()
                self.last_status_poll = now

            # === 2. 이미지 캡처 (30초마다, 모니터링 중일 때만) ===
            if self.state == MonitorState.MONITORING:
                if now - self.last_image_capture >= Config.IMAGE_CAPTURE_INTERVAL:
                    self.capture_image()
                    self.last_image_capture = now

            # === 3. LLM 분석 (1분마다, 모니터링 중일 때만) ===
            if self.state == MonitorState.MONITORING:
                if now - self.last_llm_analysis >= Config.LLM_ANALYSIS_INTERVAL:
                    # 최소 데이터가 있을 때만 분석
                    if len(self.image_history) >= 1:
                        await self.run_analysis()
                        self.last_llm_analysis = now  # 분석 완료 후에만 타이머 리셋
                    else:
                        # 이미지가 없으면 로그만 출력하고 타이머는 유지
                        print(f"[WAIT] 이미지 대기 중... ({len(self.image_history)}/{Config.MAX_IMAGE_HISTORY})")
                        self.add_log(f"Waiting for images... ({len(self.image_history)}/{Config.MAX_IMAGE_HISTORY})", "warn")

            await asyncio.sleep(1)

    def handle_key(self, key: int) -> bool:
        """키 입력 처리. False 반환 시 종료"""
        if key == ord('q') or key == ord('Q'):
            return False

        elif key == ord('s') or key == ord('S'):
            if self.state != MonitorState.MONITORING:
                self.state = MonitorState.MONITORING
                print("\n[START] 모니터링 시작!")
                self.add_log("=== Monitoring STARTED ===", "result")
                self.add_log(f"Collecting every {Config.STATUS_POLL_INTERVAL}s / Analyze every {Config.LLM_ANALYSIS_INTERVAL}s", "info")

        elif key == ord('p') or key == ord('P'):
            if self.state == MonitorState.MONITORING:
                self.state = MonitorState.IDLE
                print("\n[PAUSE] 모니터링 일시정지")
                self.add_log("=== Monitoring PAUSED ===", "warn")

        elif key == ord('a') or key == ord('A'):
            # 즉시 분석 (현재 프레임만)
            self.command_queue.put("analyze_single")

        elif key == ord(',') or key == 81:  # '<' or Left arrow
            if isinstance(self.source, FolderSource):
                name = self.source.prev_image()
                print(f"\n[PREV] {name}")

        elif key == ord('.') or key == 83:  # '>' or Right arrow
            if isinstance(self.source, FolderSource):
                name = self.source.next_image()
                print(f"\n[NEXT] {name}")

        return True

    async def run(self):
        """메인 실행"""
        cv2.namedWindow(Config.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(Config.WINDOW_NAME, 1280, 720)

        # 모니터링 루프 시작
        monitor_task = asyncio.create_task(self.monitoring_loop())

        print("\n" + "="*70)
        print("3D Printer Monitor - 3분 주기 수집 분석")
        print("="*70)
        print("수집 주기:")
        print(f"  - API 폴링: {Config.STATUS_POLL_INTERVAL}초 (최대 {Config.MAX_STATUS_HISTORY}개)")
        print(f"  - 이미지 캡처: {Config.IMAGE_CAPTURE_INTERVAL}초 (최대 {Config.MAX_IMAGE_HISTORY}장)")
        print(f"  - LLM 분석: {Config.LLM_ANALYSIS_INTERVAL}초 (3분)")
        print("-"*70)
        print("Commands:")
        print("  [S] Start monitoring (3분 주기 자동 분석)")
        print("  [P] Pause monitoring")
        print("  [A] Analyze now (현재 프레임 즉시 분석)")
        print("  [Q] Quit")
        if isinstance(self.source, FolderSource):
            print("  [<][>] Previous/Next image")
        print("="*70 + "\n")

        try:
            while self.running:
                # 프레임 가져오기
                frame = self.source.get_frame()
                if frame is None:
                    await asyncio.sleep(0.1)
                    continue

                self.current_frame = frame.copy()

                # 오버레이 그리기
                display_frame = self.draw_overlay(frame)

                # 화면 표시
                cv2.imshow(Config.WINDOW_NAME, display_frame)

                # 키 입력 처리
                key = cv2.waitKey(30) & 0xFF
                if key != 255:  # 키 입력 있음
                    if not self.handle_key(key):
                        break

                # 명령 큐 처리
                while not self.command_queue.empty():
                    cmd = self.command_queue.get()
                    if cmd == "analyze_single":
                        await self.run_analysis(force_single=True)
                    elif cmd == "analyze":
                        await self.run_analysis()

                await asyncio.sleep(0.01)

        finally:
            self.running = False
            monitor_task.cancel()
            self.source.release()
            cv2.destroyAllWindows()
            print("\n[EXIT] Monitor closed.")


# =============================================================================
# 메인
# =============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="3D Printer Monitor")
    parser.add_argument(
        "--source", "-s",
        default="http://192.168.200.103:8080/video",
        help="이미지 소스: 'webcam', 카메라ID, URL, 또는 폴더 경로"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=60,
        help="분석 간격 (초)"
    )
    parser.add_argument(
        "--lang", "-l",
        default="ko",
        choices=["ko", "en", "ja", "zh"],
        help="LLM 응답 언어 (ko=한국어, en=English, ja=日本語, zh=中文)"
    )

    args = parser.parse_args()
    Config.ANALYSIS_INTERVAL = args.interval
    Config.LANGUAGE = args.lang

    try:
        source = create_source(args.source)
        monitor = PrinterMonitor(source)
        await monitor.run()
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
