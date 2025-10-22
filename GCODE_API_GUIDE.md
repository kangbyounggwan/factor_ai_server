# G-code 변환 API 가이드

## 개요

STL 파일을 CuraEngine을 사용하여 G-code로 슬라이싱하는 API 구현 가이드입니다.

**현재 구현 방식**: 클라이언트가 프린터 정의 JSON을 직접 전송
- 간단한 사용법은 [CLIENT_API_GUIDE.md](./CLIENT_API_GUIDE.md) 참조
- STL 파일 업로드는 [STL_UPLOAD_API_GUIDE.md](./STL_UPLOAD_API_GUIDE.md) 참조

**확장 구현 (선택)**: DB에 프린터 프로파일 저장 (이 문서에서 설명)

---

## 구현된 파일

### 1. `cura_processor.py` - 핵심 슬라이싱 로직

**주요 함수:**
- `is_curaengine_available()` - CuraEngine 설치 확인
- `convert_stl_to_gcode()` - 기본 STL → G-code 변환
- `convert_stl_to_gcode_with_definition()` - 클라이언트 전송 프린터 정의 사용 ⭐
- `convert_stl_to_gcode_with_db_profile()` - DB 저장 프린터 프로파일 사용 (선택)
- `merge_settings()` - 기본 설정 + 사용자 설정 병합
- `parse_slicing_stats()` - 슬라이싱 통계 파싱

⭐ = 현재 구현에서 사용

---

## API 엔드포인트

### POST `/v1/process/generate-gcode`

STL 파일을 G-code로 변환합니다.

#### Request Body

**방법 1: 기본 프린터 사용 (서버 설정)**
```json
{
  "task_id": "abc123-def456-789",
  "cura_settings": {
    "layer_height": "0.2",
    "infill_sparse_density": "20",
    "support_enable": "true"
  }
}
```

**방법 2: 커스텀 프린터 정의 전송 (권장)**
```json
{
  "task_id": "abc123-def456-789",
  "printer_definition": {
    "version": 2,
    "name": "Creality Ender-3 Pro",
    "inherits": "creality_base",
    "metadata": {
      "visible": true,
      "platform": "creality_ender3.3mf"
    },
    "overrides": {
      "machine_width": {"default_value": 220},
      "machine_depth": {"default_value": 220},
      "machine_height": {"default_value": 250},
      "machine_name": {"default_value": "Creality Ender-3 Pro"}
    }
  },
  "cura_settings": {
    "layer_height": "0.2",
    "infill_sparse_density": "20",
    "support_enable": "true"
  }
}
```

**필드 설명:**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `task_id` | string | 조건부* | 이전 작업의 task_id |
| `stl_path` | string | 조건부* | STL 파일 직접 경로 |
| `printer_definition` | object | 선택 | 프린터 정의 JSON (전체 .def.json 내용) |
| `cura_settings` | object | 선택 | 커스텀 슬라이싱 설정 |

\* `task_id` 또는 `stl_path` 중 하나는 필수

**참고**: 실제 구현에서는 클라이언트가 `printer_definition`을 직접 전송합니다.
DB에 저장하는 방식은 선택 사항이며, 이 문서의 DB 스키마 부분을 참고하세요.

#### Response (성공)

```json
{
  "status": "ok",
  "data": {
    "task_id": "abc123-def456-789",
    "input_stl": "./output/cleaned_abc123.stl",
    "gcode_path": "./output/cleaned_abc123.gcode",
    "gcode_url": "http://localhost:7000/files/cleaned_abc123.gcode",
    "gcode_size": 1536000,
    "slicing_stats": {
      "layer_count": 150,
      "slice_time": 2.3,
      "export_time": 0.8
    },
    "cura_settings": {
      "layer_height": "0.2",
      "infill_sparse_density": "20"
    }
  }
}
```

#### Response (실패)

```json
{
  "status": "error",
  "error": "STL file not found: ./output/cleaned_abc123.stl"
}
```

---

## 데이터베이스 스키마 (권장)

