# STL 업로드 및 자동 삭제 API 가이드

## 개요

STL 파일을 직접 업로드하여 G-code로 변환하고, 다운로드 완료 후 자동으로 파일을 삭제하는 API입니다.

---

## 주요 기능

### 1. STL 파일 업로드 및 슬라이싱
- Form-data로 STL 파일 직접 업로드
- 즉시 G-code 변환
- 프린터 정의 및 슬라이싱 설정 커스터마이징

### 2. 다운로드 후 자동 삭제
- `/files/{filename}` 다운로드 완료 시 해당 파일 자동 삭제
- 서버 디스크 공간 절약

### 3. 자동 파일 정리
- output/ 디렉토리에 최신 50개 파일만 유지
- 오래된 파일 자동 삭제

---

## API 엔드포인트

### 1. POST `/v1/process/upload-stl-and-slice`

STL 파일을 업로드하고 즉시 G-code로 슬라이싱합니다.

#### Request (Form-data)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `stl_file` | File | 필수 | STL 파일 |
| `cura_settings_json` | string | 선택 | Cura 설정 JSON 문자열 |
| `printer_definition_json` | string | 선택 | 프린터 정의 JSON 문자열 |

#### Request Example

**cURL:**
```bash
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "stl_file=@mymodel.stl" \
  -F 'cura_settings_json={"layer_height":"0.2","infill_sparse_density":"20"}' \
  -F 'printer_definition_json={"version":2,"name":"My Printer","overrides":{"machine_width":{"default_value":220}}}'
```

**Python:**
```python
import requests
import json

# STL 파일 및 설정
stl_file_path = "mymodel.stl"
cura_settings = {
    "layer_height": "0.2",
    "infill_sparse_density": "20",
    "support_enable": "true"
}
printer_definition = {
    "version": 2,
    "name": "Creality Ender-3 Pro",
    "overrides": {
        "machine_width": {"default_value": 220},
        "machine_depth": {"default_value": 220},
        "machine_height": {"default_value": 250}
    }
}

# 업로드
with open(stl_file_path, 'rb') as f:
    response = requests.post(
        'http://localhost:7000/v1/process/upload-stl-and-slice',
        files={'stl_file': f},
        data={
            'cura_settings_json': json.dumps(cura_settings),
            'printer_definition_json': json.dumps(printer_definition)
        }
    )

result = response.json()
print(f"G-code URL: {result['data']['gcode_url']}")
```

**JavaScript/TypeScript:**
```typescript
async function uploadAndSlice(stlFile: File) {
  const formData = new FormData();
  formData.append('stl_file', stlFile);

  const curaSettings = {
    layer_height: "0.2",
    infill_sparse_density: "20",
    support_enable: "true"
  };

  const printerDef = {
    version: 2,
    name: "My Printer",
    overrides: {
      machine_width: { default_value: 220 },
      machine_depth: { default_value: 220 },
      machine_height: { default_value: 250 }
    }
  };

  formData.append('cura_settings_json', JSON.stringify(curaSettings));
  formData.append('printer_definition_json', JSON.stringify(printerDef));

  const response = await fetch('http://localhost:7000/v1/process/upload-stl-and-slice', {
    method: 'POST',
    body: formData
  });

  const result = await response.json();
  return result.data.gcode_url;
}
```

#### Response

**성공:**
```json
{
  "status": "ok",
  "data": {
    "stl_filename": "uploaded_mymodel_1730000000.stl",
    "stl_path": "./output/uploaded_mymodel_1730000000.stl",
    "stl_url": "http://localhost:7000/files/uploaded_mymodel_1730000000.stl",
    "gcode_filename": "uploaded_mymodel_1730000000.gcode",
    "gcode_path": "./output/uploaded_mymodel_1730000000.gcode",
    "gcode_url": "http://localhost:7000/files/uploaded_mymodel_1730000000.gcode",
    "file_size": {
      "stl_bytes": 10485760,
      "gcode_bytes": 524288
    },
    "cura_settings": {
      "layer_height": "0.2",
      "infill_sparse_density": "20"
    }
  }
}
```

**실패:**
```json
{
  "status": "error",
  "error": "Invalid cura_settings_json format"
}
```

---

### 2. GET `/files/{filename}`

파일 다운로드 (다운로드 완료 후 자동 삭제)

#### Request

```bash
GET /files/uploaded_mymodel_1730000000.gcode
```

#### Response

- **200**: 파일 전송 (다운로드 완료 후 2초 뒤 자동 삭제)
- **404**: 파일 없음

**특징:**
- 다운로드 완료 후 백그라운드에서 파일 자동 삭제
- 서버 디스크 공간 자동 관리

---

## 자동 파일 정리

### 정리 정책

