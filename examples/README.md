# Factor AI API - 클라이언트 예제

이 디렉토리에는 Factor AI API를 사용하는 클라이언트 예제 코드가 포함되어 있습니다.

## 파일 목록

### 1. `client_example.py` (Python)
Python으로 작성된 클라이언트 예제입니다.

**실행 방법:**
```bash
pip install requests
python client_example.py
```

### 2. `client_example.js` (Node.js)
Node.js로 작성된 클라이언트 예제입니다.

**실행 방법:**
```bash
npm install node-fetch@2 form-data
node client_example.js
```

### 3. `client_example.html` (웹 브라우저)
웹 브라우저에서 바로 실행할 수 있는 예제입니다.

**실행 방법:**
1. 브라우저에서 `client_example.html` 파일을 엽니다
2. 서버가 `http://localhost:7000`에서 실행 중이어야 합니다

## 주요 기능

모든 예제는 다음 기능을 포함합니다:

1. **헬스 체크**: 서버 상태 확인
2. **Image-to-3D**: 이미지를 3D 모델로 변환
3. **Text-to-3D**: 텍스트 설명으로 3D 모델 생성
4. **Blender 후처리**: 모델 정리 및 STL 변환

## 빠른 시작

### Python 예제
```python
from client_example import FactorAIClient

client = FactorAIClient()

# 이미지를 3D로 변환
result = client.image_to_3d("my_image.png")
print(f"Download: {result['download_url']}")

# 파일 다운로드
client.download_file(result['download_url'], "output.glb")
```

### JavaScript 예제
```javascript
const FactorAIClient = require('./client_example.js');

const client = new FactorAIClient();

// 이미지를 3D로 변환
const result = await client.imageToThreeD('my_image.png');
console.log('Download:', result.download_url);

// 파일 다운로드
await client.downloadFile(result.download_url, 'output.glb');
```

### 웹 브라우저 예제
1. `client_example.html`을 브라우저에서 엽니다
2. 이미지 파일을 선택합니다
3. "3D 모델 생성" 버튼을 클릭합니다
4. 완료되면 다운로드 링크가 표시됩니다

## API 응답 형식

모든 API 응답은 다음 형식을 따릅니다:

**성공:**
```json
{
  "status": "ok",
  "data": { ... },
  "error": null
}
```

**실패:**
```json
{
  "status": "error",
  "data": null,
  "error": "에러 메시지"
}
```

## 주요 응답 필드

### Image-to-3D 완료 응답
```json
{
  "status": "ok",
  "data": {
    "task_id": "0199e0be-35eb-754a-a02c-642c480e63de",
    "result_glb_url": "https://assets.meshy.ai/...",
    "download_url": "/files/model_xxx.glb",
    "local_path": "C:\\...\\output\\model_xxx.glb"
  }
}
```

### Blender 후처리 응답
```json
{
  "status": "ok",
  "data": {
    "task_id": "0199e0be-35eb-754a-a02c-642c480e63de",
    "cleaned_glb_url": "/files/model_cleaned_xxx.glb",
    "stl_url": "/files/model_cleaned_xxx.stl",
    "cleaned_glb_path": "C:\\...\\blender_out\\model_cleaned_xxx.glb",
    "stl_path": "C:\\...\\blender_out\\model_cleaned_xxx.stl"
  }
}
```

## 참고 사항

1. **Image-to-3D**는 자동으로 완료되어 반환됩니다 (최대 20분 소요)
2. **Text-to-3D**는 task_id만 즉시 반환되며, 클라이언트에서 폴링 필요
3. **Blender 후처리**는 Blender가 설치되어 있어야 사용 가능
4. 파일 다운로드는 `/files/` 경로를 통해 가능

## 에러 처리

모든 예제는 에러 처리를 포함합니다:

- **400**: 잘못된 요청
- **404**: 파일을 찾을 수 없음
- **502**: Meshy API 에러
- **503**: Blender 사용 불가
- **504**: 타임아웃

## 추가 정보

전체 API 문서는 `API_DOCUMENTATION.md` 파일을 참조하세요.
