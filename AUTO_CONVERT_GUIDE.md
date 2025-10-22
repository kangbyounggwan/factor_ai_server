# 자동 STL 변환 및 슬라이싱 가이드

## 🎯 개요

모든 3D 모델 파일 형식을 자동으로 STL로 변환하고 즉시 G-code로 슬라이싱합니다.

**지원 파일 형식**: STL, GLB, GLTF, OBJ

---

## ✨ 주요 기능

1. **자동 형식 감지**: 파일 확장자 자동 인식
2. **자동 STL 변환**: GLB/GLTF/OBJ → STL 자동 변환
3. **즉시 슬라이싱**: 변환된 STL을 즉시 G-code로 변환
4. **파일 정리**: 원본 파일은 삭제, STL과 G-code만 유지

---

## 📋 API 엔드포인트

### POST `/v1/process/upload-stl-and-slice`

**지원 파일 형식**:
- `.stl` - 그대로 사용
- `.glb` - STL로 자동 변환
- `.gltf` - STL로 자동 변환
- `.obj` - STL로 자동 변환

---

## 🚀 사용 예시

### 1. STL 파일 업로드 (변환 불필요)

```bash
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.stl" \
  -F 'cura_settings_json={"layer_height":"0.2"}'
```

### 2. GLB 파일 업로드 (자동 STL 변환)

```bash
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.glb" \
  -F 'cura_settings_json={"layer_height":"0.2"}'
```

### 3. OBJ 파일 업로드 (자동 STL 변환)

```bash
curl -X POST http://localhost:7000/v1/process/upload-stl-and-slice \
  -F "model_file=@model.obj" \
  -F 'cura_settings_json={"layer_height":"0.2"}'
```

---

## 💻 Python 예시

```python
import requests
import json

def upload_and_slice(model_path: str, cura_settings: dict = None):
    """
    모든 3D 모델 파일을 업로드하고 슬라이싱

    지원 형식: STL, GLB, GLTF, OBJ
    """

    # 기본 설정
    if cura_settings is None:
        cura_settings = {
            "layer_height": "0.2",
            "infill_sparse_density": "20",
            "support_enable": "true"
        }

    # 프린터 정의 (선택)
    printer_def = {
        "version": 2,
        "name": "My Printer",
        "overrides": {
            "machine_width": {"default_value": 220},
            "machine_depth": {"default_value": 220},
            "machine_height": {"default_value": 250}
        }
    }

    # 파일 업로드
    with open(model_path, 'rb') as f:
        response = requests.post(
            'http://localhost:7000/v1/process/upload-stl-and-slice',
            files={'model_file': f},
            data={
                'cura_settings_json': json.dumps(cura_settings),
                'printer_definition_json': json.dumps(printer_def)
            }
        )

    result = response.json()

    if result['status'] == 'ok':
        data = result['data']
        print(f"원본 파일: {data['original_filename']}")
        print(f"원본 형식: {data['original_format']}")
        print(f"STL 변환: {'예' if data['converted_to_stl'] else '아니오'}")
        print(f"G-code URL: {data['gcode_url']}")

        return data['gcode_url']
    else:
        raise Exception(f"슬라이싱 실패: {result['error']}")


# 사용 예시
# STL 파일
gcode_url = upload_and_slice('model.stl')

# GLB 파일 (자동 변환)
gcode_url = upload_and_slice('model.glb')

# OBJ 파일 (자동 변환)
gcode_url = upload_and_slice('model.obj')
```

---

## 📦 JavaScript/TypeScript 예시

```typescript
async function uploadAndSlice(
  file: File,
  curaSettings?: Record<string, string>
): Promise<string> {

  const formData = new FormData();
  formData.append('model_file', file);

  // 기본 설정
  const settings = curaSettings || {
    layer_height: "0.2",
    infill_sparse_density: "20"
  };

  formData.append('cura_settings_json', JSON.stringify(settings));

  const response = await fetch(
    'http://localhost:7000/v1/process/upload-stl-and-slice',
    {
      method: 'POST',
      body: formData
    }
  );

  const result = await response.json();

  if (result.status === 'ok') {
    console.log('원본 형식:', result.data.original_format);
    console.log('STL 변환:', result.data.converted_to_stl ? '예' : '아니오');
    return result.data.gcode_url;
  } else {
    throw new Error(result.error);
  }
}

// 사용 예시
const fileInput = document.getElementById('file-upload') as HTMLInputElement;

fileInput.addEventListener('change', async (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;

  // STL, GLB, OBJ 등 모든 형식 지원
  const gcodeUrl = await uploadAndSlice(file);
  console.log('G-code URL:', gcodeUrl);

  // 다운로드
  window.open(gcodeUrl, '_blank');
});
```

---

## 🔄 변환 프로세스

### STL 파일
```
STL 업로드
  ↓
변환 불필요
  ↓
즉시 슬라이싱
  ↓
G-code 생성
```