### 테이블 1: `printer_profiles`

프린터 프로파일 정보를 저장합니다.

```sql
CREATE TABLE printer_profiles (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    manufacturer VARCHAR(50),
    model VARCHAR(50),

    -- 프린터 사양
    build_volume_x INT NOT NULL,  -- mm
    build_volume_y INT NOT NULL,  -- mm
    build_volume_z INT NOT NULL,  -- mm
    nozzle_diameter DECIMAL(3,2) DEFAULT 0.4,  -- mm

    -- 프린터 정의 파일 (2가지 방법 중 선택)
    definition_file_path TEXT,     -- 방법 1: 파일 시스템 경로
    definition_json TEXT,          -- 방법 2: JSON 전체 내용 (TEXT/JSONB)

    -- 기본 설정
    default_settings JSONB,        -- 이 프린터의 기본 설정

    -- 메타데이터
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 인덱스
    INDEX idx_printer_active (is_active),
    INDEX idx_printer_manufacturer_model (manufacturer, model)
);
```

**예시 데이터:**

```sql
INSERT INTO printer_profiles (id, name, manufacturer, model, build_volume_x, build_volume_y, build_volume_z,
                               definition_file_path, default_settings) VALUES
(
    'ender3pro_001',
    'Creality Ender-3 Pro',
    'Creality',
    'Ender-3 Pro',
    220,
    220,
    250,
    'C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\creality_ender3pro.def.json',
    '{
        "material_print_temperature": "200",
        "material_bed_temperature": "60",
        "layer_height": "0.2",
        "infill_sparse_density": "20"
    }'::jsonb
);
```

---

### 테이블 2: `material_profiles`

재료 프로파일을 저장합니다 (선택 사항).

```sql
CREATE TABLE material_profiles (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    material_type VARCHAR(50) NOT NULL,  -- PLA, ABS, PETG, TPU 등

    -- 재료별 기본 설정
    settings JSONB NOT NULL,

    -- 호환 프린터 (NULL이면 모든 프린터 가능)
    compatible_printers JSONB,  -- ["ender3pro_001", "prusa_mk3s"]

    -- 메타데이터
    manufacturer VARCHAR(50),
    color VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_material_type (material_type),
    INDEX idx_material_active (is_active)
);
```

**예시 데이터:**

```sql
INSERT INTO material_profiles (id, name, material_type, settings) VALUES
(
    'pla_standard',
    'Standard PLA',
    'PLA',
    '{
        "material_print_temperature": "200",
        "material_bed_temperature": "60",
        "material_print_temperature_layer_0": "205",
        "cool_fan_speed": "100"
    }'::jsonb
),
(
    'abs_standard',
    'Standard ABS',
    'ABS',
    '{
        "material_print_temperature": "240",
        "material_bed_temperature": "100",
        "material_print_temperature_layer_0": "245",
        "cool_fan_speed": "0"
    }'::jsonb
);
```

---

### 테이블 3: `slicing_presets`

미리 정의된 슬라이싱 프리셋을 저장합니다 (선택 사항).

```sql
CREATE TABLE slicing_presets (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    quality_level VARCHAR(20),  -- draft, normal, fine, ultra_fine

    -- 프리셋 설정
    settings JSONB NOT NULL,

    -- 호환성
    compatible_printers JSONB,  -- NULL이면 모든 프린터
    compatible_materials JSONB,  -- NULL이면 모든 재료

    -- 메타데이터
    is_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_preset_quality (quality_level),
    INDEX idx_preset_default (is_default)
);
```

**예시 데이터:**

```sql
INSERT INTO slicing_presets (id, name, quality_level, settings) VALUES
(
    'draft_fast',
    'Draft - Fast Print',
    'draft',
    '{
        "layer_height": "0.3",
        "infill_sparse_density": "10",
        "speed_print": "80",
        "wall_line_count": "2"
    }'::jsonb
),
(
    'normal_balanced',
    'Normal - Balanced',
    'normal',
    '{
        "layer_height": "0.2",
        "infill_sparse_density": "20",
        "speed_print": "50",
        "wall_line_count": "3"
    }'::jsonb
),
(
    'fine_detailed',
    'Fine - High Detail',
    'fine',
    '{
        "layer_height": "0.1",
        "infill_sparse_density": "25",
        "speed_print": "30",
        "wall_line_count": "4"
    }'::jsonb
);
```