- **트리거**: STL 업로드 및 슬라이싱 완료 시
- **유지 개수**: 최신 50개 파일
- **대상 파일**: `*.stl`, `*.gcode`, `*.glb`, `*.jpg`, `*.png`
- **정렬 기준**: 파일 수정 시간 (오래된 것부터 삭제)

### 동작 방식

```
1. 새 파일 업로드 및 슬라이싱
   ↓
2. output/ 디렉토리 파일 개수 확인
   ↓
3. 50개 초과 시:
   - 수정 시간 기준 정렬
   - 가장 오래된 파일부터 삭제
   - 최신 50개만 유지
   ↓
4. 로그 기록
```

**로그 예시:**
```
[Cleanup] Total files: 75, deleting oldest 25 files
[Cleanup] Deleted: old_model_001.stl
[Cleanup] Deleted: old_model_001.gcode
...
[Cleanup] Completed. Remaining files: 50
```

---

## 전체 워크플로우

### 방법 1: 직접 STL 업로드

```
1. 클라이언트가 STL 파일 업로드
   POST /v1/process/upload-stl-and-slice
   form-data: { stl_file, cura_settings_json, printer_definition_json }
   ↓
2. 서버에서 즉시 슬라이싱
   - STL 저장 (uploaded_{name}_{timestamp}.stl)
   - G-code 생성 (uploaded_{name}_{timestamp}.gcode)
   - 자동 파일 정리 (최신 50개 유지)
   ↓
3. 응답: STL URL, G-code URL
   ↓
4. 클라이언트가 G-code 다운로드
   GET /files/uploaded_mymodel_1730000000.gcode
   ↓
5. 다운로드 완료 후 2초 뒤 파일 자동 삭제
```

---

### 방법 2: 이미지 → 3D 모델 → STL → G-code (기존)

```
1. 이미지 업로드
   POST /v1/process/modelling
   ↓
2. 3D 모델 생성 (Meshy API)
   → GLB 파일
   ↓
3. Blender 후처리 및 STL 변환
   → cleaned_{task_id}.stl
   ↓
4. G-code 생성
   POST /v1/process/generate-gcode
   { "task_id": "..." }
   ↓
5. G-code 다운로드
   GET /files/cleaned_{task_id}.gcode
   ↓
6. 다운로드 완료 후 자동 삭제
```

---

## 사용 예시

### Python 클라이언트 예시

```python
import requests
import json
from pathlib import Path

def upload_stl_and_slice(stl_path: str):
    """STL 파일 업로드 및 슬라이싱"""

    # 설정
    cura_settings = {
        "layer_height": "0.15",
        "infill_sparse_density": "25",
        "support_enable": "true",
        "adhesion_type": "brim",
        "speed_print": "50"
    }

    printer_def = {
        "version": 2,
        "name": "Creality Ender-3 Pro",
        "metadata": {"visible": True},
        "overrides": {
            "machine_width": {"default_value": 220},
            "machine_depth": {"default_value": 220},
            "machine_height": {"default_value": 250},
            "machine_nozzle_size": {"default_value": 0.4}
        }
    }

    # 업로드
    with open(stl_path, 'rb') as f:
        response = requests.post(
            'http://localhost:7000/v1/process/upload-stl-and-slice',
            files={'stl_file': (Path(stl_path).name, f)},
            data={
                'cura_settings_json': json.dumps(cura_settings),
                'printer_definition_json': json.dumps(printer_def)
            }
        )

    result = response.json()

    if result['status'] == 'ok':
        gcode_url = result['data']['gcode_url']
        print(f"✅ Slicing completed!")
        print(f"   G-code URL: {gcode_url}")

        # G-code 다운로드
        gcode_response = requests.get(gcode_url)

        # 로컬에 저장
        local_gcode_path = "output.gcode"
        with open(local_gcode_path, 'wb') as f:
            f.write(gcode_response.content)

        print(f"   Downloaded: {local_gcode_path}")
        print(f"   (서버 파일은 2초 후 자동 삭제됩니다)")

        return local_gcode_path
    else:
        raise Exception(f"Slicing failed: {result['error']}")


# 사용
gcode_file = upload_stl_and_slice("mymodel.stl")
print(f"G-code ready: {gcode_file}")
```

---

### JavaScript/TypeScript 클라이언트 예시

