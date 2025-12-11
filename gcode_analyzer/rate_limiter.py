"""
Rate Limiter - Gemini API 호출 제한 관리

기능:
1. Rate-limit Queue: 초당/분당 요청 수 제한
2. 사용자별 Throttling: user_id/IP 기준 제한
3. 토큰 버킷 알고리즘으로 부드러운 제한
"""
import asyncio
import time
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logger = logging.getLogger("uvicorn.error")


@dataclass
class RateLimitConfig:
    """Rate Limit 설정"""
    # 전역 제한 (Gemini API 기준)
    global_rpm: int = 4000              # 분당 요청 수 (RPM)
    global_tpm: int = 100_000_000       # 분당 토큰 수 (TPM) - 매우 느슨하게 (실제 LLM 호출은 적음)

    # 안전 마진 (90%만 사용)
    safety_margin: float = 0.9

    # 사용자별 제한
    user_rpm: int = 30                  # 사용자당 분당 요청 (넉넉하게)
    user_daily_limit: int = 500         # 사용자당 일일 요청 (넉넉하게)

    # 대기열 설정
    max_queue_size: int = 1000          # 최대 대기열 크기
    queue_timeout: float = 300.0        # 대기열 타임아웃 (초)

    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0            # 초

    @property
    def effective_rpm(self) -> int:
        return int(self.global_rpm * self.safety_margin)

    @property
    def effective_tpm(self) -> int:
        return int(self.global_tpm * self.safety_margin)