---

### 테이블 4: `gcode_jobs` (슬라이싱 작업 이력)

```sql
CREATE TABLE gcode_jobs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(100) UNIQUE NOT NULL,

    -- 파일 정보
    stl_path TEXT NOT NULL,
    gcode_path TEXT,
    stl_size BIGINT,
    gcode_size BIGINT,

    -- 프린터 및 설정
    printer_id VARCHAR(50) REFERENCES printer_profiles(id),
    material_id VARCHAR(50) REFERENCES material_profiles(id),
    preset_id VARCHAR(50) REFERENCES slicing_presets(id),
    custom_settings JSONB,
    final_settings JSONB,  -- 실제 적용된 최종 설정

    -- 슬라이싱 결과
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed
    layer_count INT,
    estimated_print_time INT,  -- seconds
    filament_length DECIMAL(10,2),  -- mm
    filament_weight DECIMAL(10,2),  -- grams

    -- 로그 및 에러
    log_path TEXT,
    error_message TEXT,

    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    processing_time DECIMAL(10,3),  -- seconds

    INDEX idx_gcode_task (task_id),
    INDEX idx_gcode_status (status),
    INDEX idx_gcode_printer (printer_id),
    INDEX idx_gcode_created (created_at)
);
```

---

## Python API 사용 예시

### 1. 기본 사용 (로컬 .def.json 파일)

```python
from cura_processor import convert_stl_to_gcode

# 기본 설정으로 슬라이싱
success = await convert_stl_to_gcode(
    stl_path="/path/to/model.stl",
    gcode_path="/path/to/output.gcode"
)

# 커스텀 설정으로 슬라이싱
success = await convert_stl_to_gcode(
    stl_path="/path/to/model.stl",
    gcode_path="/path/to/output.gcode",
    custom_settings={
        "layer_height": "0.1",
        "infill_sparse_density": "30",
        "support_enable": "true"
    }
)
```

---

### 2. DB 프린터 프로파일 사용

```python
from cura_processor import convert_stl_to_gcode_with_db_profile

# DB에서 프린터 프로파일 조회 (예시)
async def get_printer_profile(printer_id: str):
    # 실제로는 DB 쿼리를 수행
    query = """
        SELECT definition_file_path, definition_json, default_settings
        FROM printer_profiles
        WHERE id = $1 AND is_active = true
    """
    result = await db.fetchrow(query, printer_id)

    return {
        'definition_json': result['definition_file_path'] or result['definition_json'],
        'settings': result['default_settings'] or {}
    }

# 슬라이싱 실행
printer_profile = await get_printer_profile('ender3pro_001')

success = await convert_stl_to_gcode_with_db_profile(
    stl_path="/path/to/model.stl",
    gcode_path="/path/to/output.gcode",
    printer_profile=printer_profile,
    custom_settings={
        "layer_height": "0.15"  # 사용자 오버라이드
    }
)
```

---

### 3. 완전한 워크플로우 (FastAPI 예시)

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cura_processor import convert_stl_to_gcode_with_db_profile
import asyncpg

app = FastAPI()

class GCodeRequest(BaseModel):
    task_id: str
    printer_id: str = "ender3pro_001"
    material_id: str = "pla_standard"
    preset_id: str = "normal_balanced"
    custom_settings: dict = {}


