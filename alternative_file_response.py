# 대안: 파일을 직접 응답으로 반환하는 엔드포인트

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os

app = FastAPI()

@app.get("/v1/download/{task_id}")
async def download_model(task_id: str):
    """
    task_id로 생성된 GLB 파일을 직접 다운로드
    """
    output_dir = os.getenv("OUTPUT_DIR", "./output")

    # task_id에 해당하는 파일 찾기
    candidates = [
        os.path.join(output_dir, f"model_{task_id}.glb"),
        os.path.join(output_dir, f"refined_{task_id}.glb"),
        os.path.join(output_dir, f"preview_{task_id}.glb"),
    ]

    file_path = None
    for candidate in candidates:
        if os.path.exists(candidate):
            file_path = candidate
            break

    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    # 파일을 직접 응답으로 반환
    return FileResponse(
        file_path,
        media_type="model/gltf-binary",
        filename=os.path.basename(file_path),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600"
        }
    )


# 클라이언트 사용 예시
"""
// 1. 모델 생성 요청
const response = await fetch('/v1/process/modelling', {
  method: 'POST',
  body: formData
});
const result = await response.json();
const taskId = result.data.task_id;

// 2. 파일 다운로드 (별도 요청)
const fileUrl = `/v1/download/${taskId}`;
const blob = await fetch(fileUrl).then(r => r.blob());
const blobUrl = URL.createObjectURL(blob);

// 3. Three.js 로드
loader.load(blobUrl, (gltf) => {
  scene.add(gltf.scene);
  URL.revokeObjectURL(blobUrl);
});
"""
