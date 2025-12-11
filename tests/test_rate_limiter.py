"""
Rate Limiter 테스트
"""
import asyncio
import pytest
import time
from gcode_analyzer.rate_limiter import (
    GeminiRateLimiter,
    RateLimitConfig,
    RateLimitError,
    TokenBucket,
    get_rate_limiter,
    configure_rate_limiter,
)


class TestTokenBucket:
    """TokenBucket 테스트"""

    def test_initial_capacity(self):
        """초기 용량 테스트"""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.tokens == 10.0

    def test_try_acquire_success(self):
        """토큰 획득 성공"""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.try_acquire(5.0) is True
        assert bucket.tokens == 5.0

    def test_try_acquire_failure(self):
        """토큰 부족 시 획득 실패"""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.try_acquire(15.0) is False
        assert bucket.tokens == 10.0  # 토큰 유지

    def test_refill(self):
        """토큰 충전 테스트"""
        bucket = TokenBucket(capacity=10.0, refill_rate=10.0)  # 초당 10개
        bucket.tokens = 0.0
        time.sleep(0.5)  # 0.5초 대기
        bucket._refill()
        assert bucket.tokens >= 4.0  # 약 5개 충전 (오차 허용)

    @pytest.mark.asyncio
    async def test_acquire_async(self):
        """비동기 토큰 획득"""
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)  # 빠른 충전
        assert await bucket.acquire(5.0, timeout=1.0) is True


class TestGeminiRateLimiter:
    """GeminiRateLimiter 테스트"""

    @pytest.fixture
    def limiter(self):
        """테스트용 Rate Limiter"""
        config = RateLimitConfig(
            global_rpm=100,
            global_tpm=100000,
            user_rpm=5,
            user_daily_limit=20
        )
        return GeminiRateLimiter(config)

    @pytest.mark.asyncio
    async def test_acquire_success(self, limiter):
        """정상 토큰 획득"""
        result = await limiter.acquire(user_id="test_user", estimated_tokens=100)
        assert result is True

    @pytest.mark.asyncio
    async def test_user_rpm_limit(self, limiter):
        """사용자 RPM 제한 테스트"""
        user_id = "rpm_test_user"

        # 5회 요청 (제한까지)
        for i in range(5):
            await limiter.acquire(user_id=user_id, estimated_tokens=100)

        # 6번째 요청은 실패해야 함
        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(user_id=user_id, estimated_tokens=100, timeout=0.1)

        assert exc_info.value.error_code == "rpm_limit_exceeded"

    @pytest.mark.asyncio
    async def test_user_daily_limit(self, limiter):
        """사용자 일일 제한 테스트"""
        # 일일 제한이 낮은 설정으로 테스트
        config = RateLimitConfig(user_rpm=100, user_daily_limit=3)
        test_limiter = GeminiRateLimiter(config)

        user_id = "daily_test_user"

        # 3회 요청 (일일 제한까지)
        for i in range(3):
            await test_limiter.acquire(user_id=user_id, estimated_tokens=100)

        # 4번째 요청은 실패해야 함
        with pytest.raises(RateLimitError) as exc_info:
            await test_limiter.acquire(user_id=user_id, estimated_tokens=100)

        assert exc_info.value.error_code == "daily_limit_exceeded"

    def test_check_user_limit(self, limiter):
        """사용자 제한 상태 확인"""
        status = limiter.check_user_limit("new_user")
        assert status["can_request"] is True
        assert status["remaining_rpm"] == 5
        assert status["remaining_daily"] == 20

    def test_estimate_tokens(self, limiter):
        """토큰 추정 테스트"""
        # 영어 텍스트
        english_text = "Hello world this is a test"
        tokens = limiter.estimate_tokens(english_text)
        assert tokens > 0

        # 한글 텍스트 (더 많은 토큰)
        korean_text = "안녕하세요 이것은 테스트입니다"
        korean_tokens = limiter.estimate_tokens(korean_text)
        assert korean_tokens > 0

    def test_get_stats(self, limiter):
        """통계 조회"""
        stats = limiter.get_stats()
        assert "total_requests" in stats
        assert "rate_limited" in stats
        assert "total_tokens_used" in stats


class TestGlobalInstance:
    """전역 인스턴스 테스트"""

    def test_get_rate_limiter(self):
        """전역 Rate Limiter 획득"""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2  # 동일 인스턴스

    def test_configure_rate_limiter(self):
        """Rate Limiter 설정"""
        config = RateLimitConfig(user_rpm=50)
        limiter = configure_rate_limiter(config)
        assert limiter.config.user_rpm == 50


@pytest.mark.asyncio
async def test_concurrent_requests():
    """동시 요청 테스트"""
    config = RateLimitConfig(
        global_rpm=1000,
        user_rpm=100,
        user_daily_limit=1000
    )
    limiter = GeminiRateLimiter(config)

    async def make_request(user_id: str, request_num: int):
        try:
            await limiter.acquire(user_id=user_id, estimated_tokens=100)
            return True
        except RateLimitError:
            return False

    # 10개의 동시 요청
    tasks = [make_request(f"user_{i % 3}", i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # 대부분 성공해야 함
    success_count = sum(results)
    assert success_count >= 5


if __name__ == "__main__":
    # 간단한 수동 테스트
    async def manual_test():
        print("=== Rate Limiter 수동 테스트 ===\n")

        config = RateLimitConfig(
            user_rpm=5,
            user_daily_limit=10
        )
        limiter = GeminiRateLimiter(config)

        user_id = "test_user"

        print(f"설정: RPM={config.user_rpm}, Daily={config.user_daily_limit}")
        print(f"초기 상태: {limiter.check_user_limit(user_id)}\n")

        # 여러 번 요청
        for i in range(7):
            try:
                await limiter.acquire(user_id=user_id, estimated_tokens=100)
                print(f"요청 {i+1}: 성공")
            except RateLimitError as e:
                print(f"요청 {i+1}: 실패 - {e.error_code} (retry_after: {e.retry_after:.1f}s)")

            status = limiter.check_user_limit(user_id)
            print(f"  남은 RPM: {status['remaining_rpm']}, 남은 Daily: {status['remaining_daily']}")

        print(f"\n통계: {limiter.get_stats()}")

    asyncio.run(manual_test())
