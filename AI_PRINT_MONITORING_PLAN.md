# 3D 프린터 출력 불량 감지 AI 시스템 개발 계획

## 📋 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [기술 스택](#기술-스택)
4. [개발 단계별 계획](#개발-단계별-계획)
5. [데이터 수집 및 학습](#데이터-수집-및-학습)
6. [API 설계](#api-설계)
7. [프론트엔드 통합](#프론트엔드-통합)
8. [배포 및 운영](#배포-및-운영)

---

## 프로젝트 개요

### 목표
WebRTC 카메라 스트리밍을 활용하여 3D 프린터 출력 과정을 실시간 모니터링하고, AI 기반으로 다음 불량을 감지:
- **스파게티화 (Spaghetti)**: 필라멘트가 엉켜서 출력되는 현상
- **레이어 분리 (Layer Separation)**: 레이어 간 접착 불량
- **와핑 (Warping)**: 출력물 모서리가 들뜨는 현상
- **노즐 막힘 (Clogging)**: 필라멘트 압출 불량
- **서포트 붕괴 (Support Failure)**: 서포트 구조 붕괴
- **첫 레이어 실패 (First Layer Failure)**: 베드 접착 실패

### 핵심 기능
1. **실시간 모니터링**: WebRTC 스트림에서 프레임 추출 및 분석
2. **AI 불량 감지**: YOLO 또는 Foundation Model 기반 실시간 추론
3. **예측 정보 생성**: 불량 타입, 신뢰도, 위치, 시간 등
4. **MQTT 알림**: 불량 감지 시 실시간 알림
5. **이력 관리**: DB에 감지 이력 저장 및 대시보드 제공

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
│  │     AI Inference Engine                │                   │
│  │  ┌──────────┐  ┌──────────────────┐  │                   │
│  │  │ YOLOv8   │  │ SAM2 / Florence2 │  │                   │
│  │  │ Detection│  │ Segmentation     │  │                   │
│  │  └──────────┘  └──────────────────┘  │                   │
│  └────────┬──────────────────────────────┘                   │
│           │                                                   │
└───────────┼───────────────────────────────────────────────────┘
            │
            ▼
   ┌────────────────────┐
   │   Supabase DB      │
   │  ┌──────────────┐  │
   │  │ detections   │  │  - 감지 이력
   │  │ print_jobs   │  │  - 출력 작업
   │  │ cameras      │  │  - 카메라 정보
   │  │ alerts       │  │  - 알림 이력
   │  └──────────────┘  │
   └────────────────────┘
```

---

## 기술 스택

### Backend (Python)
- **FastAPI**: REST API 서버
- **OpenCV**: 비디오 프레임 처리
- **PyTorch**: 딥러닝 추론
- **Ultralytics YOLOv8**: 객체 감지
- **Transformers (Hugging Face)**: Foundation Models
  - SAM2 (Segment Anything Model 2)
  - Florence-2 (Vision-Language Model)
  - CLIP (이미지-텍스트 매칭)
- **paho-mqtt**: MQTT 클라이언트
- **aiortc**: WebRTC 처리 (선택사항)

### Frontend (React/TypeScript)
- **WebRTC API**: 카메라 스트리밍
- **MQTT.js**: 실시간 알림 수신
- **Canvas API**: 감지 결과 오버레이

### Database & Storage
- **Supabase PostgreSQL**: 메타데이터 저장
- **Supabase Storage**: 이미지/영상 저장
- **Redis** (선택): 실시간 상태 캐싱

### AI Models
| 모델 | 용도 | 크기 | 추론 속도 |
|------|------|------|-----------|
| YOLOv8n | 경량 감지 (스파게티, 와핑) | ~6MB | ~200 FPS |
| YOLOv8s | 중간 정확도 | ~22MB | ~120 FPS |
| YOLOv8m | 높은 정확도 | ~50MB | ~45 FPS |
| SAM2-tiny | 세그멘테이션 | ~40MB | ~30 FPS |
| Florence-2 | 비전-언어 | ~230MB | ~10 FPS |

**권장**: 실시간 처리를 위해 **YOLOv8n + SAM2-tiny** 조합

---

## 개발 단계별 계획

### Phase 1: 기반 인프라 구축 (Week 1-2)

#### 1.1 WebRTC 프레임 추출 API
**파일**: `webrtc_capture.py`

```python
"""
WebRTC 스트림에서 프레임을 추출하여 AI 분석용으로 제공
"""
import cv2
import numpy as np
from typing import Optional, Tuple
import asyncio
import aiohttp

class WebRTCFrameCapture:
    def __init__(self, stream_url: str):
        """
        Args:
            stream_url: WebRTC 스트림 URL
        """
        self.stream_url = stream_url
        self.cap = None
        self.last_frame = None
        self.frame_interval = 1.0  # 1초마다 1프레임 추출 (기본값)

    async def start_capture(self):
        """스트림 캡처 시작"""
        # WebRTC -> HTTP 프록시 사용 또는 직접 연결
        # go2rtc, mediamtx 등의 프록시 활용
        pass

    async def get_frame(self) -> Optional[np.ndarray]:
        """현재 프레임 반환"""
        pass

    def stop_capture(self):
        """캡처 중지"""
        pass
```

**작업**:
- [ ] WebRTC 스트림 → OpenCV 변환 로직 구현
- [ ] 프레임 추출 주기 설정 (FPS 조절)
- [ ] 에러 핸들링 및 재연결 로직
- [ ] 메모리 관리 (프레임 버퍼 크기 제한)

#### 1.2 데이터베이스 스키마 설계

**Supabase 테이블 생성**:

```sql
-- 감지 이력 테이블
CREATE TABLE print_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    device_uuid UUID NOT NULL,
    print_job_id UUID REFERENCES print_jobs(id),

    -- 감지 정보
    detection_type VARCHAR(50) NOT NULL, -- 'spaghetti', 'warping', 'layer_separation', etc.
    confidence FLOAT NOT NULL,           -- 0.0 ~ 1.0
    severity VARCHAR(20) NOT NULL,       -- 'low', 'medium', 'high', 'critical'

    -- 위치 정보 (bounding box)
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_width INTEGER,
    bbox_height INTEGER,

    -- 이미지 저장
    frame_image_url TEXT,                -- Supabase Storage URL
    annotated_image_url TEXT,            -- 바운딩 박스 표시된 이미지

    -- 메타데이터
    layer_number INTEGER,                -- 현재 레이어
    print_progress FLOAT,                -- 출력 진행률 (%)
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- 인덱스
    CONSTRAINT detections_device_time_idx
        FOREIGN KEY (device_uuid, timestamp)
);

-- 알림 설정 테이블
CREATE TABLE alert_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    device_uuid UUID,

    -- 알림 조건
    enabled BOOLEAN DEFAULT TRUE,
    detection_types TEXT[],              -- ['spaghetti', 'warping', ...]
    min_confidence FLOAT DEFAULT 0.7,
    severity_threshold VARCHAR(20) DEFAULT 'medium',

    -- 알림 채널
    mqtt_enabled BOOLEAN DEFAULT TRUE,
    email_enabled BOOLEAN DEFAULT FALSE,
    sms_enabled BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 출력 작업 테이블 (기존에 없다면)
CREATE TABLE print_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    device_uuid UUID NOT NULL,

    gcode_file_id UUID,
    model_name VARCHAR(255),

    status VARCHAR(50) DEFAULT 'printing', -- 'printing', 'paused', 'completed', 'failed'
    progress FLOAT DEFAULT 0.0,
    current_layer INTEGER DEFAULT 0,
    total_layers INTEGER,

    -- AI 모니터링 상태
    ai_monitoring_enabled BOOLEAN DEFAULT TRUE,
    detection_count INTEGER DEFAULT 0,

    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_detections_user_time ON print_detections(user_id, timestamp DESC);
CREATE INDEX idx_detections_device_time ON print_detections(device_uuid, timestamp DESC);
CREATE INDEX idx_detections_job ON print_detections(print_job_id);
CREATE INDEX idx_print_jobs_user ON print_jobs(user_id, started_at DESC);
```

**작업**:
- [ ] Supabase SQL 에디터에서 테이블 생성
- [ ] RLS (Row Level Security) 정책 설정
- [ ] API 권한 확인

---

### Phase 2: AI 모델 선택 및 학습 (Week 3-4)

#### 2.1 모델 선택 전략

**Option 1: YOLOv8 Custom Training** (권장)
- **장점**: 빠른 추론 속도, 커스텀 데이터 학습 가능
- **단점**: 라벨링 데이터 필요

**Option 2: Foundation Model (Florence-2, SAM2)**
- **장점**: Zero-shot 또는 Few-shot 학습, 라벨링 최소화
- **단점**: 느린 추론 속도, GPU 필수

**Option 3: Hybrid Approach** (최적)
- YOLOv8으로 1차 감지 (빠른 스크리닝)
- Florence-2로 2차 검증 (정확도 향상)

#### 2.2 데이터 수집

**필요 데이터**:
- 정상 출력 영상: 500+ 프레임
- 스파게티화: 200+ 프레임
- 와핑: 150+ 프레임
- 레이어 분리: 100+ 프레임
- 노즐 막힘: 100+ 프레임
- 서포트 붕괴: 100+ 프레임

**데이터 소스**:
1. **자체 수집**: 실제 프린터에서 의도적 불량 유발
2. **공개 데이터셋**:
   - [Spaghetti Detective Dataset](https://github.com/TheSpaghettiDetective/ml_api)
   - [3D Print Monitor Dataset (Kaggle)](https://www.kaggle.com/datasets)
3. **합성 데이터**: Blender로 시뮬레이션

#### 2.3 YOLOv8 학습 파이프라인

**파일**: `train_yolo_detector.py`

```python
"""
YOLOv8 커스텀 학습 스크립트
"""
from ultralytics import YOLO
import yaml

# 데이터셋 구조
# dataset/
#   ├── images/
#   │   ├── train/
#   │   └── val/
#   └── labels/
#       ├── train/
#       └── val/

# dataset.yaml 생성
dataset_config = {
    'path': './dataset',
    'train': 'images/train',
    'val': 'images/val',
    'names': {
        0: 'spaghetti',
        1: 'warping',
        2: 'layer_separation',
        3: 'clogging',
        4: 'support_failure',
        5: 'first_layer_fail'
    }
}

with open('dataset.yaml', 'w') as f:
    yaml.dump(dataset_config, f)

# 모델 학습
model = YOLO('yolov8n.pt')  # nano 모델 (가장 빠름)

results = model.train(
    data='dataset.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    device=0,  # GPU 0
    project='print_detector',
    name='yolov8n_v1',

    # Augmentation
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    degrees=10,
    translate=0.1,
    scale=0.5,
    shear=0.0,
    perspective=0.0,
    flipud=0.5,
    fliplr=0.5,
    mosaic=1.0,
    mixup=0.0,
)

# 모델 검증
metrics = model.val()
print(f"mAP50: {metrics.box.map50}")
print(f"mAP50-95: {metrics.box.map}")

# 모델 내보내기
model.export(format='onnx')  # ONNX 포맷으로 변환 (더 빠른 추론)
```

**작업**:
- [ ] 데이터 수집 및 라벨링 (Roboflow, LabelImg 사용)
- [ ] 학습 데이터 증강 (Augmentation)
- [ ] 모델 학습 및 검증
- [ ] 하이퍼파라미터 튜닝
- [ ] 최종 모델 선정 (정확도 vs 속도)

#### 2.4 Foundation Model 통합 (선택)

**Florence-2 예제**:
```python
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image

processor = AutoProcessor.from_pretrained("microsoft/Florence-2-base")
model = AutoModelForCausalLM.from_pretrained("microsoft/Florence-2-base")

def detect_with_florence(image_path: str, prompt: str = "<OD>"):
    """
    Florence-2로 객체 감지

    Args:
        image_path: 이미지 경로
        prompt: "<OD>" (Object Detection), "<CAPTION>" (Captioning)
    """
    image = Image.open(image_path)

    inputs = processor(text=prompt, images=image, return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=1024)

    result = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    return result
```

---

### Phase 3: AI 추론 서비스 개발 (Week 5-6)

#### 3.1 AI 추론 모듈

**파일**: `ai_inference.py`

```python
"""
실시간 AI 추론 서비스
"""
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

# 모델 로드 (서버 시작 시 한 번만)
YOLO_MODEL = None
YOLO_MODEL_PATH = "./models/yolov8n_print_detector.pt"
CONFIDENCE_THRESHOLD = 0.5
IOU_THRESHOLD = 0.45

# 불량 타입별 심각도 매핑
SEVERITY_MAP = {
    'spaghetti': 'critical',
    'warping': 'high',
    'layer_separation': 'high',
    'clogging': 'medium',
    'support_failure': 'medium',
    'first_layer_fail': 'critical'
}

class AIInferenceService:
    """AI 추론 서비스"""

    def __init__(self, model_path: str = YOLO_MODEL_PATH):
        """
        Args:
            model_path: YOLO 모델 경로
        """
        self.model = self._load_model(model_path)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"[AI] Model loaded on {self.device}")

    def _load_model(self, model_path: str) -> YOLO:
        """모델 로드"""
        if not Path(model_path).exists():
            logger.error(f"[AI] Model not found: {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        model = YOLO(model_path)
        return model

    async def predict(
        self,
        frame: np.ndarray,
        conf_threshold: float = CONFIDENCE_THRESHOLD,
        iou_threshold: float = IOU_THRESHOLD
    ) -> List[Dict]:
        """
        프레임에서 불량 감지

        Args:
            frame: OpenCV 이미지 (BGR)
            conf_threshold: 신뢰도 임계값
            iou_threshold: IoU 임계값

        Returns:
            감지 결과 리스트
            [
                {
                    'detection_type': 'spaghetti',
                    'confidence': 0.95,
                    'bbox': [x, y, w, h],
                    'severity': 'critical',
                    'timestamp': '2025-01-26T10:30:00Z'
                },
                ...
            ]
        """
        if frame is None or frame.size == 0:
            logger.warning("[AI] Empty frame received")
            return []

        try:
            # YOLO 추론
            results = self.model.predict(
                frame,
                conf=conf_threshold,
                iou=iou_threshold,
                verbose=False,
                device=self.device
            )

            detections = []

            for result in results:
                boxes = result.boxes

                for i, box in enumerate(boxes):
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    xyxy = box.xyxy[0].cpu().numpy()

                    # 클래스 이름 가져오기
                    class_name = self.model.names[cls_id]

                    # 바운딩 박스 [x, y, w, h] 형식으로 변환
                    x1, y1, x2, y2 = xyxy
                    bbox = [
                        int(x1),
                        int(y1),
                        int(x2 - x1),
                        int(y2 - y1)
                    ]

                    detection = {
                        'detection_type': class_name,
                        'confidence': round(conf, 4),
                        'bbox': bbox,
                        'severity': SEVERITY_MAP.get(class_name, 'low'),
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    }

                    detections.append(detection)

                    logger.info(
                        f"[AI] Detected {class_name} "
                        f"(conf={conf:.2f}, severity={detection['severity']})"
                    )

            return detections

        except Exception as e:
            logger.error(f"[AI] Prediction failed: {str(e)}")
            return []

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict]
    ) -> np.ndarray:
        """
        프레임에 감지 결과 그리기

        Args:
            frame: 원본 프레임
            detections: 감지 결과 리스트

        Returns:
            어노테이션이 그려진 프레임
        """
        annotated = frame.copy()

        # 심각도별 색상
        color_map = {
            'critical': (0, 0, 255),    # 빨강
            'high': (0, 165, 255),      # 주황
            'medium': (0, 255, 255),    # 노랑
            'low': (0, 255, 0)          # 초록
        }

        for det in detections:
            x, y, w, h = det['bbox']
            severity = det['severity']
            conf = det['confidence']
            det_type = det['detection_type']

            color = color_map.get(severity, (255, 255, 255))

            # 바운딩 박스
            cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)

            # 레이블
            label = f"{det_type}: {conf:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(
                annotated,
                (x, y - label_size[1] - 10),
                (x + label_size[0], y),
                color,
                -1
            )
            cv2.putText(
                annotated,
                label,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1
            )

        return annotated

