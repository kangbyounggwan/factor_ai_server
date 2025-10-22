# 자동 STL 변환 기능 구현 완료

## ✅ 구현 완료 사항

### 1. 파일 형식 자동 감지 및 변환

**지원 파일 형식**:
- `.stl` - 변환 불필요, 직접 슬라이싱
- `.glb` - 자동 STL 변환 후 슬라이싱
- `.gltf` - 자동 STL 변환 후 슬라이싱
- `.obj` - 자동 STL 변환 후 슬라이싱

### 2. 구현 위치

**파일**: [main.py](c:\Users\USER\factor_AI_python\main.py)
**함수**: `upload_stl_and_slice()` (라인 567-751)
**엔드포인트**: `POST /v1/process/upload-stl-and-slice`

### 3. 주요 변경 사항

#### 파라미터 변경
```python
# 이전
stl_file: UploadFile = File(...)

# 변경 후 (모든 3D 모델 형식 지원)
model_file: UploadFile = File(...)
```

#### 파일 확장자 감지
```python
file_ext = file_ext.lower()

if file_ext == ".stl":
    # 변환 불필요

elif file_ext in [".glb", ".gltf", ".obj"]:
    # Trimesh로 자동 변환

else:
    # 지원하지 않는 형식
    raise HTTPException(400, "Unsupported file format")
```

#### Trimesh 변환 로직
```python
import trimesh

# 파일 로드
mesh = trimesh.load(temp_path, file_type=file_ext[1:])

# 여러 메시 병합 (Scene인 경우)
if hasattr(mesh, "geometry"):
    mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))

# 메시 수리
trimesh.repair.fix_inversion(mesh)      # 반전 수정
trimesh.repair.fill_holes(mesh)         # 구멍 메우기
mesh.remove_degenerate_faces()          # 퇴화된 면 제거
mesh.remove_duplicate_faces()           # 중복 면 제거
mesh.remove_unreferenced_vertices()     # 미사용 정점 제거

# STL로 내보내기
mesh.export(stl_path, file_type='stl')

# 원본 파일 삭제 (디스크 공간 절약)
os.remove(temp_path)
```

### 4. Response 형식

#### STL 직접 업로드
```json
{
  "status": "ok",
  "data": {
    "original_filename": "model.stl",
    "original_format": ".stl",
    "converted_to_stl": false,
    "stl_filename": "uploaded_model_1730000000.stl",
    "stl_url": "http://localhost:7000/files/uploaded_model_1730000000.stl",
    "gcode_filename": "uploaded_model_1730000000.gcode",
    "gcode_url": "http://localhost:7000/files/uploaded_model_1730000000.gcode",
    "file_size": {
      "stl_bytes": 10485760,
      "gcode_bytes": 524288
    }
  }
}
```

#### GLB 자동 변환
```json
{
  "status": "ok",
  "data": {
    "original_filename": "model.glb",
    "original_format": ".glb",
    "converted_to_stl": true,        // ✅ 변환됨
    "stl_filename": "uploaded_model_1730000000.stl",
    "stl_url": "http://localhost:7000/files/uploaded_model_1730000000.stl",
    "gcode_filename": "uploaded_model_1730000000.gcode",
    "gcode_url": "http://localhost:7000/files/uploaded_model_1730000000.gcode",
    "file_size": {
      "stl_bytes": 8388608,
      "gcode_bytes": 524288
    }
  }
}
```

### 5. 에러 처리

#### 지원하지 않는 형식
```json
{
  "status": "error",
  "error": "Unsupported file format: .fbx. Supported: .stl, .glb, .gltf, .obj"
}
```

#### Trimesh 없음
```json
{
  "status": "error",
  "error": "Trimesh library not available for file conversion"
}
```

#### 변환 실패
```json
{
  "status": "error",
  "error": "Failed to convert .glb to STL: [상세 에러 메시지]"
}
```

---

## 📋 사용 예시

### cURL

```bash
# STL 직접 업로드
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.stl" \
  -F 'cura_settings_json={"layer_height":"0.2"}'

# GLB 자동 변환
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.glb" \
  -F 'cura_settings_json={"layer_height":"0.2"}'

# OBJ 자동 변환
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.obj" \
  -F 'cura_settings_json={"layer_height":"0.15"}'
```

### Python

```python
import requests
import json

def upload_and_slice(model_path: str):
    """모든 3D 모델 파일 업로드 및 슬라이싱"""

    with open(model_path, 'rb') as f:
        response = requests.post(
            'http://localhost:7000/v1/process/upload-stl-and-slice',
            files={'model_file': f},
            data={
                'cura_settings_json': json.dumps({
                    "layer_height": "0.2",
                    "infill_sparse_density": "20"
                })
            }
        )

    result = response.json()

    if result['status'] == 'ok':
        data = result['data']
        print(f"Original: {data['original_format']}")
        print(f"Converted: {data['converted_to_stl']}")
        print(f"G-code: {data['gcode_url']}")
        return data['gcode_url']
    else:
        raise Exception(f"Failed: {result['error']}")

# 모든 형식 동일하게 사용
upload_and_slice('model.stl')
upload_and_slice('model.glb')
upload_and_slice('model.obj')
```

### JavaScript/TypeScript

