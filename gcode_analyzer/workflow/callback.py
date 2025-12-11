"""
Progress Callback System for Real-time Updates
"""
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ProgressUpdate:
    """진행 상태 업데이트 데이터"""
    progress: float  # 0.0 ~ 1.0
    step: str  # 현재 단계 이름
    message: str  # 1-2줄 요약 메시지
    details: Optional[Dict[str, Any]] = None  # 추가 상세 정보
    is_streaming: bool = False  # LLM 스트리밍 여부
    streaming_content: Optional[str] = None  # 스트리밍 중인 내용

# 콜백 타입 정의
ProgressCallback = Callable[[ProgressUpdate], None]

# 스트리밍 콜백 (LLM 청크 단위)
StreamingCallback = Callable[[str], None]

class ProgressTracker:
    """
    Progress 추적 및 콜백 호출 관리

    각 노드에서 이 클래스를 통해 progress를 업데이트하면
    등록된 콜백이 호출되어 store가 업데이트됨
    """
    def __init__(self, callback: Optional[ProgressCallback] = None):
        self.callback = callback
        self.current_progress = 0.0
        self.current_step = "init"
        self.streaming_buffer = ""  # LLM 스트리밍 버퍼

    def update(self, progress: float, step: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Progress 업데이트 및 콜백 호출"""
        self.current_progress = progress
        self.current_step = step

        if self.callback:
            update = ProgressUpdate(
                progress=progress,
                step=step,
                message=message,
                details=details
            )
            self.callback(update)

    def stream_update(self, progress: float, step: str, chunk: str, message: str = ""):
        """LLM 스트리밍 업데이트 - 실시간 청크 전달"""
        self.current_progress = progress
        self.current_step = step
        self.streaming_buffer += chunk

        if self.callback:
            # 스트리밍 버퍼에서 마지막 100자만 표시
            display_content = self.streaming_buffer[-150:] if len(self.streaming_buffer) > 150 else self.streaming_buffer
            # 줄바꿈을 공백으로 치환하여 한 줄로 표시
            display_content = display_content.replace("\n", " ").strip()

            update = ProgressUpdate(
                progress=progress,
                step=step,
                message=message or f"분석 중: {display_content}...",
                is_streaming=True,
                streaming_content=display_content
            )
            self.callback(update)

    def clear_streaming_buffer(self):
        """스트리밍 버퍼 초기화"""
        self.streaming_buffer = ""

    def get_streaming_callback(self, progress: float, step: str) -> StreamingCallback:
        """LLM 스트리밍용 콜백 생성"""
        def streaming_callback(chunk: str):
            self.stream_update(progress, step, chunk)
        return streaming_callback

    def __repr__(self):
        return f"ProgressTracker(progress={self.current_progress:.0%}, step={self.current_step})"