@app.post("/v1/slice/gcode")
async def generate_gcode_with_profile(request: GCodeRequest):
    """
    DB 프로파일을 사용한 G-code 생성
    """
    # 1. DB에서 프린터 프로파일 조회
    printer = await db.fetchrow(
        "SELECT * FROM printer_profiles WHERE id = $1",
        request.printer_id
    )
    if not printer:
        raise HTTPException(404, "Printer not found")

    # 2. 재료 프로파일 조회 (선택)
    material = await db.fetchrow(
        "SELECT settings FROM material_profiles WHERE id = $1",
        request.material_id
    )

    # 3. 프리셋 조회 (선택)
    preset = await db.fetchrow(
        "SELECT settings FROM slicing_presets WHERE id = $1",
        request.preset_id
    )

    # 4. 설정 병합 (우선순위: 기본 < 재료 < 프리셋 < 사용자)
    merged_settings = {}
    if printer['default_settings']:
        merged_settings.update(printer['default_settings'])
    if material:
        merged_settings.update(material['settings'])
    if preset:
        merged_settings.update(preset['settings'])
    merged_settings.update(request.custom_settings)

    # 5. STL 경로 결정
    stl_path = f"./output/cleaned_{request.task_id}.stl"
    gcode_path = f"./output/cleaned_{request.task_id}.gcode"

    # 6. 작업 이력 생성
    job_id = await db.fetchval(
        """
        INSERT INTO gcode_jobs
        (task_id, stl_path, gcode_path, printer_id, material_id, preset_id,
         custom_settings, final_settings, status, started_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'processing', NOW())
        RETURNING id
        """,
        request.task_id, stl_path, gcode_path,
        request.printer_id, request.material_id, request.preset_id,
        json.dumps(request.custom_settings),
        json.dumps(merged_settings)
    )

    try:
        # 7. 슬라이싱 실행
        printer_profile = {
            'definition_json': printer['definition_file_path'] or printer['definition_json'],
            'settings': printer['default_settings']
        }

        success = await convert_stl_to_gcode_with_db_profile(
            stl_path=stl_path,
            gcode_path=gcode_path,
            printer_profile=printer_profile,
            custom_settings=merged_settings
        )

        if not success:
            raise RuntimeError("Slicing failed")

        # 8. 작업 완료 업데이트
        await db.execute(
            """
            UPDATE gcode_jobs
            SET status = 'completed',
                completed_at = NOW(),
                processing_time = EXTRACT(EPOCH FROM (NOW() - started_at)),
                gcode_size = $2
            WHERE id = $1
            """,
            job_id,
            os.path.getsize(gcode_path)
        )

        return {
            "status": "ok",
            "job_id": job_id,
            "task_id": request.task_id,
            "gcode_url": f"/files/{os.path.basename(gcode_path)}"
        }

    except Exception as e:
        # 9. 실패 처리
        await db.execute(
            """
            UPDATE gcode_jobs
            SET status = 'failed',
                error_message = $2,
                completed_at = NOW()
            WHERE id = $1
            """,
            job_id,
            str(e)
        )
        raise HTTPException(500, str(e))