# 싱글톤 인스턴스
_ai_service: Optional[AIInferenceService] = None

def get_ai_service() -> AIInferenceService:
    """AI 서비스 싱글톤 인스턴스 반환"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIInferenceService()
    return _ai_service
```

**작업**:
- [ ] YOLO 모델 로드 및 추론 구현
- [ ] 바운딩 박스 그리기 기능
- [ ] 성능 최적화 (배치 처리, GPU 활용)
- [ ] 에러 핸들링

#### 3.2 모니터링 API 엔드포인트

**파일**: `main.py` 추가

```python
"""
AI 모니터링 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import cv2
import numpy as np
from datetime import datetime
import uuid

from ai_inference import get_ai_service
from supabase_db import save_detection, get_print_job
from supabase_storage import upload_frame_image
from mqtt_notification import send_detection_alert

router = APIRouter(prefix="/v1/ai-monitoring", tags=["AI Monitoring"])

class StartMonitoringRequest(BaseModel):
    device_uuid: str
    print_job_id: Optional[str] = None
    user_id: str
    confidence_threshold: float = 0.5
    frame_interval: int = 5  # 5초마다 분석

class DetectionResponse(BaseModel):
    detection_id: str
    detection_type: str
    confidence: float
    severity: str
    bbox: List[int]
    frame_url: Optional[str]
    timestamp: str