```javascript
async function uploadAndSlice(file) {
  const formData = new FormData();
  formData.append('model_file', file);
  formData.append('cura_settings_json', JSON.stringify({
    layer_height: "0.2",
    infill_sparse_density: "20"
  }));

  const response = await fetch(
    'http://localhost:7000/v1/process/upload-stl-and-slice',
    {
      method: 'POST',
      body: formData
    }
  );

  const result = await response.json();

  if (result.status === 'ok') {
    console.log('Original format:', result.data.original_format);
    console.log('Converted to STL:', result.data.converted_to_stl);
    return result.data.gcode_url;
  } else {
    throw new Error(result.error);
  }
}

// 파일 입력 예시
const fileInput = document.getElementById('file-upload');
fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  // STL, GLB, GLTF, OBJ 모두 자동 처리
  const gcodeUrl = await uploadAndSlice(file);
  console.log('G-code URL:', gcodeUrl);
});
```

---

## 🔄 변환 프로세스

### STL 파일 (변환 불필요)
```
STL 업로드
  ↓
파일 저장
  ↓
CuraEngine 슬라이싱
  ↓
G-code 생성
  ↓
파일 정리 (최신 50개 유지)
  ↓
Response 반환
```

### GLB/GLTF/OBJ 파일 (자동 변환)
```
GLB/GLTF/OBJ 업로드
  ↓
임시 파일로 저장
  ↓
Trimesh로 파일 로드
  ↓
여러 메시 병합 (Scene인 경우)
  ↓
메시 수리
  - 반전 수정
  - 구멍 메우기
  - 퇴화 면 제거
  - 중복 면 제거
  - 미사용 정점 제거
  ↓
STL로 내보내기
  ↓
원본 파일 삭제
  ↓
CuraEngine 슬라이싱
  ↓
G-code 생성
  ↓
파일 정리 (최신 50개 유지)
  ↓
Response 반환
```

---

## 🧪 테스트

### 테스트 스크립트

**파일**: [test_auto_convert.py](c:\Users\USER\factor_AI_python\test_auto_convert.py)

```bash
# 서버 실행
uvicorn main:app --reload --port 7000

# 테스트 실행 (다른 터미널)
python test_auto_convert.py
```

### 테스트 결과 예시
```
============================================================
Auto-Conversion Test
============================================================

[TEST] STL file: model_abc123.stl
  [OK] Upload successful
       Original format: .stl
       Converted to STL: False
       STL filename: uploaded_model_1730000000.stl
       STL size: 10,485,760 bytes
       G-code filename: uploaded_model_1730000000.gcode
       G-code size: 524,288 bytes
       G-code URL: http://localhost:7000/files/uploaded_model_1730000000.gcode

[TEST] GLB file: model_def456.glb
  [OK] Upload successful
       Original format: .glb
       Converted to STL: True
       STL filename: uploaded_model_1730000001.stl
       STL size: 8,388,608 bytes
       G-code filename: uploaded_model_1730000001.gcode
       G-code size: 524,288 bytes
       G-code URL: http://localhost:7000/files/uploaded_model_1730000001.gcode

============================================================
Test completed
============================================================
```

---

## 📚 관련 문서

| 문서 | 설명 |
|------|------|
| [AUTO_CONVERT_GUIDE.md](./AUTO_CONVERT_GUIDE.md) | 자동 변환 완전 가이드 |
| [README_API.md](./README_API.md) | API 빠른 시작 가이드 |
| [STL_UPLOAD_API_GUIDE.md](./STL_UPLOAD_API_GUIDE.md) | STL 업로드 완전 가이드 |
| [CLIENT_API_GUIDE.md](./CLIENT_API_GUIDE.md) | 클라이언트 개발자 가이드 |

---

## ⚙️ 기술 스택

- **FastAPI**: 웹 프레임워크
- **Trimesh**: 3D 메시 처리 및 변환
- **CuraEngine**: G-code 슬라이싱
- **Python 3.10+**: 비동기 처리

---

## 📦 의존성

```txt
fastapi==0.115.0
uvicorn[standard]==0.31.0
trimesh==4.5.3
python-multipart==0.0.9
```

**설치**:
```bash
pip install -r requirements.txt
```

---

## 💡 주요 장점

1. **투명한 사용**: 클라이언트는 파일 형식에 관계없이 동일한 API 사용
2. **자동 처리**: 파일 확장자만으로 자동 변환 여부 결정
3. **메시 수리**: 변환 과정에서 자동으로 메시 문제 수정
4. **디스크 효율**: 원본 파일은 변환 후 자동 삭제
5. **명확한 피드백**: Response에 변환 여부 명시

---

## ⚠️ 주의사항

### 1. 파일 크기
- 대용량 GLB/OBJ 파일(>100MB)은 변환 시간이 오래 걸릴 수 있음
- 메모리 부족 가능성 있음
- 사전에 외부 도구로 최적화 권장

### 2. 복잡한 모델
- 여러 객체가 있는 GLB/GLTF는 자동으로 병합됨
- 매우 복잡한 모델은 수동 확인 권장

### 3. 변환 시간
- STL: 즉시 (0초)
- GLB: 1-5초 (크기에 따라)
- OBJ: 1-5초 (크기에 따라)
- GLTF: 1-5초 (크기에 따라)

### 4. 지원하지 않는 형식
- `.fbx` - FBX 파일
- `.blend` - Blender 파일
- `.3ds` - 3DS Max 파일
- `.dae` - Collada 파일

이러한 형식은 외부 도구(Blender, MeshLab 등)로 STL 변환 후 업로드

---

## 🎉 완료!

### 구현된 기능
✅ 파일 형식 자동 감지
✅ GLB → STL 자동 변환
✅ GLTF → STL 자동 변환
✅ OBJ → STL 자동 변환
✅ 메시 자동 수리
✅ 원본 파일 자동 삭제
✅ 변환 후 즉시 슬라이싱
✅ 명확한 에러 메시지
✅ 완전한 문서화
✅ 테스트 스크립트

**모든 3D 파일 형식을 투명하게 처리합니다!** 🎊