```

---

## CuraEngine 설정 파라미터 전체 목록

### 기본 프린트 설정

```json
{
  "layer_height": "0.2",                    // 레이어 높이 (mm)
  "initial_layer_height": "0.2",            // 첫 레이어 높이 (mm)
  "line_width": "0.4",                      // 라인 너비 (mm)
  "wall_line_count": "3",                   // 벽 레이어 수
  "wall_thickness": "1.2",                  // 벽 두께 (mm)
  "wall_0_wipe_dist": "0.0",                // 외벽 wipe 거리
  "top_layers": "4",                        // 상단 레이어 수
  "bottom_layers": "4",                     // 하단 레이어 수
  "top_thickness": "0.8",                   // 상단 두께 (mm)
  "bottom_thickness": "0.8"                 // 하단 두께 (mm)
}
```

### 인필 설정

```json
{
  "infill_sparse_density": "20",            // 인필 밀도 (%)
  "infill_pattern": "grid",                 // 패턴: grid, lines, cubic, gyroid, triangles
  "infill_overlap": "30",                   // 인필-벽 오버랩 (%)
  "infill_wipe_dist": "0.0",                // Wipe 거리
  "infill_before_walls": "false",           // 벽 먼저 프린트
  "zig_zaggify_infill": "false",            // 지그재그 활성화
  "connect_infill_polygons": "true"         // 인필 폴리곤 연결
}
```

### 속도 설정 (mm/s)

```json
{
  "speed_print": "50",                      // 기본 프린트 속도
  "speed_infill": "60",                     // 인필 속도
  "speed_wall": "40",                       // 벽 속도
  "speed_wall_0": "30",                     // 외벽 속도
  "speed_wall_x": "40",                     // 내벽 속도
  "speed_topbottom": "40",                  // 상하단 속도
  "speed_support": "50",                    // 서포트 속도
  "speed_travel": "150",                    // 이동 속도
  "speed_layer_0": "20",                    // 첫 레이어 속도
  "speed_print_layer_0": "20",              // 첫 레이어 프린트 속도
  "speed_travel_layer_0": "100"             // 첫 레이어 이동 속도
}
```

### 온도 설정 (°C)

```json
{
  "material_print_temperature": "200",                  // 노즐 온도
  "material_print_temperature_layer_0": "205",          // 첫 레이어 노즐 온도
  "material_initial_print_temperature": "200",          // 초기 온도
  "material_final_print_temperature": "200",            // 최종 온도
  "material_bed_temperature": "60",                     // 베드 온도
  "material_bed_temperature_layer_0": "60",             // 첫 레이어 베드 온도
  "material_standby_temperature": "175"                 // 대기 온도
}
```

### 서포트 설정

```json
{
  "support_enable": "false",                // 서포트 활성화
  "support_type": "buildplate",             // everywhere 또는 buildplate
  "support_angle": "50",                    // 서포트 각도 (°)
  "support_pattern": "zigzag",              // 패턴: zigzag, grid, triangles
  "support_infill_rate": "20",              // 서포트 밀도 (%)
  "support_line_distance": "2.0",           // 라인 간격 (mm)
  "support_z_distance": "0.2",              // Z 간격 (mm)
  "support_xy_distance": "0.7",             // XY 간격 (mm)
  "support_roof_enable": "true",            // 서포트 루프
  "support_bottom_enable": "false"          // 서포트 바닥
}
```

### 접착 설정

```json
{
  "adhesion_type": "skirt",                 // none, skirt, brim, raft
  "skirt_line_count": "3",                  // Skirt 라인 수
  "skirt_gap": "3",                         // Skirt 간격 (mm)
  "skirt_brim_minimal_length": "250",       // 최소 길이 (mm)
  "brim_width": "8",                        // Brim 너비 (mm)
  "brim_line_count": "20",                  // Brim 라인 수
  "raft_margin": "15",                      // Raft 마진 (mm)
  "raft_airgap": "0.3"                      // Raft 에어갭 (mm)
}
```

### 리트랙션 설정

```json
{
  "retraction_enable": "true",              // 리트랙션 활성화
  "retraction_amount": "5",                 // 거리 (mm)
  "retraction_speed": "45",                 // 속도 (mm/s)
  "retraction_retract_speed": "45",         // 당김 속도
  "retraction_prime_speed": "45",           // 밀어넣기 속도
  "retraction_extra_prime_amount": "0",     // 추가 프라임
  "retraction_min_travel": "1.5",           // 최소 이동 거리 (mm)
  "retraction_count_max": "100",            // 최대 리트랙션 횟수
  "retraction_extrusion_window": "10"       // 압출 윈도우 (mm)
}
```

### 냉각 설정

```json
{
  "cool_fan_enabled": "true",               // 쿨링팬 활성화
  "cool_fan_speed": "100",                  // 팬 속도 (%)
  "cool_fan_speed_0": "0",                  // 첫 레이어 팬 속도
  "cool_fan_speed_min": "100",              // 최소 팬 속도
  "cool_fan_speed_max": "100",              // 최대 팬 속도
  "cool_fan_full_at_height": "0.6",         // 최대 속도 높이 (mm)
  "cool_fan_full_layer": "4",               // 최대 속도 레이어
  "cool_min_layer_time": "10",              // 최소 레이어 시간 (초)
  "cool_min_layer_time_fan_speed_max": "10", // 최소 시간 (최대 팬)
  "cool_min_speed": "10",                   // 최소 속도 (mm/s)
  "cool_lift_head": "false"                 // 헤드 들어올리기
}
```

### 품질 설정

```json
{
  "optimize_wall_printing_order": "true",   // 벽 프린트 순서 최적화
  "outer_inset_first": "false",             // 외벽 먼저 프린트
  "alternate_extra_perimeter": "false",     // 교대 추가 둘레
  "fill_outline_gaps": "true",              // 아웃라인 갭 채우기
  "filter_out_tiny_gaps": "false",          // 작은 갭 필터링
  "fill_perimeter_gaps": "everywhere",      // 둘레 갭 채우기
  "xy_offset": "0",                         // XY 오프셋 (mm)
  "hole_xy_offset": "0",                    // 구멍 XY 오프셋
  "z_seam_type": "back",                    // Z 솔기: back, shortest, random
  "z_seam_x": "220",                        // Z 솔기 X 위치
  "z_seam_y": "220"                         // Z 솔기 Y 위치
}
```

---

## 환경 변수 설정

`.env` 파일에 다음을 추가:

```env
# CuraEngine 경로 (필수)
CURAENGINE_PATH=C:\Program Files\UltiMaker Cura 5.7.1\CuraEngine.exe