```typescript
interface SliceResult {
  stl_filename: string;
  gcode_filename: string;
  gcode_url: string;
  file_size: {
    stl_bytes: number;
    gcode_bytes: number;
  };
}

async function uploadSTLAndSlice(
  stlFile: File,
  curaSettings?: Record<string, string>,
  printerDef?: any
): Promise<SliceResult> {

  const formData = new FormData();
  formData.append('stl_file', stlFile);

  // 기본 설정
  const defaultSettings = {
    layer_height: "0.2",
    infill_sparse_density: "20",
    support_enable: "false",
    adhesion_type: "skirt"
  };

  const defaultPrinter = {
    version: 2,
    name: "Default Printer",
    overrides: {
      machine_width: { default_value: 220 },
      machine_depth: { default_value: 220 },
      machine_height: { default_value: 250 }
    }
  };

  formData.append('cura_settings_json',
    JSON.stringify(curaSettings || defaultSettings));
  formData.append('printer_definition_json',
    JSON.stringify(printerDef || defaultPrinter));

  const response = await fetch('http://localhost:7000/v1/process/upload-stl-and-slice', {
    method: 'POST',
    body: formData
  });

  const result = await response.json();

  if (result.status !== 'ok') {
    throw new Error(result.error);
  }

  return result.data;
}

// 사용 예시
const fileInput = document.getElementById('stl-upload') as HTMLInputElement;
fileInput.addEventListener('change', async (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;

  try {
    const result = await uploadSTLAndSlice(file, {
      layer_height: "0.15",
      infill_sparse_density: "30"
    });

    console.log('G-code URL:', result.gcode_url);

    // 다운로드
    const link = document.createElement('a');
    link.href = result.gcode_url;
    link.download = result.gcode_filename;
    link.click();

    // 서버 파일은 다운로드 후 자동 삭제됨
  } catch (error) {
    console.error('Slicing failed:', error);
  }
});
```

---

## 파일 명명 규칙

### STL 업로드 방식
```
업로드 파일: mymodel.stl
↓
서버 저장: uploaded_mymodel_1730000000.stl
G-code: uploaded_mymodel_1730000000.gcode
```

### 이미지 → 3D 방식
```
Task ID: 0199e86c-5074-7883-ba58-e6445e486c70
↓
GLB: model_{task_id}.glb
Cleaned GLB: cleaned_{task_id}.glb
STL: cleaned_{task_id}.stl
G-code: cleaned_{task_id}.gcode
```

---

## 환경 변수

```env
# 파일 저장 디렉토리
OUTPUT_DIR=./output

# 공개 URL (다운로드 링크용)
PUBLIC_BASE_URL=http://localhost:7000

# CuraEngine 설정
CURAENGINE_PATH=C:\Program Files\UltiMaker Cura 5.7.1\CuraEngine.exe
CURA_DEFINITION_JSON=C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\creality_ender3pro.def.json
CURA_TIMEOUT=300
CURA_VERBOSE=true
```

---

## 주의사항

### 1. 다운로드 후 삭제 타이밍
- 파일 다운로드 완료 후 **2초 후** 자동 삭제
- 다운로드가 느린 경우 삭제 전에 완료되지 않을 수 있음
- 필요시 `mark_for_deletion()` 함수의 `await asyncio.sleep(2)` 값 조정

### 2. 파일 정리
- 업로드 및 슬라이싱 완료 시마다 자동 실행
- 최신 50개 유지 (환경에 따라 조정 가능)
- 로그 파일(`*.txt`)은 자동 삭제 대상 아님

### 3. 동시 업로드
- 여러 클라이언트가 동시에 업로드 가능
- 타임스탬프로 파일명 중복 방지
- 파일 정리는 전체 디렉토리 기준

---

## 에러 처리

| 상태 코드 | 설명 | 해결 방법 |
|-----------|------|-----------|
| 400 | JSON 형식 오류 | `cura_settings_json`, `printer_definition_json` 검증 |
| 404 | 파일 없음 | 다운로드 URL 확인 |
| 500 | 슬라이싱 실패 | 로그 확인, STL 파일 유효성 검증 |
| 503 | CuraEngine 없음 | 서버 설정 확인 |

---

## 테스트

### 테스트 스크립트 실행

```bash
cd c:\Users\USER\factor_AI_python
python test_upload_stl.py
```

### 수동 테스트

```bash
# 1. STL 업로드 및 슬라이싱
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "stl_file=@test.stl" \
  -F 'cura_settings_json={"layer_height":"0.2"}'

# 2. G-code 다운로드
curl -O http://localhost:7000/files/uploaded_test_1730000000.gcode

# 3. 2초 후 서버에서 파일 자동 삭제 확인
ls ./output/
```

---

## 요약

### ✅ 새로 추가된 기능

1. **STL 파일 직접 업로드**: Form-data로 즉시 업로드 가능
2. **다운로드 후 자동 삭제**: 디스크 공간 절약
3. **자동 파일 정리**: 최신 50개만 유지

### 📋 API 엔드포인트

- `POST /v1/process/upload-stl-and-slice` - STL 업로드 및 슬라이싱
- `GET /files/{filename}` - 파일 다운로드 (자동 삭제)

### 🎯 사용 시나리오

1. **빠른 슬라이싱**: 기존 STL 파일을 즉시 G-code로 변환
2. **디스크 관리**: 서버에 파일 누적되지 않도록 자동 정리
3. **백업 유지**: 최신 50개 모델은 서버에 보관

**모든 구현이 완료되었습니다!** 🎉
