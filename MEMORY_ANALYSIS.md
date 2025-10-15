# 메모리 누수 및 잠재적 문제 분석 보고서

## 날짜: 2025-10-15

## 🔴 주요 문제점

### 1. **multipart 파일 업로드 - 전체 메모리 로드**
**위치:** `main.py:98`
```python
file_bytes = await upload.read()  # ⚠️ 전체 파일을 메모리에 로드
```

**문제:**
- 대용량 이미지 업로드 시 전체 파일이 메모리에 로드됨
- 100MB 이미지 10개 동시 업로드 시 1GB 메모리 사용

**해결 방법:**
```python
# 옵션 1: 파일 크기 제한
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
if len(file_bytes) > MAX_UPLOAD_SIZE:
    raise HTTPException(status_code=413, detail="File too large")

# 옵션 2: 스트리밍 처리 (더 복잡)
```

### 2. **base64 인코딩으로 메모리 2배 증가**
**위치:** `utill.py:33-36`
```python
async def to_data_url_from_url(url: str, mime_type: Optional[str] = None) -> str:
    async with get_httpx_client() as client:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        content = r.content  # 원본 크기
    b64 = base64.b64encode(content).decode("utf-8")  # +33% 크기 증가
    mt = mime_type or "image/png"
    return f"data:{mt};base64,{b64}"  # 최종적으로 메모리 2배 사용
```

**문제:**
- 10MB 이미지 → 13.3MB base64 → 최대 23MB 메모리 사용 (원본 + base64)
- `to_data_url_from_bytes()`도 동일한 문제

**영향:**
- `start_image_to_3d()`: URL에서 다운로드 → base64 변환
- `start_image_to_3d_from_bytes()`: 업로드된 파일 → base64 변환

### 3. **응답 로그에 전체 데이터 출력**
**위치:** `main.py:129, 150`
```python
logger.info("[Modelling] Response (multipart): %s",
            json.dumps(response_data, ensure_ascii=False, default=str))
```

**문제:**
- `response_data`에 `raw` 필드가 포함되면 전체 API 응답이 로그에 출력됨
- base64 인코딩된 이미지 URL이 포함되면 로그 파일이 폭발적으로 증가

**해결 방법:**
```python
# 로그용 축약된 데이터 생성
log_data = {k: v for k, v in response_data.items() if k not in ['raw', 'request_payload']}
log_data['task_id'] = response_data.get('task_id')
log_data['status'] = response_data.get('status')
logger.info("[Modelling] Response: %s", log_data)
```

### 4. **폴링 루프 - 무한 대기 가능성**
**위치:** `modelling_api.py:96-114`
```python
async def poll_until_done(endpoint: str, task_id: str, timeout_sec: int = 20 * 60, interval: int = 6):
    start = time.monotonic()
    last_status: Optional[str] = None
    while True:  # ⚠️ 무한 루프
        if time.monotonic() - start > timeout_sec:
            raise TimeoutError(...)
        task = await meshy_get_task(endpoint, task_id)
        status = str(task.get("status", "")).upper()
        # ...
        if status in ("PENDING", "PROCESSING"):
            await asyncio.sleep(interval)
            continue  # 계속 반복
```

**문제:**
- timeout이 20분(1200초)으로 설정되어 있음
- 여러 요청이 동시에 폴링하면 메모리 및 연결 누적

**현재 상태:** 타임아웃이 있으므로 **문제 없음**, 하지만 모니터링 필요

### 5. **output 디렉토리 파일 누적**
**위치:** `main.py:100-110`, `utill.py:80-95`

**문제:**
- 업로드된 파일, 다운로드된 GLB 파일 등이 계속 축적됨
- 자동 삭제 메커니즘 없음

**해결 방법:**
```python
# 정기적인 파일 정리 작업 추가
# 예: 7일 이상 된 파일 삭제
```

## 🟡 경미한 문제점

### 6. **print() 문 남아있음**
**위치:** `main.py:135`
```python
print(payload)  # ⚠️ 프로덕션에서 제거 권장
```

**해결 방법:**
```python
logger.debug("Payload: %s", payload)  # logger 사용
```

### 7. **httpx 타임아웃 관리**
**위치:** `utill.py:17-19`
```python
def get_httpx_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(60.0)
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)
```

**문제:**
- 모든 HTTP 요청에 60초 타임아웃 적용
- 대용량 파일 다운로드 시 부족할 수 있음

**현재:** `download_file()`에서 `timeout=180` 사용하므로 **문제 없음**

## ✅ 권장 수정 사항

### 우선순위 1 (높음)
1. **파일 크기 제한 추가** - 업로드 크기 제한
2. **응답 로그 축약** - 민감한/대용량 데이터 제외

### 우선순위 2 (중간)
3. **파일 정리 작업** - 오래된 파일 자동 삭제
4. **print() 제거** - logger로 대체

### 우선순위 3 (낮음)
5. **메모리 사용량 모니터링** 추가

## 📊 예상 메모리 사용량

### 시나리오 1: 단일 이미지 to 3D (10MB 이미지)
```
- 파일 업로드: 10MB (file_bytes)
- base64 인코딩: 13.3MB
- 디스크 저장: 10MB
- 총 메모리: ~23MB (동시에 메모리 상주)
- 요청 완료 후: GC로 정리됨
```

### 시나리오 2: 10개 동시 요청
```
- 총 메모리: ~230MB
- FastAPI 오버헤드: ~50MB
- 합계: ~280MB
```

### 결론
**현재 코드는 일반적인 사용에서 메모리 누수 없음**
- 모든 리소스가 적절히 정리됨 (context manager 사용)
- 하지만 대용량 파일 처리 시 메모리 스파이크 발생 가능

## 권장 조치
1. 파일 크기 제한 (50MB)
2. 로그 출력 최적화
3. 주기적인 파일 정리