# 프린터 정의 파일 (필수 - DB 미사용 시)
CURA_DEFINITION_JSON=C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\creality_ender3pro.def.json

# 슬라이싱 타임아웃 (초)
CURA_TIMEOUT=300

# 상세 로깅
CURA_VERBOSE=true

# 출력 디렉토리
OUTPUT_DIR=./output
```

---

## 프린터 정의 파일 (.def.json) 저장 방법

### 방법 1: 파일 시스템 경로 저장 (권장)

```sql
UPDATE printer_profiles
SET definition_file_path = 'C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\creality_ender3pro.def.json'
WHERE id = 'ender3pro_001';
```

### 방법 2: JSON 내용 저장 (DB에 전체 포함)

```python
# .def.json 파일을 읽어서 DB에 저장
import json

with open('creality_ender3pro.def.json', 'r') as f:
    definition_json = f.read()

await db.execute(
    "UPDATE printer_profiles SET definition_json = $1 WHERE id = $2",
    definition_json,
    'ender3pro_001'
)
```

---

## 요약: G-code 변환 시 필요한 내용

### 1. **필수 입력**
- ✅ STL 파일 경로
- ✅ 출력 G-code 파일 경로
- ✅ 프린터 정의 파일 (.def.json) - DB 저장 또는 파일 경로

### 2. **선택 입력**
- 커스텀 슬라이싱 설정 (layer_height, infill 등)
- 재료 프로파일 (온도 설정)
- 슬라이싱 프리셋 (품질 레벨)

### 3. **DB 스키마**
- `printer_profiles` - 프린터 정보 및 .def.json
- `material_profiles` - 재료별 온도/속도 설정
- `slicing_presets` - 미리 정의된 품질 프리셋
- `gcode_jobs` - 슬라이싱 작업 이력 및 통계

### 4. **설정 병합 우선순위**
```
기본 설정 (DEFAULT_CURA_SETTINGS)
  ↓ 오버라이드
프린터 기본 설정 (printer_profiles.default_settings)
  ↓ 오버라이드
재료 설정 (material_profiles.settings)
  ↓ 오버라이드
프리셋 설정 (slicing_presets.settings)
  ↓ 오버라이드
사용자 커스텀 설정 (cura_settings)
```

### 5. **출력**
- G-code 파일 경로
- 슬라이싱 통계 (레이어 수, 예상 시간, 필라멘트 사용량)
- 로그 파일

---

## 다음 단계

1. ✅ `cura_processor.py` 구현 완료
2. DB 스키마 생성 및 프린터 프로파일 삽입
3. `main.py`에 DB 연동 로직 추가
4. 테스트 실행

구현 완료!
