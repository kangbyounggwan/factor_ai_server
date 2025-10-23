# 프린터 이름으로 G-code 슬라이싱 API 가이드

## 📋 개요

클라이언트가 DB에서 프린터 정보를 가져와서 `printer_name`을 전송하면, 서버가 해당 프린터로 G-code를 생성합니다.

---

## 🚀 API 엔드포인트

### POST `/v1/process/upload-stl-and-slice`

3D 모델 파일을 업로드하고 지정된 프린터로 G-code 슬라이싱

---

## 📤 Request

### Form-data 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `model_file` | File | ✅ | 3D 모델 파일 (STL, GLB, GLTF, OBJ) |
| `printer_name` | String | ⭐ | 프린터 이름 (DB의 filename에서 .def.json 제거) |
| `cura_settings_json` | String | ❌ | Cura 설정 JSON 문자열 |
| `printer_definition_json` | String | ❌ | 전체 프린터 정의 JSON (고급 사용자) |

**우선순위**: `printer_name` > `printer_definition_json` > 기본 프린터

---

## 📥 Response

### 성공 응답 (200 OK)

```json
{
  "status": "ok",
  "data": {
    "original_filename": "model.stl",
    "original_format": ".stl",
    "converted_to_stl": false,
    "stl_filename": "uploaded_model_1730000000.stl",
    "stl_path": "/output/uploaded_model_1730000000.stl",
    "stl_url": "http://server:7000/files/uploaded_model_1730000000.stl",
    "gcode_filename": "uploaded_model_1730000000.gcode",
    "gcode_path": "/output/uploaded_model_1730000000.gcode",
    "gcode_url": "http://server:7000/files/uploaded_model_1730000000.gcode",
    "file_size": {
      "stl_bytes": 10485760,
      "gcode_bytes": 524288
    },
    "printer_name": "elegoo_neptune_x",
    "printer_source": "client_name",
    "cura_settings": {
      "layer_height": "0.2"
    }
  }
}
```

### 에러 응답

```json
{
  "status": "error",
  "error": "Printer definition not found: invalid_printer_name"
}
```

---

## 💻 사용 예시

### 1. Python (requests)

```python
import requests

# DB에서 프린터 정보 가져오기
printer = db.query("SELECT filename FROM printers WHERE id = ?", [printer_id])
filename = printer['filename']  # "elegoo_neptune_x.def.json"

# printer_name 추출
printer_name = filename.replace('.def.json', '')  # "elegoo_neptune_x"

# API 요청
with open('model.stl', 'rb') as f:
    response = requests.post(
        'http://localhost:7000/v1/process/upload-stl-and-slice',
        files={'model_file': ('model.stl', f, 'application/octet-stream')},
        data={
            'printer_name': printer_name,
            'cura_settings_json': '{"layer_height":"0.2","infill_sparse_density":"20"}'
        }
    )

result = response.json()

if result['status'] == 'ok':
    gcode_url = result['data']['gcode_url']
    print(f"G-code URL: {gcode_url}")

    # G-code 다운로드
    gcode_response = requests.get(gcode_url)
    with open('output.gcode', 'wb') as f:
        f.write(gcode_response.content)
else:
    print(f"Error: {result['error']}")
```

### 2. JavaScript/TypeScript (Fetch API)

```javascript
// DB에서 프린터 정보 가져오기
const printer = await db.getPrinter(printerId);
const filename = printer.filename; // "elegoo_neptune_x.def.json"

// printer_name 추출
const printerName = filename.replace('.def.json', ''); // "elegoo_neptune_x"

// FormData 생성
const formData = new FormData();
formData.append('model_file', fileInput.files[0]);
formData.append('printer_name', printerName);
formData.append('cura_settings_json', JSON.stringify({
  layer_height: "0.2",
  infill_sparse_density: "20"
}));

// API 요청
const response = await fetch('http://localhost:7000/v1/process/upload-stl-and-slice', {
  method: 'POST',
  body: formData
});

const result = await response.json();

if (result.status === 'ok') {
  const gcodeUrl = result.data.gcode_url;
  console.log('G-code URL:', gcodeUrl);

  // G-code 다운로드
  const gcodeResponse = await fetch(gcodeUrl);
  const gcodeBlob = await gcodeResponse.blob();

  // 파일로 저장
  const url = window.URL.createObjectURL(gcodeBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'output.gcode';
  a.click();
} else {
  console.error('Error:', result.error);
}
```

### 3. cURL

```bash
# DB에서 filename 가져오기 (예: "elegoo_neptune_x.def.json")
# printer_name = "elegoo_neptune_x" (.def.json 제거)

curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.stl" \
  -F "printer_name=elegoo_neptune_x" \
  -F 'cura_settings_json={"layer_height":"0.2","infill_sparse_density":"20"}'
```

---

## 📊 DB 연동 예시

### DB 스키마

```sql
CREATE TABLE printers (
  id UUID PRIMARY KEY,
  manufacturer VARCHAR(100),
  series VARCHAR(100),
  model VARCHAR(100),
  display_name VARCHAR(200),
  filename VARCHAR(200),  -- "elegoo_neptune_x.def.json"
  -- ... 기타 컬럼
);
```

### 백엔드 코드 (Python/FastAPI 예시)

