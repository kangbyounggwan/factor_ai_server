# 3D 프린터 출력 불량 감지 AI 시스템 개발 계획 v2.0
## Spaghetti Detective 모델 기반 + 실패 장면 자동 수집

## 📋 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [기술 스택 (업데이트)](#기술-스택)
4. [개발 단계별 계획](#개발-단계별-계획)
5. [실패 장면 수집 시스템](#실패-장면-수집-시스템)
6. [API 설계](#api-설계)
7. [프론트엔드 통합](#프론트엔드-통합)
8. [배포 및 운영](#배포-및-운영)

---

## 프로젝트 개요

### 목표
WebRTC 카메라 스트리밍을 활용하여 3D 프린터 출력 과정을 실시간 모니터링하고, **사전 학습된 Spaghetti Detective AI 모델**로 불량을 감지:
- **스파게티화 (Spaghetti)**: 필라멘트가 엉켜서 출력되는 현상
- **레이어 분리 (Layer Separation)**: 레이어 간 접착 불량
- **와핑 (Warping)**: 출력물 모서리가 들뜨는 현상
- **노즐 막힘 (Clogging)**: 필라멘트 압출 불량
- **서포트 붕괴 (Support Failure)**: 서포트 구조 붕괴
- **첫 레이어 실패 (First Layer Failure)**: 베드 접착 실패

### 핵심 기능
1. **실시간 모니터링**: WebRTC 스트림에서 프레임 추출 및 분석
2. **AI 불량 감지**: **Spaghetti Detective 사전학습 모델** 사용 (학습 불필요!)
3. **예측 정보 생성**: 불량 타입, 신뢰도, 위치, 시간 등
4. **MQTT 알림**: 불량 감지 시 실시간 알림
5. **실패 장면 자동 수집**: 감지된 불량 프레임을 DB/Storage에 자동 저장 ⭐ **NEW**
6. **데이터셋 구축**: 수집된 데이터로 향후 커스텀 모델 학습 가능 ⭐ **NEW**
7. **이력 관리**: DB에 감지 이력 저장 및 대시보드 제공

### ⚡ 주요 변경사항 (v2.0)
- ✅ **학습 불필요**: Spaghetti Detective 사전학습 모델 사용
- ✅ **즉시 배포 가능**: 개발 기간 12주 → **4주로 단축**
- ✅ **실패 장면 자동 저장**: 감지 시 프레임 + 메타데이터 자동 DB 저장
- ✅ **데이터셋 축적**: 실전 데이터 자동 수집으로 향후 개선 가능
- ✅ **비용 절감**: 라벨링 작업 불필요

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Web)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ CameraFeed   │  │ AI Dashboard │  │ Alert Panel  │      │
│  │ (WebRTC)     │  │ (Detection)  │  │ (MQTT Sub)   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │               │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼──────────────┐
│         │                  │ HTTP API         │ MQTT          │
│         ▼                  ▼                  ▼               │
│  ┌──────────────────────────────────────────────────┐        │
│  │           FastAPI Server (main.py)               │        │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐ │        │
│  │  │ WebRTC     │  │ AI Model   │  │ MQTT       │ │        │
│  │  │ Frame      │  │ Inference  │  │ Publisher  │ │        │
│  │  │ Capture    │  │ Service    │  │            │ │        │
│  │  └─────┬──────┘  └─────┬──────┘  └────────────┘ │        │
│  └────────┼───────────────┼──────────────────────────┘        │
│           │               │                                   │
│  ┌────────▼───────────────▼──────────────┐                   │
│  │  Spaghetti Detective Model (Pre-trained) ⭐             │
│  │  ┌──────────────────────────────────┐  │                   │
│  │  │ - No Training Required           │  │                   │
│  │  │ - 3D Print Failure Specialized   │  │                   │
│  │  │ - High Accuracy (proven)         │  │                   │
│  │  └──────────────────────────────────┘  │                   │
│  └────────┬──────────────────────────────┘                   │
│           │                                                   │
│  ┌────────▼─────────────────────────────┐                    │
│  │  Failure Scene Collector ⭐ NEW      │                    │
│  │  ┌──────────────────────────────┐   │                    │
│  │  │ Auto-save detected frames    │   │                    │
│  │  │ Build training dataset       │   │                    │
│  │  └──────────────────────────────┘   │                    │
│  └────────┬──────────────────────────────┘                   │
│           │                                                   │
└───────────┼───────────────────────────────────────────────────┘
            │
            ▼
   ┌────────────────────┐
   │   Supabase DB      │
   │  ┌──────────────┐  │
   │  │ detections   │  │  - 감지 이력
   │  │ failure_scenes│ │  - 실패 장면 (NEW) ⭐
   │  │ print_jobs   │  │  - 출력 작업
   │  │ cameras      │  │  - 카메라 정보
   │  │ alerts       │  │  - 알림 이력
   │  └──────────────┘  │
   └────────────────────┘
            │
            ▼
   ┌────────────────────┐
   │ Supabase Storage   │
   │  ┌──────────────┐  │
   │  │ failure_frames│ │  - 불량 프레임 이미지 ⭐
   │  │ annotated_imgs│ │  - 바운딩박스 표시 이미지
   │  │ video_clips  │  │  - 불량 발생 전후 영상 (선택)
   │  └──────────────┘  │
   └────────────────────┘
```

---

## 기술 스택 (업데이트)

### Backend (Python)
- **FastAPI**: REST API 서버
- **OpenCV**: 비디오 프레임 처리
- **PyTorch**: 딥러닝 추론
- **Spaghetti Detective Model**: 사전학습 3D 프린터 불량 감지 모델 ⭐ **핵심**
- **paho-mqtt**: MQTT 클라이언트
- **Pillow**: 이미지 처리

### AI Model (사전학습 - 학습 불필요!)
- **Spaghetti Detective Pre-trained Model**
  - 출처: [TheSpaghettiDetective/ml_api](https://github.com/TheSpaghettiDetective/ml_api)
  - 크기: ~50MB
  - 추론 속도: ~30 FPS (GPU)
  - 특징: 3D 프린터 전용, 실전 검증됨
  - **라벨링/학습 불필요!** ✅

### Frontend (React/TypeScript)
- **WebRTC API**: 카메라 스트리밍
- **MQTT.js**: 실시간 알림 수신
- **Canvas API**: 감지 결과 오버레이
- **React Query**: 이력 데이터 관리

### Database & Storage
- **Supabase PostgreSQL**: 메타데이터 저장
- **Supabase Storage**: 실패 장면 이미지/영상 저장 ⭐
- **Redis** (선택): 실시간 상태 캐싱

---

## 개발 단계별 계획 (4주로 단축!)

### Phase 1: Spaghetti Detective 모델 통합 (Week 1)

#### 1.1 모델 다운로드 및 설치

**파일**: `setup_model.py`

```python
"""
Spaghetti Detective 모델 다운로드 및 설정
"""
import os
import requests
from pathlib import Path
import torch

MODEL_DIR = Path("./models")
MODEL_DIR.mkdir(exist_ok=True)

def download_spaghetti_detective_model():
    """
    Spaghetti Detective 사전학습 모델 다운로드

    출처: https://github.com/TheSpaghettiDetective/ml_api
    """
    model_url = "https://github.com/TheSpaghettiDetective/ml_api/releases/download/v1.0/spaghetti_detector.pth"
    model_path = MODEL_DIR / "spaghetti_detector.pth"

    if model_path.exists():
        print(f"✅ Model already exists: {model_path}")
        return model_path

    print(f"📥 Downloading Spaghetti Detective model...")
    response = requests.get(model_url, stream=True)
    response.raise_for_status()

    with open(model_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"✅ Model downloaded: {model_path}")
    return model_path

def verify_model():
    """모델 로드 테스트"""
    model_path = MODEL_DIR / "spaghetti_detector.pth"

    try:
        # PyTorch 모델 로드 테스트
        model = torch.load(model_path, map_location='cpu')
        print("✅ Model verification successful")
        return True
    except Exception as e:
        print(f"❌ Model verification failed: {e}")
        return False

if __name__ == "__main__":
    # 모델 다운로드
    model_path = download_spaghetti_detective_model()

    # 검증
    if verify_model():
        print("\n🎉 Setup complete! Ready to use.")
    else:
        print("\n❌ Setup failed. Please check the model file.")
```

**실행**:
```bash
python setup_model.py
```

**작업**:
- [ ] Spaghetti Detective 모델 다운로드
- [ ] 모델 로드 테스트
- [ ] 추론 속도 벤치마크

#### 1.2 AI 추론 서비스 (사전학습 모델 사용)

**파일**: `ai_inference_pretrained.py`

```python
"""
Spaghetti Detective 사전학습 모델 기반 추론 서비스
"""
import cv2
import numpy as np
import torch
from typing import List, Dict, Optional
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

MODEL_PATH = "./models/spaghetti_detector.pth"
CONFIDENCE_THRESHOLD = 0.7  # Spaghetti Detective 권장값

class SpaghettiDetectiveInference:
    """Spaghetti Detective 추론 서비스"""

    def __init__(self, model_path: str = MODEL_PATH):
        """
        Args:
            model_path: 사전학습 모델 경로
        """
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model = self._load_model(model_path)
        self.model.eval()
        logger.info(f"[AI] Spaghetti Detective model loaded on {self.device}")

    def _load_model(self, model_path: str):
        """모델 로드"""
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        model = torch.load(model_path, map_location=self.device)
        model.to(self.device)
        return model

    def preprocess_frame(self, frame: np.ndarray) -> torch.Tensor:
        """
        프레임 전처리

        Spaghetti Detective 입력 형식:
        - 크기: 300x300
        - 정규화: ImageNet 평균/표준편차
        """
        # 리사이즈
        resized = cv2.resize(frame, (300, 300))

        # BGR → RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # 정규화
        normalized = rgb.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        normalized = (normalized - mean) / std

        # Tensor 변환 [H, W, C] → [C, H, W]
        tensor = torch.from_numpy(normalized).permute(2, 0, 1)
        tensor = tensor.unsqueeze(0)  # Batch dimension

        return tensor.to(self.device)

    async def predict(
        self,
        frame: np.ndarray,
        conf_threshold: float = CONFIDENCE_THRESHOLD
    ) -> List[Dict]:
        """
        불량 감지 추론

        Args:
            frame: OpenCV 이미지 (BGR)
            conf_threshold: 신뢰도 임계값

        Returns:
            감지 결과 리스트
            [
                {
                    'detection_type': 'spaghetti',
                    'confidence': 0.95,
                    'severity': 'critical',
                    'timestamp': '2025-01-26T10:30:00Z',
                    'bbox': [x, y, w, h]  # 모델이 제공하는 경우
                },
                ...
            ]
        """
        if frame is None or frame.size == 0:
            logger.warning("[AI] Empty frame received")
            return []

        try:
            # 전처리
            input_tensor = self.preprocess_frame(frame)

            # 추론
            with torch.no_grad():
                outputs = self.model(input_tensor)

            # 결과 파싱
            detections = self._parse_outputs(outputs, conf_threshold)

            if detections:
                logger.info(f"[AI] Detected {len(detections)} failure(s)")
                for det in detections:
                    logger.info(
                        f"[AI]   - {det['detection_type']}: "
                        f"{det['confidence']:.2f} ({det['severity']})"
                    )

            return detections

        except Exception as e:
            logger.error(f"[AI] Prediction failed: {str(e)}")
            return []

    def _parse_outputs(
        self,
        outputs: torch.Tensor,
        conf_threshold: float
    ) -> List[Dict]:
        """
        모델 출력 파싱

        Spaghetti Detective 출력 형식:
        - outputs['failure_detected']: bool
        - outputs['confidence']: float (0-1)
        - outputs['failure_type']: str ('spaghetti', 'warping', etc.)
        - outputs['bbox']: [x, y, w, h] (선택적)
        """
        detections = []

        # 불량 감지 여부
        if not outputs.get('failure_detected', False):
            return []

        confidence = outputs.get('confidence', 0.0)

        if confidence < conf_threshold:
            return []

        failure_type = outputs.get('failure_type', 'unknown')

        # 심각도 매핑
        severity_map = {
            'spaghetti': 'critical',
            'warping': 'high',
            'layer_separation': 'high',
            'clogging': 'medium',
            'support_failure': 'medium',
            'first_layer_fail': 'critical'
        }

        detection = {
            'detection_type': failure_type,
            'confidence': round(confidence, 4),
            'severity': severity_map.get(failure_type, 'medium'),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        # 바운딩 박스 (있는 경우)
        if 'bbox' in outputs:
            detection['bbox'] = outputs['bbox']

        detections.append(detection)

        return detections

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict]
    ) -> np.ndarray:
        """
        프레임에 감지 결과 그리기
        """
        annotated = frame.copy()

        color_map = {
            'critical': (0, 0, 255),    # 빨강
            'high': (0, 165, 255),      # 주황
            'medium': (0, 255, 255),    # 노랑
            'low': (0, 255, 0)          # 초록
        }

        for det in detections:
            severity = det['severity']
            conf = det['confidence']
            det_type = det['detection_type']

            color = color_map.get(severity, (255, 255, 255))

            # 바운딩 박스가 있으면 그리기
            if 'bbox' in det:
                x, y, w, h = det['bbox']
                cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 3)

            # 텍스트 라벨
            label = f"{det_type}: {conf:.2f}"

            # 화면 상단에 경고 표시
            cv2.putText(
                annotated,
                f"WARNING: {label.upper()}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                color,
                2
            )

            # Severity 표시
            cv2.putText(
                annotated,
                f"Severity: {severity.upper()}",
                (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2
            )

        return annotated

# 싱글톤 인스턴스
_ai_service: Optional[SpaghettiDetectiveInference] = None

def get_ai_service() -> SpaghettiDetectiveInference:
    """AI 서비스 싱글톤"""
    global _ai_service
    if _ai_service is None:
        _ai_service = SpaghettiDetectiveInference()
    return _ai_service
```

**작업**:
- [ ] Spaghetti Detective 모델 통합
- [ ] 전처리 파이프라인 구현
- [ ] 추론 테스트

---

### Phase 2: 실패 장면 자동 수집 시스템 (Week 1) ⭐ **핵심**

#### 2.1 실패 장면 DB 스키마

**Supabase SQL**:

```sql
-- 실패 장면 테이블 (NEW)
CREATE TABLE failure_scenes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    device_uuid UUID NOT NULL,
    detection_id UUID REFERENCES print_detections(id),
    print_job_id UUID REFERENCES print_jobs(id),

    -- 감지 정보
    failure_type VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    severity VARCHAR(20) NOT NULL,

    -- 프레임 정보
    frame_timestamp TIMESTAMPTZ NOT NULL,
    frame_number INTEGER,

    -- 이미지 저장 (Supabase Storage)
    original_frame_url TEXT NOT NULL,      -- 원본 프레임
    annotated_frame_url TEXT,              -- 바운딩박스 표시
    before_frames_url TEXT,                -- 불량 발생 전 프레임 (선택)
    after_frames_url TEXT,                 -- 불량 발생 후 프레임 (선택)

    -- 출력 컨텍스트
    layer_number INTEGER,
    print_progress FLOAT,
    nozzle_temp FLOAT,
    bed_temp FLOAT,
    print_speed FLOAT,

    -- 라벨링 상태 (향후 학습용)
    is_verified BOOLEAN DEFAULT FALSE,     -- 사람이 검증했는지
    verified_by UUID REFERENCES auth.users(id),
    verified_at TIMESTAMPTZ,
    is_false_positive BOOLEAN DEFAULT FALSE,
    corrected_type VARCHAR(50),            -- 수정된 타입 (있는 경우)

    -- 데이터셋 포함 여부
    include_in_dataset BOOLEAN DEFAULT TRUE,
    dataset_split VARCHAR(20),             -- 'train', 'val', 'test'

    -- 메타데이터
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_failure_scenes_user ON failure_scenes(user_id, created_at DESC);
CREATE INDEX idx_failure_scenes_device ON failure_scenes(device_uuid, created_at DESC);
CREATE INDEX idx_failure_scenes_type ON failure_scenes(failure_type);
CREATE INDEX idx_failure_scenes_verified ON failure_scenes(is_verified, include_in_dataset);

-- RLS 정책
ALTER TABLE failure_scenes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own failure scenes"
    ON failure_scenes FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own failure scenes"
    ON failure_scenes FOR INSERT
    WITH CHECK (auth.uid() = user_id);
```

#### 2.2 실패 장면 수집 서비스

**파일**: `failure_scene_collector.py`

```python
"""
실패 장면 자동 수집 서비스
- 감지된 불량 프레임 자동 저장
- 전후 컨텍스트 프레임 저장 (선택)
- 메타데이터 DB 저장
"""
import cv2
import numpy as np
from typing import Dict, List, Optional
import logging
from datetime import datetime
from pathlib import Path
import uuid
from collections import deque

from supabase_storage import (
    upload_failure_frame,
    upload_failure_video_clip
)
from supabase_db import save_failure_scene

logger = logging.getLogger("uvicorn.error")

class FailureSceneCollector:
    """실패 장면 수집기"""

    def __init__(
        self,
        device_uuid: str,
        user_id: str,
        print_job_id: Optional[str] = None,
        buffer_size: int = 30,  # 30프레임 버퍼 (약 5초)
        save_context: bool = True  # 전후 프레임 저장 여부
    ):
        """
        Args:
            device_uuid: 디바이스 UUID
            user_id: 사용자 ID
            print_job_id: 출력 작업 ID
            buffer_size: 전후 프레임 버퍼 크기
            save_context: 전후 컨텍스트 프레임 저장 여부
        """
        self.device_uuid = device_uuid
        self.user_id = user_id
        self.print_job_id = print_job_id
        self.save_context = save_context

        # 프레임 버퍼 (최근 N개 프레임 저장)
        self.frame_buffer: deque = deque(maxlen=buffer_size)
        self.frame_counter = 0

    def add_frame(self, frame: np.ndarray):
        """
        프레임을 버퍼에 추가

        Args:
            frame: OpenCV 이미지
        """
        if self.save_context:
            self.frame_buffer.append({
                'frame': frame.copy(),
                'timestamp': datetime.utcnow(),
                'frame_number': self.frame_counter
            })

        self.frame_counter += 1

    async def collect_failure_scene(
        self,
        current_frame: np.ndarray,
        annotated_frame: np.ndarray,
        detection: Dict,
        print_context: Optional[Dict] = None
    ) -> str:
        """
        실패 장면 수집 및 저장

        Args:
            current_frame: 현재 원본 프레임
            annotated_frame: 어노테이션된 프레임
            detection: 감지 정보
            print_context: 출력 컨텍스트 (온도, 속도 등)

        Returns:
            failure_scene_id: 저장된 장면 ID
        """
        scene_id = str(uuid.uuid4())

        logger.info(f"[Collector] Collecting failure scene: {scene_id}")

        try:
            # 1. 현재 프레임 저장
            original_url = await upload_failure_frame(
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                scene_id=scene_id,
                frame=current_frame,
                frame_type='original'
            )

            annotated_url = await upload_failure_frame(
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                scene_id=scene_id,
                frame=annotated_frame,
                frame_type='annotated'
            )

            logger.info(f"[Collector] Frames uploaded: {scene_id}")

            # 2. 전후 컨텍스트 저장 (선택)
            before_url = None
            after_url = None

            if self.save_context and len(self.frame_buffer) > 0:
                # 불량 발생 전 프레임 (최근 15프레임)
                before_frames = list(self.frame_buffer)[-15:]
                before_url = await self._save_context_video(
                    scene_id,
                    before_frames,
                    'before'
                )

                logger.info(f"[Collector] Context frames saved: {scene_id}")

            # 3. DB에 메타데이터 저장
            scene_data = {
                'id': scene_id,
                'user_id': self.user_id,
                'device_uuid': self.device_uuid,
                'print_job_id': self.print_job_id,
                'detection_id': detection.get('detection_id'),

                'failure_type': detection['detection_type'],
                'confidence': detection['confidence'],
                'severity': detection['severity'],

                'frame_timestamp': detection['timestamp'],
                'frame_number': self.frame_counter,

                'original_frame_url': original_url,
                'annotated_frame_url': annotated_url,
                'before_frames_url': before_url,
                'after_frames_url': after_url,

                # 출력 컨텍스트
                'layer_number': print_context.get('layer_number') if print_context else None,
                'print_progress': print_context.get('progress') if print_context else None,
                'nozzle_temp': print_context.get('nozzle_temp') if print_context else None,
                'bed_temp': print_context.get('bed_temp') if print_context else None,
                'print_speed': print_context.get('print_speed') if print_context else None,
            }

            await save_failure_scene(scene_data)

            logger.info(
                f"[Collector] ✅ Failure scene saved: {scene_id} "
                f"({detection['detection_type']})"
            )

            return scene_id

        except Exception as e:
            logger.error(f"[Collector] Failed to collect scene: {str(e)}")
            raise

    async def _save_context_video(
        self,
        scene_id: str,
        frames: List[Dict],
        video_type: str  # 'before' or 'after'
    ) -> Optional[str]:
        """
        전후 프레임을 비디오로 저장

        Args:
            scene_id: 장면 ID
            frames: 프레임 리스트
            video_type: 'before' or 'after'

        Returns:
            비디오 URL
        """
        if not frames:
            return None

        try:
            # 임시 비디오 파일 생성
            temp_video_path = f"/tmp/{scene_id}_{video_type}.mp4"

            # VideoWriter 설정
            first_frame = frames[0]['frame']
            height, width = first_frame.shape[:2]

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 6  # 6 FPS로 저장 (빠르게 재생)
            writer = cv2.VideoWriter(
                temp_video_path,
                fourcc,
                fps,
                (width, height)
            )

            # 프레임 쓰기
            for frame_data in frames:
                writer.write(frame_data['frame'])

            writer.release()

            # Supabase Storage 업로드
            video_url = await upload_failure_video_clip(
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                scene_id=scene_id,
                video_path=temp_video_path,
                video_type=video_type
            )

            # 임시 파일 삭제
            Path(temp_video_path).unlink(missing_ok=True)

            logger.info(f"[Collector] Context video saved: {video_type}")

            return video_url

        except Exception as e:
            logger.error(f"[Collector] Failed to save context video: {str(e)}")
            return None
```

**작업**:
- [ ] 실패 장면 DB 스키마 생성
- [ ] 수집 서비스 구현
- [ ] Storage 업로드 함수 구현
- [ ] 테스트

---

### Phase 3: 통합 및 API 구현 (Week 2)

#### 3.1 Supabase Storage 업로드 함수

**파일**: `supabase_storage.py` (추가)

```python
"""
Supabase Storage 업로드 함수
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Optional
import logging

from supabase_client import get_supabase_client

logger = logging.getLogger("uvicorn.error")

BUCKET_FAILURE_FRAMES = "failure_frames"
BUCKET_FAILURE_VIDEOS = "failure_videos"

async def upload_failure_frame(
    user_id: str,
    device_uuid: str,
    scene_id: str,
    frame: np.ndarray,
    frame_type: str = 'original'  # 'original' or 'annotated'
) -> str:
    """
    실패 프레임을 Supabase Storage에 업로드

    Args:
        user_id: 사용자 ID
        device_uuid: 디바이스 UUID
        scene_id: 장면 ID
        frame: OpenCV 이미지
        frame_type: 'original' or 'annotated'

    Returns:
        Public URL
    """
    try:
        supabase = get_supabase_client()

        # 파일명 생성
        filename = f"{user_id}/{device_uuid}/{scene_id}_{frame_type}.jpg"

        # 이미지 인코딩
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        image_bytes = buffer.tobytes()

        # 업로드
        response = supabase.storage.from_(BUCKET_FAILURE_FRAMES).upload(
            path=filename,
            file=image_bytes,
            file_options={"content-type": "image/jpeg"}
        )

        # Public URL 생성
        public_url = supabase.storage.from_(BUCKET_FAILURE_FRAMES).get_public_url(filename)

        logger.info(f"[Storage] Frame uploaded: {filename}")

        return public_url

    except Exception as e:
        logger.error(f"[Storage] Upload failed: {str(e)}")
        raise

async def upload_failure_video_clip(
    user_id: str,
    device_uuid: str,
    scene_id: str,
    video_path: str,
    video_type: str = 'before'  # 'before' or 'after'
) -> str:
    """
    비디오 클립을 Supabase Storage에 업로드
    """
    try:
        supabase = get_supabase_client()

        filename = f"{user_id}/{device_uuid}/{scene_id}_{video_type}.mp4"

        with open(video_path, 'rb') as f:
            video_bytes = f.read()

        response = supabase.storage.from_(BUCKET_FAILURE_VIDEOS).upload(
            path=filename,
            file=video_bytes,
            file_options={"content-type": "video/mp4"}
        )

        public_url = supabase.storage.from_(BUCKET_FAILURE_VIDEOS).get_public_url(filename)

        logger.info(f"[Storage] Video uploaded: {filename}")

        return public_url

    except Exception as e:
        logger.error(f"[Storage] Video upload failed: {str(e)}")
        raise
```

#### 3.2 Supabase DB 저장 함수

**파일**: `supabase_db.py` (추가)

```python
"""
Supabase DB 저장 함수
"""
from typing import Dict
import logging

from supabase_client import get_supabase_client

logger = logging.getLogger("uvicorn.error")

async def save_failure_scene(scene_data: Dict) -> Dict:
    """
    실패 장면을 DB에 저장

    Args:
        scene_data: 장면 데이터

    Returns:
        저장된 레코드
    """
    try:
        supabase = get_supabase_client()

        response = supabase.table('failure_scenes').insert(scene_data).execute()

        logger.info(f"[DB] Failure scene saved: {scene_data['id']}")

        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"[DB] Save failed: {str(e)}")
        raise

async def get_failure_scenes(
    user_id: str,
    device_uuid: Optional[str] = None,
    failure_type: Optional[str] = None,
    verified_only: bool = False,
    limit: int = 100
) -> List[Dict]:
    """
    실패 장면 조회
    """
    try:
        supabase = get_supabase_client()

        query = supabase.table('failure_scenes').select('*')
        query = query.eq('user_id', user_id)

        if device_uuid:
            query = query.eq('device_uuid', device_uuid)

        if failure_type:
            query = query.eq('failure_type', failure_type)

        if verified_only:
            query = query.eq('is_verified', True)

        query = query.order('created_at', desc=True).limit(limit)

        response = query.execute()

        return response.data

    except Exception as e:
        logger.error(f"[DB] Query failed: {str(e)}")
        return []
```

#### 3.3 모니터링 워커 통합

**파일**: `monitoring_worker.py` (수정)

```python
# ... (이전 코드)

from failure_scene_collector import FailureSceneCollector

class MonitoringWorker:
    def __init__(self, ...):
        # ... (기존 코드)

        # 실패 장면 수집기 추가 ⭐
        self.scene_collector = FailureSceneCollector(
            device_uuid=device_uuid,
            user_id=user_id,
            print_job_id=print_job_id,
            save_context=True  # 전후 프레임 저장
        )

    async def _monitoring_loop(self):
        while self.is_running:
            try:
                frame = await self.capture.get_frame()

                if frame is None:
                    # ... (에러 처리)
                    continue

                # 프레임을 버퍼에 추가 (컨텍스트용) ⭐
                self.scene_collector.add_frame(frame)

                # AI 분석
                detections = await self.ai_service.predict(frame)

                if detections:
                    annotated_frame = self.ai_service.draw_detections(frame, detections)

                    for det in detections:
                        # 기존 처리
                        await self._process_detection(det, annotated_frame)

                        # 실패 장면 수집 ⭐ NEW
                        await self._collect_failure_scene(
                            frame,
                            annotated_frame,
                            det
                        )

                await asyncio.sleep(self.frame_interval)

            except Exception as e:
                logger.error(f"[Worker] Error: {str(e)}")

    async def _collect_failure_scene(
        self,
        frame: np.ndarray,
        annotated_frame: np.ndarray,
        detection: Dict
    ):
        """
        실패 장면 수집 (NEW)
        """
        try:
            # 출력 컨텍스트 가져오기
            print_context = await self._get_print_context()

            # 장면 수집
            scene_id = await self.scene_collector.collect_failure_scene(
                current_frame=frame,
                annotated_frame=annotated_frame,
                detection=detection,
                print_context=print_context
            )

            logger.info(f"[Worker] Failure scene collected: {scene_id}")

        except Exception as e:
            logger.error(f"[Worker] Scene collection failed: {str(e)}")

    async def _get_print_context(self) -> Dict:
        """
        현재 출력 컨텍스트 정보 가져오기
        (MQTT 또는 DB에서)
        """
        # TODO: MQTT 토픽에서 실시간 정보 가져오기
        return {
            'layer_number': 120,
            'progress': 45.5,
            'nozzle_temp': 205.0,
            'bed_temp': 60.0,
            'print_speed': 50.0
        }
```

**작업**:
- [ ] Storage 업로드 함수 구현
- [ ] DB 저장 함수 구현
- [ ] 워커에 수집기 통합
- [ ] 테스트

---

### Phase 4: 프론트엔드 - 실패 장면 관리 (Week 3)

#### 4.1 실패 장면 대시보드

**파일**: `packages/web/src/components/FailureScenesDashboard.tsx`

```typescript
/**
 * 실패 장면 대시보드
 * - 수집된 실패 장면 목록 표시
 * - 검증 UI (사람이 확인)
 * - 데이터셋 관리
 */
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Check, X, Eye, Download } from 'lucide-react';

interface FailureScene {
  id: string;
  failure_type: string;
  confidence: number;
  severity: string;
  original_frame_url: string;
  annotated_frame_url: string;
  before_frames_url?: string;
  frame_timestamp: string;
  is_verified: boolean;
  is_false_positive: boolean;
  layer_number?: number;
  print_progress?: number;
}

export const FailureScenesDashboard = ({ deviceUuid }: { deviceUuid?: string }) => {
  const [scenes, setScenes] = useState<FailureScene[]>([]);
  const [filter, setFilter] = useState<'all' | 'unverified' | 'verified'>('all');

  // 장면 목록 로드
  useEffect(() => {
    fetchScenes();
  }, [deviceUuid, filter]);

  const fetchScenes = async () => {
    const params = new URLSearchParams();
    if (deviceUuid) params.append('device_uuid', deviceUuid);
    if (filter === 'unverified') params.append('unverified_only', 'true');
    if (filter === 'verified') params.append('verified_only', 'true');

    const response = await fetch(`/v1/failure-scenes?${params}`);
    const data = await response.json();
    setScenes(data.scenes || []);
  };

  // 검증 (정확함)
  const handleVerify = async (sceneId: string, isCorrect: boolean) => {
    await fetch(`/v1/failure-scenes/${sceneId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        is_correct: isCorrect,
        is_false_positive: !isCorrect
      })
    });

    await fetchScenes();
  };

  // 데이터셋 내보내기
  const handleExportDataset = async () => {
    const response = await fetch('/v1/failure-scenes/export-dataset', {
      method: 'POST'
    });

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `failure_dataset_${Date.now()}.zip`;
    link.click();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Failure Scenes ({scenes.length})</span>
            <div className="flex gap-2">
              <Button onClick={handleExportDataset} size="sm">
                <Download className="w-4 h-4 mr-2" />
                Export Dataset
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* 필터 */}
          <div className="flex gap-2 mb-4">
            <Button
              variant={filter === 'all' ? 'default' : 'outline'}
              onClick={() => setFilter('all')}
              size="sm"
            >
              All
            </Button>
            <Button
              variant={filter === 'unverified' ? 'default' : 'outline'}
              onClick={() => setFilter('unverified')}
              size="sm"
            >
              Unverified
            </Button>
            <Button
              variant={filter === 'verified' ? 'default' : 'outline'}
              onClick={() => setFilter('verified')}
              size="sm"
            >
              Verified
            </Button>
          </div>

          {/* 장면 그리드 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {scenes.map(scene => (
              <Card key={scene.id} className="overflow-hidden">
                {/* 이미지 */}
                <img
                  src={scene.annotated_frame_url}
                  alt={scene.failure_type}
                  className="w-full h-48 object-cover"
                />

                <CardContent className="p-4">
                  {/* 타입 & 신뢰도 */}
                  <div className="flex items-center justify-between mb-2">
                    <Badge className={getSeverityColor(scene.severity)}>
                      {scene.failure_type}
                    </Badge>
                    <span className="text-sm text-gray-500">
                      {(scene.confidence * 100).toFixed(1)}%
                    </span>
                  </div>

                  {/* 메타데이터 */}
                  <div className="text-xs text-gray-500 space-y-1">
                    {scene.layer_number && (
                      <div>Layer: {scene.layer_number}</div>
                    )}
                    {scene.print_progress && (
                      <div>Progress: {scene.print_progress.toFixed(1)}%</div>
                    )}
                    <div>{new Date(scene.frame_timestamp).toLocaleString()}</div>
                  </div>

                  {/* 검증 버튼 */}
                  {!scene.is_verified && (
                    <div className="flex gap-2 mt-4">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        onClick={() => handleVerify(scene.id, true)}
                      >
                        <Check className="w-4 h-4 mr-1" />
                        Correct
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        onClick={() => handleVerify(scene.id, false)}
                      >
                        <X className="w-4 h-4 mr-1" />
                        Wrong
                      </Button>
                    </div>
                  )}

                  {/* 검증됨 표시 */}
                  {scene.is_verified && (
                    <Badge variant="secondary" className="mt-2">
                      ✓ Verified
                    </Badge>
                  )}

                  {/* 원본/비디오 보기 */}
                  <div className="flex gap-2 mt-2">
                    <a
                      href={scene.original_frame_url}
                      target="_blank"
                      className="text-blue-500 text-sm"
                    >
                      Original
                    </a>
                    {scene.before_frames_url && (
                      <a
                        href={scene.before_frames_url}
                        target="_blank"
                        className="text-blue-500 text-sm"
                      >
                        Video
                      </a>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

function getSeverityColor(severity: string) {
  switch (severity) {
    case 'critical': return 'bg-red-500';
    case 'high': return 'bg-orange-500';
    case 'medium': return 'bg-yellow-500';
    default: return 'bg-gray-500';
  }
}
```

#### 4.2 실패 장면 API

**파일**: `main.py` (추가)

```python
"""
실패 장면 관리 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import zipfile
import io

router = APIRouter(prefix="/v1/failure-scenes", tags=["Failure Scenes"])

class VerifySceneRequest(BaseModel):
    is_correct: bool
    is_false_positive: bool
    corrected_type: Optional[str] = None

@router.get("/")
async def get_failure_scenes(
    user_id: str,
    device_uuid: Optional[str] = None,
    failure_type: Optional[str] = None,
    unverified_only: bool = False,
    verified_only: bool = False,
    limit: int = 100
):
    """실패 장면 목록 조회"""
    from supabase_db import get_failure_scenes

    scenes = await get_failure_scenes(
        user_id=user_id,
        device_uuid=device_uuid,
        failure_type=failure_type,
        verified_only=verified_only,
        limit=limit
    )

    if unverified_only:
        scenes = [s for s in scenes if not s['is_verified']]

    return {"scenes": scenes, "total": len(scenes)}

@router.post("/{scene_id}/verify")
async def verify_scene(scene_id: str, request: VerifySceneRequest):
    """
    실패 장면 검증
    - 사람이 확인하여 정확성 표시
    """
    from supabase_client import get_supabase_client

    supabase = get_supabase_client()

    update_data = {
        'is_verified': True,
        'is_false_positive': request.is_false_positive,
        'verified_at': 'NOW()',
        'updated_at': 'NOW()'
    }

    if request.corrected_type:
        update_data['corrected_type'] = request.corrected_type

    response = supabase.table('failure_scenes').update(update_data).eq('id', scene_id).execute()

    return {"status": "ok", "scene_id": scene_id}

@router.post("/export-dataset")
async def export_dataset(
    user_id: str,
    verified_only: bool = True
):
    """
    검증된 실패 장면을 데이터셋으로 내보내기
    - YOLO 형식 (images/ + labels/)
    - 향후 커스텀 학습에 사용
    """
    from supabase_db import get_failure_scenes
    import requests

    # 검증된 장면만 가져오기
    scenes = await get_failure_scenes(
        user_id=user_id,
        verified_only=verified_only,
        limit=1000
    )

    # ZIP 파일 생성
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # dataset.yaml 생성
        yaml_content = """
path: ./dataset
train: images/train
val: images/val
names:
  0: spaghetti
  1: warping
  2: layer_separation
  3: clogging
  4: support_failure
  5: first_layer_fail
"""
        zip_file.writestr('dataset.yaml', yaml_content)

        # 이미지 다운로드 및 추가
        for i, scene in enumerate(scenes):
            # 원본 이미지 다운로드
            img_response = requests.get(scene['original_frame_url'])
            img_data = img_response.content

            split = 'train' if i % 10 < 8 else 'val'  # 80% train, 20% val

            zip_file.writestr(
                f"images/{split}/{scene['id']}.jpg",
                img_data
            )

            # TODO: 바운딩 박스가 있으면 라벨 파일 생성
            # labels/{split}/{scene_id}.txt

    zip_buffer.seek(0)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        zip_buffer,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename=failure_dataset.zip'}
    )

@router.get("/stats")
async def get_failure_stats(user_id: str, time_range: str = "7d"):
    """
    실패 장면 통계
    - 타입별 빈도
    - 검증 상태
    """
    from supabase_client import get_supabase_client

    supabase = get_supabase_client()

    # 타입별 카운트
    response = supabase.rpc('get_failure_type_counts', {'user_id_param': user_id}).execute()

    return {
        "total_scenes": response.data.get('total', 0),
        "verified": response.data.get('verified', 0),
        "type_distribution": response.data.get('by_type', {}),
        "severity_distribution": response.data.get('by_severity', {})
    }
```

**작업**:
- [ ] 실패 장면 대시보드 UI
- [ ] 검증 UI 구현
- [ ] 데이터셋 내보내기 API
- [ ] 통계 API

---

### Phase 5: 배포 및 테스트 (Week 4)

#### 5.1 requirements.txt 업데이트

```txt
fastapi==0.115.0
uvicorn[standard]==0.31.0
httpx==0.28.1
python-multipart==0.0.9
python-dotenv==1.0.1
pydantic==2.12.4

# AI & Vision
torch==2.1.0
torchvision==0.16.0
opencv-python==4.8.1.78
Pillow==10.1.0
numpy==1.24.3

# Spaghetti Detective (사전학습 모델) ⭐
# git+https://github.com/TheSpaghettiDetective/ml_api.git

# Database & Storage
supabase==2.24.0
websockets==15.0.1
paho-mqtt==1.6.1

# Utils
requests==2.31.0
python-jose[cryptography]==3.3.0
```

#### 5.2 Docker 배포

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

# CUDA 지원 (GPU 사용 시)
# FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Spaghetti Detective 모델 다운로드
RUN python -c "from setup_model import download_spaghetti_detective_model; download_spaghetti_detective_model()"

# 소스 코드
COPY *.py /app/

EXPOSE 7000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
```

**작업**:
- [ ] Docker 이미지 빌드
- [ ] GPU 지원 설정
- [ ] 테스트 및 벤치마크
- [ ] 프로덕션 배포

---

## 타임라인 요약 (4주로 단축!)

| Week | Phase | 주요 작업 | 산출물 |
|------|-------|----------|--------|
| 1 | Phase 1-2 | 모델 통합 + 실패 장면 수집 | AI 추론 서비스, DB 스키마 |
| 2 | Phase 3 | API 통합 | 완전한 백엔드 API |
| 3 | Phase 4 | 프론트엔드 | 대시보드 UI |
| 4 | Phase 5 | 배포 & 테스트 | 프로덕션 시스템 |

**총 예상 기간**: 4주 (약 1개월) ⚡

---

## 🎯 v2.0 핵심 개선사항

### 1. **즉시 사용 가능** ✅
- ❌ 학습 불필요
- ✅ Spaghetti Detective 사전학습 모델 사용
- ⚡ 개발 기간 12주 → 4주

### 2. **실패 장면 자동 수집** ⭐
- 감지된 불량 프레임 자동 저장
- 전후 컨텍스트 (비디오 클립)
- 출력 상태 메타데이터 (온도, 속도, 레이어 등)

### 3. **데이터셋 자동 구축** 📊
- 실전 데이터 축적
- 사람 검증 UI
- YOLO 형식 내보내기
- 향후 커스텀 학습 가능

### 4. **비용 절감** 💰
- 라벨링 작업 불필요
- GPU 서버 학습 비용 없음
- 즉시 배포 가능

---

## 체크리스트

### 개발 환경
- [ ] Python 3.11 설치
- [ ] PyTorch 설치
- [ ] OpenCV 설치
- [ ] Spaghetti Detective 모델 다운로드

### 인프라
- [ ] Supabase 프로젝트 생성
- [ ] Storage 버킷 생성 (failure_frames, failure_videos)
- [ ] DB 테이블 생성 (failure_scenes)

### 백엔드
- [ ] AI 추론 서비스 구현
- [ ] 실패 장면 수집기 구현
- [ ] API 엔드포인트 구현
- [ ] MQTT 알림 통합

### 프론트엔드
- [ ] 실패 장면 대시보드
- [ ] 검증 UI
- [ ] 데이터셋 내보내기

### 배포
- [ ] Docker 이미지 빌드
- [ ] 테스트
- [ ] 프로덕션 배포

---

**문서 작성일**: 2025-01-26
**버전**: 2.0 (Spaghetti Detective + Auto-Collection)
**작성자**: Claude AI Assistant