@router.post("/start")
async def start_monitoring(request: StartMonitoringRequest):
    """
    AI 모니터링 시작

    - WebRTC 스트림에서 프레임 추출 시작
    - 백그라운드에서 주기적으로 AI 분석
    """
    # TODO: WebRTC 캡처 시작
    # TODO: 백그라운드 작업 등록

    return {
        "status": "ok",
        "message": f"Monitoring started for device {request.device_uuid}",
        "monitoring_id": str(uuid.uuid4())
    }

@router.post("/stop")
async def stop_monitoring(device_uuid: str):
    """AI 모니터링 중지"""
    # TODO: 백그라운드 작업 취소

    return {
        "status": "ok",
        "message": f"Monitoring stopped for device {device_uuid}"
    }

@router.post("/analyze-frame", response_model=List[DetectionResponse])
async def analyze_frame(
    device_uuid: str,
    user_id: str,
    file: UploadFile = File(...),
    print_job_id: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    단일 프레임 분석

    - 이미지 업로드하여 즉시 AI 분석
    - 감지 결과 DB 저장 및 MQTT 알림
    """
    try:
        # 이미지 읽기
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        # AI 추론
        ai_service = get_ai_service()
        detections = await ai_service.predict(frame, conf_threshold=0.5)

        if not detections:
            return []

        # 어노테이션된 이미지 생성
        annotated_frame = ai_service.draw_detections(frame, detections)

        # DB 저장 및 알림 (백그라운드)
        for det in detections:
            detection_id = str(uuid.uuid4())
            det['detection_id'] = detection_id

            # 이미지 업로드
            frame_url = await upload_frame_image(
                user_id,
                device_uuid,
                detection_id,
                annotated_frame
            )
            det['frame_url'] = frame_url

            # DB 저장
            background_tasks.add_task(
                save_detection,
                user_id=user_id,
                device_uuid=device_uuid,
                print_job_id=print_job_id,
                detection=det
            )

            # MQTT 알림
            background_tasks.add_task(
                send_detection_alert,
                user_id=user_id,
                device_uuid=device_uuid,
                detection=det
            )

        return [DetectionResponse(**det) for det in detections]

    except Exception as e:
        logger.error(f"[AI] Frame analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detections/history")
async def get_detection_history(
    user_id: str,
    device_uuid: Optional[str] = None,
    print_job_id: Optional[str] = None,
    limit: int = 50
):
    """감지 이력 조회"""
    # TODO: DB에서 감지 이력 조회
    pass

@router.get("/detections/stats")
async def get_detection_stats(
    user_id: str,
    device_uuid: Optional[str] = None,
    time_range: str = "24h"  # 1h, 24h, 7d, 30d
):
    """
    감지 통계

    - 불량 타입별 발생 빈도
    - 시간대별 추이
    - 평균 신뢰도
    """
    # TODO: 통계 쿼리
    pass
```

**작업**:
- [ ] 모니터링 시작/중지 API 구현
- [ ] 프레임 분석 API 구현
- [ ] 이력 조회 API 구현
- [ ] 통계 API 구현

---

### Phase 4: 실시간 모니터링 워커 (Week 7)

#### 4.1 백그라운드 워커

**파일**: `monitoring_worker.py`

```python
"""
백그라운드 모니터링 워커
WebRTC 스트림에서 주기적으로 프레임 추출하여 AI 분석
"""
import asyncio
from typing import Dict, Optional
import logging
from datetime import datetime

from webrtc_capture import WebRTCFrameCapture
from ai_inference import get_ai_service
from supabase_db import save_detection, update_print_job_status
from supabase_storage import upload_frame_image
from mqtt_notification import send_detection_alert

logger = logging.getLogger("uvicorn.error")

class MonitoringWorker:
    """모니터링 워커"""

    def __init__(
        self,
        device_uuid: str,
        user_id: str,
        stream_url: str,
        print_job_id: Optional[str] = None,
        frame_interval: int = 5,  # 5초마다 분석
        confidence_threshold: float = 0.5
    ):
        self.device_uuid = device_uuid
        self.user_id = user_id
        self.stream_url = stream_url
        self.print_job_id = print_job_id
        self.frame_interval = frame_interval
        self.confidence_threshold = confidence_threshold

        self.capture = WebRTCFrameCapture(stream_url)
        self.ai_service = get_ai_service()
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """모니터링 시작"""
        if self.is_running:
            logger.warning(f"[Worker] Already running for {self.device_uuid}")
            return

        self.is_running = True
        await self.capture.start_capture()

        # 백그라운드 태스크 시작
        self.task = asyncio.create_task(self._monitoring_loop())

        logger.info(f"[Worker] Started for device {self.device_uuid}")

    async def stop(self):
        """모니터링 중지"""
        self.is_running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        self.capture.stop_capture()

        logger.info(f"[Worker] Stopped for device {self.device_uuid}")

    async def _monitoring_loop(self):
        """메인 모니터링 루프"""
        consecutive_failures = 0
        max_failures = 5

        while self.is_running:
            try:
                # 프레임 가져오기
                frame = await self.capture.get_frame()

                if frame is None:
                    consecutive_failures += 1
                    logger.warning(
                        f"[Worker] No frame from {self.device_uuid} "
                        f"({consecutive_failures}/{max_failures})"
                    )

                    if consecutive_failures >= max_failures:
                        logger.error(
                            f"[Worker] Too many failures, stopping {self.device_uuid}"
                        )
                        await self.stop()
                        break

                    await asyncio.sleep(self.frame_interval)
                    continue

                # 성공 시 카운터 리셋
                consecutive_failures = 0

                # AI 분석
                detections = await self.ai_service.predict(
                    frame,
                    conf_threshold=self.confidence_threshold
                )

                if detections:
                    logger.info(
                        f"[Worker] {len(detections)} detection(s) "
                        f"for {self.device_uuid}"
                    )

                    # 어노테이션된 이미지 생성
                    annotated_frame = self.ai_service.draw_detections(
                        frame,
                        detections
                    )

                    # 각 감지 결과 처리
                    for det in detections:
                        await self._process_detection(det, annotated_frame)

                # 대기
                await asyncio.sleep(self.frame_interval)

            except asyncio.CancelledError:
                logger.info(f"[Worker] Task cancelled for {self.device_uuid}")
                break

            except Exception as e:
                logger.error(f"[Worker] Error in monitoring loop: {str(e)}")
                consecutive_failures += 1

                if consecutive_failures >= max_failures:
                    logger.error(f"[Worker] Too many errors, stopping")
                    await self.stop()
                    break

                await asyncio.sleep(self.frame_interval)

    async def _process_detection(self, detection: Dict, frame):
        """감지 결과 처리"""
        import uuid

        detection_id = str(uuid.uuid4())
        detection['detection_id'] = detection_id

        try:
            # 이미지 Supabase Storage 업로드
            frame_url = await upload_frame_image(
                self.user_id,
                self.device_uuid,
                detection_id,
                frame
            )
            detection['frame_url'] = frame_url

            # DB 저장
            await save_detection(
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                print_job_id=self.print_job_id,
                detection=detection
            )

            # MQTT 알림
            await send_detection_alert(
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                detection=detection
            )

            # Critical 감지 시 출력 작업 상태 업데이트
            if detection['severity'] == 'critical' and self.print_job_id:
                await update_print_job_status(
                    self.print_job_id,
                    status='paused',
                    reason=f"Critical detection: {detection['detection_type']}"
                )

        except Exception as e:
            logger.error(f"[Worker] Failed to process detection: {str(e)}")

# 워커 관리자
class MonitoringManager:
    """모니터링 워커 관리자 (싱글톤)"""

    def __init__(self):
        self.workers: Dict[str, MonitoringWorker] = {}

    async def start_monitoring(
        self,
        device_uuid: str,
        user_id: str,
        stream_url: str,
        **kwargs
    ):
        """모니터링 시작"""
        if device_uuid in self.workers:
            logger.warning(f"[Manager] Already monitoring {device_uuid}")
            return

        worker = MonitoringWorker(
            device_uuid=device_uuid,
            user_id=user_id,
            stream_url=stream_url,
            **kwargs
        )

        await worker.start()
        self.workers[device_uuid] = worker

        logger.info(f"[Manager] Monitoring started for {device_uuid}")

    async def stop_monitoring(self, device_uuid: str):
        """모니터링 중지"""
        if device_uuid not in self.workers:
            logger.warning(f"[Manager] Not monitoring {device_uuid}")
            return

        worker = self.workers[device_uuid]
        await worker.stop()
        del self.workers[device_uuid]

        logger.info(f"[Manager] Monitoring stopped for {device_uuid}")

    async def stop_all(self):
        """모든 모니터링 중지"""
        for device_uuid in list(self.workers.keys()):
            await self.stop_monitoring(device_uuid)

# 싱글톤 인스턴스
_monitoring_manager: Optional[MonitoringManager] = None

def get_monitoring_manager() -> MonitoringManager:
    """모니터링 매니저 싱글톤"""
    global _monitoring_manager
    if _monitoring_manager is None:
        _monitoring_manager = MonitoringManager()
    return _monitoring_manager
```

**작업**:
- [ ] 백그라운드 워커 구현
- [ ] 워커 관리자 구현
- [ ] 에러 핸들링 및 재연결 로직
- [ ] 성능 모니터링 (CPU, GPU, 메모리 사용량)

---

### Phase 5: 프론트엔드 통합 (Week 8)

#### 5.1 AI 모니터링 대시보드

**파일**: `packages/web/src/components/AIMonitoringPanel.tsx`

```typescript
/**
 * AI 모니터링 패널
 * - 실시간 감지 결과 표시
 * - MQTT로 알림 수신
 * - 감지 이력 차트
 */
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import { onDetectionMessage } from '@shared/services/mqttService';

interface Detection {
  detection_id: string;
  detection_type: string;
  confidence: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  bbox: [number, number, number, number];
  frame_url?: string;
  timestamp: string;
}

export const AIMonitoringPanel = ({ deviceUuid }: { deviceUuid: string }) => {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [isMonitoring, setIsMonitoring] = useState(false);

  // MQTT 구독
  useEffect(() => {
    if (!deviceUuid) return;

    const unsubscribe = onDetectionMessage(deviceUuid, (payload) => {
      const detection = payload as Detection;
      setDetections(prev => [detection, ...prev].slice(0, 10)); // 최근 10개만
    });

    return () => unsubscribe();
  }, [deviceUuid]);

  // 모니터링 시작/중지
  const toggleMonitoring = async () => {
    if (isMonitoring) {
      // 중지 API 호출
      await fetch(`/v1/ai-monitoring/stop?device_uuid=${deviceUuid}`, {
        method: 'POST'
      });
      setIsMonitoring(false);
    } else {
      // 시작 API 호출
      await fetch('/v1/ai-monitoring/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_uuid: deviceUuid,
          user_id: 'user-id', // 실제 user_id
          confidence_threshold: 0.5,
          frame_interval: 5
        })
      });
      setIsMonitoring(true);
    }
  };

  // 심각도별 색상
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'medium': return 'bg-yellow-500';
      case 'low': return 'bg-green-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>AI Monitoring</span>
          <button onClick={toggleMonitoring}>
            {isMonitoring ? 'Stop' : 'Start'}
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* 실시간 감지 목록 */}
        <div className="space-y-2">
          {detections.map(det => (
            <div key={det.detection_id} className="flex items-center gap-2 p-2 border rounded">
              <Badge className={getSeverityColor(det.severity)}>
                {det.severity}
              </Badge>
              <span className="font-medium">{det.detection_type}</span>
              <span className="text-sm text-gray-500">
                {(det.confidence * 100).toFixed(1)}%
              </span>
              {det.frame_url && (
                <a href={det.frame_url} target="_blank" className="text-blue-500">
                  View
                </a>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
```

**작업**:
- [ ] AI 모니터링 패널 컴포넌트
- [ ] MQTT 감지 알림 수신
- [ ] 감지 이력 차트 (Recharts)
- [ ] 이미지 오버레이 (Canvas)

#### 5.2 MQTT 토픽 추가

**파일**: `mqtt_notification.py` 수정

```python
# 새로운 토픽 추가
TOPIC_AI_DETECTION = "ai/detection/{device_uuid}"

def send_detection_alert(
    user_id: str,
    device_uuid: str,
    detection: Dict
) -> bool:
    """
    AI 감지 알림 전송

    Topic: ai/detection/{device_uuid}
    Payload:
        {
            "detection_id": "uuid",
            "detection_type": "spaghetti",
            "confidence": 0.95,
            "severity": "critical",
            "bbox": [x, y, w, h],
            "frame_url": "https://...",
            "timestamp": "2025-01-26T10:30:00Z"
        }
    """
    try:
        client = create_mqtt_client()
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()

        topic = TOPIC_AI_DETECTION.format(device_uuid=device_uuid)

        payload = {
            "detection_id": detection['detection_id'],
            "detection_type": detection['detection_type'],
            "confidence": detection['confidence'],
            "severity": detection['severity'],
            "bbox": detection['bbox'],
            "frame_url": detection.get('frame_url'),
            "timestamp": detection['timestamp']
        }

        message = json.dumps(payload)
        result = client.publish(topic, message, qos=1, retain=False)

        result.wait_for_publish(timeout=5)

        if result.is_published():
            logger.info(f"[MQTT] Detection alert sent: {device_uuid}")
            return True
        else:
            logger.error(f"[MQTT] Failed to send detection alert")
            return False

        client.loop_stop()
        client.disconnect()

        return True

    except Exception as e:
        logger.error(f"[MQTT] Error sending detection alert: {e}")
        return False
```

---

### Phase 6: 테스트 및 최적화 (Week 9-10)

#### 6.1 성능 테스트

**테스트 항목**:
- [ ] 모델 추론 속도 (FPS)
- [ ] 메모리 사용량
- [ ] GPU 활용률
- [ ] 동시 모니터링 가능 디바이스 수
- [ ] 네트워크 대역폭

**최적화 방법**:
1. **ONNX 변환**: PyTorch → ONNX (2-3배 빠름)
2. **TensorRT 최적화**: NVIDIA GPU 전용
3. **배치 처리**: 여러 프레임 한 번에 처리
4. **비동기 처리**: I/O 블로킹 제거

#### 6.2 정확도 평가

**평가 지표**:
- Precision (정밀도)
- Recall (재현율)
- F1 Score
- mAP (mean Average Precision)
- False Positive Rate

**테스트 데이터셋**:
- 실제 프린터 출력 영상 100건
- 정상/불량 비율 7:3

---

### Phase 7: 배포 및 운영 (Week 11-12)

#### 7.1 Docker 컨테이너화

**파일**: `Dockerfile.ai`

```dockerfile
FROM python:3.11-slim

# CUDA 지원 (GPU 사용 시)
# FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델 파일 복사
COPY models/ /app/models/

# 소스 코드 복사
COPY *.py /app/

# 포트 노출
EXPOSE 7000

# 서버 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
```

**docker-compose.yml 수정**:

```yaml
services:
  ai-server:
    build:
      context: .
      dockerfile: Dockerfile.ai
    ports:
      - "7000:7000"
    volumes:
      - ./models:/app/models:ro
      - ./output:/app/output
    environment:
      - CUDA_VISIBLE_DEVICES=0  # GPU 0 사용
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

#### 7.2 모니터링 및 로깅

**Prometheus 메트릭 추가**:

```python
from prometheus_client import Counter, Histogram, Gauge

# 메트릭 정의
detection_counter = Counter(
    'ai_detections_total',
    'Total number of detections',
    ['detection_type', 'severity']
)

inference_duration = Histogram(
    'ai_inference_duration_seconds',
    'AI inference duration'
)

active_monitors = Gauge(
    'ai_active_monitors',
    'Number of active monitoring workers'
)

# 사용 예시
@inference_duration.time()
async def predict(...):
    # ...
    for det in detections:
        detection_counter.labels(
            detection_type=det['detection_type'],
            severity=det['severity']
        ).inc()
```

#### 7.3 알림 및 대응

**자동 대응 시나리오**:

1. **Critical 감지 시**:
   - MQTT 즉시 알림
   - (선택) 프린터 일시정지
   - 관리자에게 SMS/Email 전송

2. **High 감지 반복 시** (5분 내 3회):
   - 경고 알림
   - 대시보드에 경고 표시

3. **Medium 감지**:
   - 로그 기록
   - 통계에만 반영

---

## 추가 고려사항

### 보안
- [ ] API 인증 (JWT)
- [ ] MQTT TLS 암호화
- [ ] 이미지 데이터 암호화

### 확장성
- [ ] 멀티 GPU 지원
- [ ] 로드 밸런싱
- [ ] Redis 캐싱

### 비용 최적화
- [ ] 모델 경량화 (Pruning, Quantization)
- [ ] 클라우드 vs 온프레미스 선택
- [ ] Spot Instance 활용

---

## 참고 자료

### AI 모델
- [Ultralytics YOLOv8 Docs](https://docs.ultralytics.com/)
- [Florence-2 Hugging Face](https://huggingface.co/microsoft/Florence-2-base)
- [SAM2 GitHub](https://github.com/facebookresearch/segment-anything-2)

### 3D 프린터 불량 감지
- [The Spaghetti Detective](https://www.thespaghettidetective.com/)
- [OctoPrint AI Plugin](https://plugins.octoprint.org/)

### 데이터셋
- [Kaggle 3D Print Dataset](https://www.kaggle.com/datasets)
- [Roboflow 3D Printing](https://universe.roboflow.com/)

---

## 타임라인 요약

| Week | Phase | 주요 작업 | 산출물 |
|------|-------|----------|--------|
| 1-2 | Phase 1 | 인프라 구축 | WebRTC 캡처, DB 스키마 |
| 3-4 | Phase 2 | AI 모델 학습 | YOLOv8 학습 모델 |
| 5-6 | Phase 3 | 추론 서비스 | AI API 엔드포인트 |
| 7 | Phase 4 | 워커 개발 | 백그라운드 모니터링 |
| 8 | Phase 5 | 프론트엔드 | 대시보드 UI |
| 9-10 | Phase 6 | 테스트 | 성능/정확도 보고서 |
| 11-12 | Phase 7 | 배포 | Docker, 모니터링 |

**총 예상 기간**: 12주 (약 3개월)

---

## 체크리스트

### 개발 환경
- [ ] Python 3.11 설치
- [ ] CUDA & cuDNN 설치 (GPU 사용 시)
- [ ] PyTorch 설치
- [ ] Ultralytics 설치
- [ ] OpenCV 설치

### 데이터
- [ ] 학습 데이터 수집 (최소 1000장)
- [ ] 데이터 라벨링 (Roboflow)
- [ ] 데이터셋 분할 (train/val/test)

### 모델
- [ ] YOLOv8 학습
- [ ] 모델 검증 (mAP > 0.7)
- [ ] 모델 최적화 (ONNX 변환)

### API
- [ ] 모니터링 API 구현
- [ ] WebRTC 통합
- [ ] MQTT 알림 구현
- [ ] DB 연동

### 프론트엔드
- [ ] AI 대시보드 구현
- [ ] 실시간 알림 UI
- [ ] 감지 이력 차트

### 배포
- [ ] Docker 이미지 빌드
- [ ] GPU 설정
- [ ] 모니터링 대시보드 (Grafana)
- [ ] 로그 수집 (ELK Stack)

---

**문서 작성일**: 2025-01-26
**최종 수정일**: 2025-01-26
**작성자**: Claude AI Assistant
