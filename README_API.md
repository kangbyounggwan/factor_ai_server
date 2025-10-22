# Factor AI 3D 프린팅 API

3D 모델 파일 업로드, 자동 STL 변환, 슬라이싱, G-code 생성을 위한 완전한 API입니다.

**지원 파일 형식**: STL, GLB, GLTF, OBJ (자동 변환)

---

## 🚀 빠른 시작

### 1. 서버 실행

```bash
cd c:\Users\USER\factor_AI_python
uvicorn main:app --host 0.0.0.0 --port 7000 --reload
```

### 2. 3D 모델 파일 업로드 및 슬라이싱

```bash
# STL, GLB, GLTF, OBJ 모두 지원 (자동 변환)
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.stl" \
  -F 'cura_settings_json={"layer_height":"0.2","infill_sparse_density":"20"}'

# GLB 파일도 자동으로 STL 변환 후 슬라이싱
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.glb" \
  -F 'cura_settings_json={"layer_height":"0.2"}'
```

### 3. G-code 다운로드

```bash
curl -O http://localhost:7000/files/uploaded_model_{timestamp}.gcode
```

**다운로드 완료 후 서버에서 파일 자동 삭제됩니다!**

---

## 📚 API 문서

| 문서 | 설명 |
|------|------|
| **[AUTO_CONVERT_GUIDE.md](./AUTO_CONVERT_GUIDE.md)** | ⭐ 자동 STL 변환 및 슬라이싱 가이드 |
| **[STL_UPLOAD_API_GUIDE.md](./STL_UPLOAD_API_GUIDE.md)** | ⭐ STL 업로드 및 슬라이싱 완전 가이드 |
| **[CLIENT_API_GUIDE.md](./CLIENT_API_GUIDE.md)** | 클라이언트 개발자용 API 가이드 |
| [GCODE_API_GUIDE.md](./GCODE_API_GUIDE.md) | 상세 기술 문서 (DB 확장 포함) |
| [FINAL_SUMMARY.md](./FINAL_SUMMARY.md) | 전체 구현 요약 |

⭐ = 가장 자주 사용되는 문서

---

## 🎯 주요 엔드포인트

### 1. 3D 모델 업로드 및 슬라이싱 (권장)

**`POST /v1/process/upload-stl-and-slice`**

Form-data로 3D 모델 파일을 업로드하고 즉시 G-code로 변환합니다.

**지원 파일 형식**:
- `.stl` - 직접 슬라이싱
- `.glb` - 자동 STL 변환 후 슬라이싱
- `.gltf` - 자동 STL 변환 후 슬라이싱
- `.obj` - 자동 STL 변환 후 슬라이싱

```python
import requests
import json

# STL, GLB, GLTF, OBJ 모두 동일한 방식으로 사용
with open('model.glb', 'rb') as f:  # .stl, .glb, .gltf, .obj
    response = requests.post(
        'http://localhost:7000/v1/process/upload-stl-and-slice',
        files={'model_file': f},  # 파라미터명 변경: stl_file -> model_file
        data={
            'cura_settings_json': json.dumps({
                "layer_height": "0.2",
                "infill_sparse_density": "20",
                "support_enable": "true"
            })
        }
    )

result = response.json()
print(f"Original format: {result['data']['original_format']}")
print(f"Converted to STL: {result['data']['converted_to_stl']}")
print(f"G-code URL: {result['data']['gcode_url']}")
```

---

### 2. 이미지 → 3D 모델 생성

**`POST /v1/process/modelling`**

이미지 파일에서 3D 모델(GLB, STL)을 자동 생성합니다.

```python
with open('photo.jpg', 'rb') as f:
    response = requests.post(
        'http://localhost:7000/v1/process/modelling',
        files={'image_file': f},
        data={'task': 'image_to_3d', 'json': '{}'}
    )

task_id = response.json()['data']['task_id']
stl_url = response.json()['data']['stl_download_url']
```

---

### 3. G-code 생성 (Task ID 방식)

**`POST /v1/process/generate-gcode`**