```python
from fastapi import FastAPI, UploadFile, File, Form
import httpx

app = FastAPI()

@app.post("/api/slice")
async def slice_model(
    file: UploadFile = File(...),
    printer_id: str = Form(...),
    layer_height: float = Form(0.2)
):
    # 1. DB에서 프린터 정보 조회
    printer = await db.get_printer(printer_id)

    if not printer:
        return {"error": "Printer not found"}

    # 2. filename에서 printer_name 추출
    filename = printer['filename']  # "elegoo_neptune_x.def.json"
    printer_name = filename.replace('.def.json', '')  # "elegoo_neptune_x"

    # 3. 슬라이싱 서버로 요청
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://slicing-server:7000/v1/process/upload-stl-and-slice',
            files={'model_file': (file.filename, await file.read())},
            data={
                'printer_name': printer_name,
                'cura_settings_json': f'{{"layer_height":"{layer_height}"}}'
            }
        )

    result = response.json()

    if result['status'] == 'ok':
        return {
            "success": True,
            "gcode_url": result['data']['gcode_url'],
            "printer_name": printer_name,
            "display_name": printer['display_name']
        }
    else:
        return {
            "success": False,
            "error": result['error']
        }
```

---

## 🔄 전체 워크플로우

```
1. 클라이언트
   ↓
   DB에서 프린터 정보 조회
   SELECT filename FROM printers WHERE id = ?
   ↓
   filename: "elegoo_neptune_x.def.json"
   ↓
   printer_name 추출: "elegoo_neptune_x"
   ↓
2. API 요청
   POST /v1/process/upload-stl-and-slice
   - model_file: STL 파일
   - printer_name: "elegoo_neptune_x"
   - cura_settings_json: {...}
   ↓
3. 서버
   ↓
   Cura definitions 디렉토리에서 파일 찾기
   C:\...\definitions\elegoo_neptune_x.def.json
   ↓
   CuraEngine이 상속 체인 해결
   elegoo_neptune_x → elegoo_base → fdmprinter
   ↓
   G-code 생성
   ↓
4. 응답
   {
     "gcode_url": "http://server/files/output.gcode",
     "printer_name": "elegoo_neptune_x"
   }
   ↓
5. 클라이언트
   G-code 다운로드 (2초 후 서버에서 자동 삭제)
```

---

## ⚙️ Cura 설정 예시

### 일반적인 설정

```json
{
  "layer_height": "0.2",
  "wall_line_count": "3",
  "infill_sparse_density": "20",
  "speed_print": "50",
  "material_print_temperature": "200",
  "material_bed_temperature": "60",
  "support_enable": "true",
  "adhesion_type": "brim"
}
```

### PLA 기본 설정

```json
{
  "layer_height": "0.2",
  "infill_sparse_density": "20",
  "material_print_temperature": "200",
  "material_bed_temperature": "60",
  "speed_print": "50"
}
```

### ABS 고온 설정

```json
{
  "layer_height": "0.2",
  "infill_sparse_density": "20",
  "material_print_temperature": "240",
  "material_bed_temperature": "100",
  "speed_print": "40"
}
```

---

## ⚠️ 주의사항

### 1. printer_name 형식

**올바른 형식**:
- ✅ `elegoo_neptune_x`
- ✅ `creality_ender3pro`
- ✅ `ultimaker2_plus`

**잘못된 형식**:
- ❌ `elegoo_neptune_x.def.json` (확장자 포함)
- ❌ `Elegoo Neptune X` (공백 포함)
- ❌ `ELEGOO NEPTUNE X` (대문자 + 공백)

### 2. 서버 요구사항

- **CuraEngine 설치 필수**: 서버에 CuraEngine과 definitions 디렉토리 필요
- **파일 존재 확인**: printer_name에 해당하는 .def.json 파일이 서버에 있어야 함

### 3. 파일 자동 삭제

- G-code 다운로드 후 **2초 뒤 서버에서 자동 삭제**
- 다운로드 실패 시 재요청 불가
- 필요 시 즉시 다운로드 권장

### 4. 에러 처리

| 에러 메시지 | 원인 | 해결 방법 |
|-----------|-----|---------|
| `Printer definition not found` | 존재하지 않는 printer_name | DB의 filename 확인 |
| `CuraEngine not available` | CuraEngine 미설치 | 서버 설정 확인 |
| `Slicing failed` | 슬라이싱 오류 | STL 파일 확인 |
| `Invalid cura_settings_json` | JSON 형식 오류 | JSON 문법 확인 |

---

## 📚 관련 문서

- [AUTO_CONVERT_GUIDE.md](./AUTO_CONVERT_GUIDE.md) - 파일 형식 자동 변환
- [STL_UPLOAD_API_GUIDE.md](./STL_UPLOAD_API_GUIDE.md) - STL 업로드 가이드
- [README_API.md](./README_API.md) - API 빠른 시작

---

## 🎯 실전 체크리스트

### 클라이언트 개발자

- [ ] DB에서 `filename` 컬럼 가져오기
- [ ] `.def.json` 제거하여 `printer_name` 추출
- [ ] FormData에 `printer_name` 포함
- [ ] G-code URL로 다운로드 구현
- [ ] 에러 처리 구현

### 백엔드 개발자

- [ ] DB에 `filename` 컬럼 저장
- [ ] 프린터 목록 API 제공
- [ ] 슬라이싱 서버 연동
- [ ] 파일 다운로드 프록시 (선택)

### DevOps

- [ ] 서버에 CuraEngine 설치
- [ ] definitions 디렉토리 마운트
- [ ] .env 파일 설정
- [ ] 타임아웃 설정 (CURA_TIMEOUT=300)

---

## 🎉 완료!

이제 DB의 프린터 정보만으로 손쉽게 G-code를 생성할 수 있습니다! 🚀