@dataclass
class TokenBucket:
    """토큰 버킷 - 부드러운 rate limiting"""
    capacity: float                     # 버킷 용량
    tokens: float = field(default=0.0)  # 현재 토큰
    refill_rate: float = 1.0            # 초당 충전량
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self):
        self.tokens = self.capacity

    def _refill(self):
        """토큰 충전"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """토큰 획득 시도 (non-blocking)"""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """토큰 획득 (blocking with timeout)"""
        start = time.time()
        while time.time() - start < timeout:
            if self.try_acquire(tokens):
                return True
            # 필요한 토큰이 충전될 때까지 대기
            wait_time = min(0.1, (tokens - self.tokens) / self.refill_rate)
            await asyncio.sleep(max(0.01, wait_time))
        return False

    def time_until_available(self, tokens: float = 1.0) -> float:
        """토큰이 사용 가능해질 때까지 남은 시간"""
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        return (tokens - self.tokens) / self.refill_rate


@dataclass
class UserRateInfo:
    """사용자별 Rate 정보"""
    user_id: str
    request_count: int = 0              # 현재 분 요청 수
    daily_count: int = 0                # 오늘 요청 수
    last_request: float = field(default_factory=time.time)
    minute_start: float = field(default_factory=time.time)
    day_start: float = field(default_factory=time.time)

    def reset_if_needed(self):
        """분/일 경계 시 리셋"""
        now = time.time()

        # 분 리셋
        if now - self.minute_start >= 60:
            self.request_count = 0
            self.minute_start = now

        # 일 리셋 (24시간)
        if now - self.day_start >= 86400:
            self.daily_count = 0
            self.day_start = now


@dataclass
class QueueItem:
    """대기열 항목"""
    task_id: str
    user_id: Optional[str]
    priority: int = 0                   # 높을수록 먼저 처리
    estimated_tokens: int = 0
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class RateLimitError(Exception):
    """Rate Limit 초과 에러"""
    def __init__(self, message: str, retry_after: float = 0.0, error_code: str = "rate_limit"):
        super().__init__(message)
        self.retry_after = retry_after
        self.error_code = error_code


class GeminiRateLimiter:
    """
    Gemini API Rate Limiter

    사용법:
    ```python
    limiter = GeminiRateLimiter()

    # 요청 전 체크
    await limiter.acquire(user_id="user123", estimated_tokens=1000)

    # 또는 데코레이터 사용
    @limiter.limit(user_id_param="user_id")
    async def analyze_gcode(user_id: str, content: str):
        ...
    ```
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()

        # 전역 토큰 버킷 (RPM 기준)
        self._global_bucket = TokenBucket(
            capacity=self.config.effective_rpm,
            refill_rate=self.config.effective_rpm / 60.0  # 초당 충전
        )

        # TPM 토큰 버킷
        self._token_bucket = TokenBucket(
            capacity=self.config.effective_tpm,
            refill_rate=self.config.effective_tpm / 60.0
        )

        # 사용자별 정보
        self._user_rates: Dict[str, UserRateInfo] = defaultdict(
            lambda: UserRateInfo(user_id="anonymous")
        )

        # 대기열
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=self.config.max_queue_size
        )
        self._queue_processor_task: Optional[asyncio.Task] = None

        # 통계
        self._stats = {
            "total_requests": 0,
            "rate_limited": 0,
            "queue_timeouts": 0,
            "total_tokens_used": 0
        }

        self._lock = asyncio.Lock()

    async def acquire(
        self,
        user_id: Optional[str] = None,
        estimated_tokens: int = 1000,
        timeout: float = 30.0,
        priority: int = 0
    ) -> bool:
        """
        Rate limit 토큰 획득

        Args:
            user_id: 사용자 ID (None이면 anonymous)
            estimated_tokens: 예상 토큰 사용량
            timeout: 대기 타임아웃 (초)
            priority: 우선순위 (높을수록 먼저)

        Returns:
            True if acquired, False if timeout

        Raises:
            RateLimitError: 사용자 제한 초과 시
        """
        user_id = user_id or "anonymous"

        async with self._lock:
            # 사용자별 제한 체크
            user_info = self._user_rates[user_id]
            user_info.reset_if_needed()

            # 일일 제한 체크
            if user_info.daily_count >= self.config.user_daily_limit:
                self._stats["rate_limited"] += 1
                raise RateLimitError(
                    f"일일 요청 한도 초과 ({self.config.user_daily_limit}회)",
                    retry_after=user_info.day_start + 86400 - time.time(),
                    error_code="daily_limit_exceeded"
                )

            # 분당 제한 체크
            if user_info.request_count >= self.config.user_rpm:
                wait_time = user_info.minute_start + 60 - time.time()
                if wait_time > timeout:
                    self._stats["rate_limited"] += 1
                    raise RateLimitError(
                        f"분당 요청 한도 초과 ({self.config.user_rpm}회)",
                        retry_after=wait_time,
                        error_code="rpm_limit_exceeded"
                    )

        # 전역 RPM 토큰 획득
        if not await self._global_bucket.acquire(1.0, timeout):
            self._stats["rate_limited"] += 1
            raise RateLimitError(
                "서버가 바쁩니다. 잠시 후 다시 시도해주세요.",
                retry_after=self._global_bucket.time_until_available(1.0),
                error_code="server_busy"
            )

        # TPM 토큰 획득
        if not await self._token_bucket.acquire(estimated_tokens, timeout):
            self._stats["rate_limited"] += 1
            raise RateLimitError(
                "토큰 한도에 도달했습니다. 잠시 후 다시 시도해주세요.",
                retry_after=self._token_bucket.time_until_available(estimated_tokens),
                error_code="token_limit_exceeded"
            )

        # 사용자 카운트 증가
        async with self._lock:
            user_info.request_count += 1
            user_info.daily_count += 1
            user_info.last_request = time.time()

        self._stats["total_requests"] += 1
        self._stats["total_tokens_used"] += estimated_tokens

        return True

    def check_user_limit(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        사용자 제한 상태 확인

        Returns:
            {
                "can_request": bool,
                "remaining_rpm": int,
                "remaining_daily": int,
                "retry_after": float (seconds, 0 if can_request)
            }
        """
        user_id = user_id or "anonymous"
        user_info = self._user_rates[user_id]
        user_info.reset_if_needed()

        remaining_rpm = max(0, self.config.user_rpm - user_info.request_count)
        remaining_daily = max(0, self.config.user_daily_limit - user_info.daily_count)

        can_request = remaining_rpm > 0 and remaining_daily > 0

        retry_after = 0.0
        if not can_request:
            if remaining_daily == 0:
                retry_after = user_info.day_start + 86400 - time.time()
            else:
                retry_after = user_info.minute_start + 60 - time.time()

        return {
            "can_request": can_request,
            "remaining_rpm": remaining_rpm,
            "remaining_daily": remaining_daily,
            "retry_after": max(0, retry_after)
        }

    def estimate_tokens(self, content: str) -> int:
        """
        텍스트의 토큰 수 추정

        간단한 휴리스틱: 4글자당 1토큰 (영어 기준)
        한글은 2글자당 1토큰 정도
        """
        # 간단한 추정
        ascii_chars = sum(1 for c in content if ord(c) < 128)
        non_ascii_chars = len(content) - ascii_chars

        return (ascii_chars // 4) + (non_ascii_chars // 2) + 100  # 버퍼

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            **self._stats,
            "global_bucket_tokens": self._global_bucket.tokens,
            "token_bucket_tokens": self._token_bucket.tokens,
            "active_users": len([u for u in self._user_rates.values() if time.time() - u.last_request < 60])
        }

    def limit(
        self,
        user_id_param: str = "user_id",
        estimate_tokens_from: Optional[str] = None
    ):
        """
        Rate limit 데코레이터

        사용법:
        ```python
        @limiter.limit(user_id_param="user_id", estimate_tokens_from="content")
        async def analyze(user_id: str, content: str):
            ...
        ```
        """
        def decorator(func: Callable[..., Awaitable[Any]]):
            async def wrapper(*args, **kwargs):
                # user_id 추출
                user_id = kwargs.get(user_id_param)

                # 토큰 추정
                estimated_tokens = 1000
                if estimate_tokens_from and estimate_tokens_from in kwargs:
                    content = kwargs[estimate_tokens_from]
                    if isinstance(content, str):
                        estimated_tokens = self.estimate_tokens(content)

                # Rate limit 획득
                await self.acquire(user_id=user_id, estimated_tokens=estimated_tokens)

                # 함수 실행
                return await func(*args, **kwargs)

            return wrapper
        return decorator


# 전역 인스턴스
_rate_limiter: Optional[GeminiRateLimiter] = None


def get_rate_limiter() -> GeminiRateLimiter:
    """전역 Rate Limiter 인스턴스 반환"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter


def configure_rate_limiter(config: RateLimitConfig) -> GeminiRateLimiter:
    """Rate Limiter 설정 및 반환"""
    global _rate_limiter
    _rate_limiter = GeminiRateLimiter(config)
    return _rate_limiter