이전 작업의 STL 파일을 G-code로 변환합니다.

```python
response = requests.post(
    'http://localhost:7000/v1/process/generate-gcode',
    json={
        'task_id': 'abc123-def456',
        'cura_settings': {
            'layer_height': '0.15',
            'infill_sparse_density': '30'
        }
    }
)

gcode_url = response.json()['data']['gcode_url']
```

---

### 4. 파일 다운로드 (자동 삭제)

**`GET /files/{filename}`**

파일을 다운로드합니다. **다운로드 완료 후 2초 뒤 서버에서 자동 삭제됩니다.**

```python
gcode = requests.get('http://localhost:7000/files/model.gcode').text
# 서버 파일은 자동으로 삭제됨
```

---

## ⚙️ 주요 기능

### ✅ 구현된 기능

1. **STL 파일 직접 업로드** - Form-data로 간편하게 업로드
2. **즉시 슬라이싱** - 업로드와 동시에 G-code 생성
3. **프린터 정의 커스터마이징** - 클라이언트가 원하는 프린터 설정 전송
4. **다운로드 후 자동 삭제** - 디스크 공간 자동 관리
5. **자동 파일 정리** - 최신 50개 파일만 서버에 유지
6. **이미지 → 3D 모델** - AI 기반 3D 모델 자동 생성
7. **Blender 후처리** - 메시 정리 및 최적화

---

## 🔧 설정

### 환경 변수 (.env)

```env
# 출력 디렉토리
OUTPUT_DIR=./output

# 공개 URL
PUBLIC_BASE_URL=http://localhost:7000

# CuraEngine
CURAENGINE_PATH=C:\Program Files\UltiMaker Cura 5.7.1\CuraEngine.exe
CURA_DEFINITION_JSON=C:\...\creality_ender3pro.def.json
CURA_TIMEOUT=300

# Blender (선택)
BLENDER_PATH=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe

# Meshy API
MESHY_API_KEY=your_key_here
```

---

## 📋 전체 워크플로우

### 방법 1: STL 직접 업로드 (빠름)

```
1. STL 파일 업로드
   POST /v1/process/upload-stl-and-slice
   ↓
2. 즉시 G-code 생성
   ↓
3. G-code 다운로드
   GET /files/model.gcode
   ↓
4. 서버 파일 자동 삭제
```

### 방법 2: 이미지 → 3D 모델 → G-code (완전 자동)

```
1. 이미지 업로드
   POST /v1/process/modelling
   ↓
2. AI가 3D 모델 생성 (GLB)
   ↓
3. Blender 후처리 + STL 변환
   ↓
4. G-code 생성
   POST /v1/process/generate-gcode
   ↓
5. G-code 다운로드
   ↓
6. 서버 파일 자동 삭제
```

---

## 🎨 Cura 슬라이싱 설정

### 기본 설정

```json
{
  "layer_height": "0.2",              // 레이어 높이 (mm)
  "wall_line_count": "3",             // 벽 레이어 수
  "infill_sparse_density": "20",      // 인필 밀도 (%)
  "infill_pattern": "grid",           // 인필 패턴
  "speed_print": "50",                // 프린트 속도 (mm/s)
  "support_enable": "false",          // 서포트 활성화
  "adhesion_type": "skirt"            // 접착 타입
}
```

### 고급 설정

```json
{
  "material_print_temperature": "200",      // 노즐 온도 (°C)
  "material_bed_temperature": "60",         // 베드 온도 (°C)
  "retraction_amount": "5",                 // 리트랙션 거리 (mm)
  "cool_fan_speed": "100",                  // 냉각 팬 속도 (%)
  "speed_wall_0": "30",                     // 외벽 속도 (mm/s)
  "support_angle": "50",                    // 서포트 각도 (°)
  "brim_width": "8"                         // Brim 너비 (mm)
}
```

**전체 90개+ 설정**: [GCODE_API_GUIDE.md](./GCODE_API_GUIDE.md) 참조

---

## 🖨️ 프린터 정의

### 클라이언트에서 프린터 정의 전송 (권장)