### GLB/GLTF/OBJ 파일
```
GLB/GLTF/OBJ 업로드
  ↓
Trimesh로 로드
  ↓
메시 병합 (여러 객체가 있는 경우)
  ↓
기본 수리
  - 반전 수정
  - 구멍 메우기
  - 중복 면 제거
  ↓
STL로 내보내기
  ↓
원본 파일 삭제
  ↓
슬라이싱
  ↓
G-code 생성
```

---

## 📤 Response 형식

### 성공 (STL 직접 업로드)

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

### 성공 (GLB → STL 변환)

```json
{
  "status": "ok",
  "data": {
    "original_filename": "model.glb",
    "original_format": ".glb",
    "converted_to_stl": true,
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

### 실패 (지원하지 않는 형식)

```json
{
  "status": "error",
  "error": "Unsupported file format: .fbx. Supported: .stl, .glb, .gltf, .obj"
}
```

---

## 🎨 지원 파일 형식 상세

| 형식 | 확장자 | 변환 | 설명 |
|------|--------|------|------|
| STL | `.stl` | 불필요 | 직접 슬라이싱 |
| GLB | `.glb` | 자동 | Binary glTF |
| GLTF | `.gltf` | 자동 | Text glTF |
| OBJ | `.obj` | 자동 | Wavefront OBJ |

### 미지원 형식
- `.fbx` - FBX 파일
- `.blend` - Blender 파일
- `.3ds` - 3DS Max 파일
- `.dae` - Collada 파일

*미지원 형식은 외부 도구로 STL 변환 후 업로드*

---

## ⚙️ 변환 설정

### Trimesh 변환 옵션

현재 적용되는 기본 수리:
- `fix_inversion` - 반전된 면 수정
- `fill_holes` - 구멍 메우기
- `remove_degenerate_faces` - 퇴화된 면 제거
- `remove_duplicate_faces` - 중복 면 제거
- `remove_unreferenced_vertices` - 미사용 정점 제거

---

## 🧪 테스트

### 다양한 형식 테스트

```python
import requests
import json
from pathlib import Path

def test_auto_conversion():
    """여러 파일 형식으로 테스트"""

    test_files = [
        'model.stl',
        'model.glb',
        'model.obj',
    ]

    for file_path in test_files:
        if not Path(file_path).exists():
            print(f"⏭️  Skipping {file_path} (not found)")
            continue

        print(f"\n📤 Testing: {file_path}")

        with open(file_path, 'rb') as f:
            response = requests.post(
                'http://localhost:7000/v1/process/upload-stl-and-slice',
                files={'model_file': f}
            )

        result = response.json()

        if result['status'] == 'ok':
            data = result['data']
            print(f"✅ Success!")
            print(f"   원본: {data['original_format']}")
            print(f"   변환: {data['converted_to_stl']}")
            print(f"   STL: {data['stl_bytes']} bytes")
            print(f"   G-code: {data['gcode_url']}")
        else:
            print(f"❌ Failed: {result['error']}")

test_auto_conversion()
```

---

## 💡 팁

### 1. 파일 크기 최적화

큰 GLB/OBJ 파일은 변환 시간이 오래 걸릴 수 있습니다.
- 작은 파일로 테스트 먼저 진행
- 필요시 외부 도구로 메시 최적화 후 업로드

### 2. 멀티 파트 모델

여러 객체가 있는 GLB/GLTF 파일:
- 자동으로 모든 메시 병합
- 하나의 STL 파일로 변환

### 3. 파일명 보존

원본 파일명이 유지됩니다:
- 입력: `my_model.glb`
- STL: `uploaded_my_model_1730000000.stl`
- G-code: `uploaded_my_model_1730000000.gcode`

---

## ⚠️ 주의사항

### 1. 변환 시간
- STL: 즉시 (변환 없음)
- GLB: 1-5초 (크기에 따라)
- OBJ: 1-5초 (크기에 따라)

### 2. 메모리 사용
대용량 파일 (>100MB):
- 서버 메모리 부족 가능
- 외부 도구로 사전 최적화 권장

### 3. 변환 정확도
- Trimesh 라이브러리 사용
- 대부분의 모델에서 정상 작동
- 복잡한 모델은 수동 확인 권장

---

## 🔧 문제 해결

### 변환 실패
```json
{
  "status": "error",
  "error": "Failed to convert .glb to STL: ..."
}
```

**해결 방법**:
1. 외부 도구로 STL 변환 (Blender, MeshLab 등)
2. 변환된 STL 파일 직접 업로드
3. 모델 최적화 (면 개수 줄이기)

### Trimesh 없음
```json
{
  "status": "error",
  "error": "Trimesh library not available"
}
```

**해결 방법**:
```bash
pip install trimesh
```

---

## 📊 지원 현황

| 기능 | 상태 |
|------|------|
| STL 업로드 | ✅ 지원 |
| GLB → STL | ✅ 자동 변환 |
| GLTF → STL | ✅ 자동 변환 |
| OBJ → STL | ✅ 자동 변환 |
| 자동 슬라이싱 | ✅ 지원 |
| 파일 자동 삭제 | ✅ 지원 |

---

**모든 3D 파일 형식을 자동으로 처리합니다!** 🎉