```json
{
  "printer_definition": {
    "version": 2,
    "name": "Creality Ender-3 Pro",
    "overrides": {
      "machine_width": {"default_value": 220},
      "machine_depth": {"default_value": 220},
      "machine_height": {"default_value": 250},
      "machine_nozzle_size": {"default_value": 0.4}
    }
  }
}
```

### 프린터 정의 파일 위치

Cura 설치 디렉토리:
```
C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\
```

주요 프린터:
- `creality_ender3pro.def.json` - Ender-3 Pro
- `prusa_i3.def.json` - Prusa i3
- `ultimaker2.def.json` - Ultimaker 2

---

## 🧪 테스트

### 테스트 스크립트 실행

```bash
# Cura 프로세서 테스트
python test_cura.py

# STL 업로드 테스트
python test_upload_stl.py
```

### 수동 테스트

```bash
# Health check
curl http://localhost:7000/health

# STL 업로드
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "stl_file=@test.stl"

# G-code 다운로드
curl -O http://localhost:7000/files/uploaded_test_{timestamp}.gcode
```

---

## ⚠️ 중요 사항

### 1. 파일 자동 삭제
- 다운로드 완료 후 **2초 뒤** 서버 파일 자동 삭제
- 백업이 필요한 파일은 반드시 로컬에 저장

### 2. 파일 정리
- 서버는 **최신 50개 파일만 유지**
- 오래된 파일은 자동으로 삭제됨

### 3. 설정 값 형식
- 모든 Cura 설정 값은 **문자열**로 전송
- 예: `"layer_height": "0.2"` ✅
- 예: `"layer_height": 0.2` ❌

---

## 🔍 에러 처리

| 상태 코드 | 설명 | 해결 방법 |
|-----------|------|-----------|
| 400 | 잘못된 요청 | JSON 형식 확인 |
| 404 | 파일 없음 | task_id 또는 파일명 확인 |
| 500 | 서버 오류 | 로그 확인 |
| 503 | CuraEngine 없음 | 서버 설정 확인 |

---

## 📊 파일 명명 규칙

### STL 업로드
```
입력: mymodel.stl
서버 저장: uploaded_mymodel_1730000000.stl
G-code: uploaded_mymodel_1730000000.gcode
```

### 이미지 → 3D
```
Task ID: abc123-def456-789
GLB: model_abc123.glb
Cleaned GLB: cleaned_abc123.glb
STL: cleaned_abc123.stl
G-code: cleaned_abc123.gcode
```

---

## 🎉 지원되는 파일 형식

### 입력
- **이미지**: JPG, PNG, JPEG (3D 모델 생성용)
- **3D 모델** (슬라이싱용):
  - `.stl` - 직접 슬라이싱
  - `.glb` - 자동 STL 변환 후 슬라이싱
  - `.gltf` - 자동 STL 변환 후 슬라이싱
  - `.obj` - 자동 STL 변환 후 슬라이싱
- **프린터 정의**: JSON (.def.json)

### 출력
- **3D 모델**: GLB, STL
- **G-code**: .gcode
- **로그**: .txt

### 자동 변환 프로세스
```
GLB/GLTF/OBJ 업로드
  ↓
Trimesh 라이브러리로 로드
  ↓
메시 병합 (여러 객체)
  ↓
메시 수리 (구멍 메우기, 면 수정)
  ↓
STL로 내보내기
  ↓
원본 파일 삭제
  ↓
CuraEngine으로 슬라이싱
```

---

## 💡 사용 팁

1. **빠른 테스트**: STL 직접 업로드 사용
2. **자동 생성**: 이미지에서 3D 모델 자동 생성
3. **디스크 관리**: 서버 파일은 자동으로 정리됨
4. **프린터 설정**: 클라이언트에서 프린터 정의 캐싱하여 재사용

---

## 📞 추가 정보

- **GitHub**: [프로젝트 링크]
- **문서**: 이 디렉토리의 MD 파일들 참조
- **예제**: `examples/` 디렉토리 참조

---

**모든 기능이 완벽하게 작동합니다!** 🚀
