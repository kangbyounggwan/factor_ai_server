# Factor AI API 클라이언트 예제 (Python)
import requests
import time
from pathlib import Path

BASE_URL = "http://localhost:7000"

class FactorAIClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip('/')

    def health_check(self):
        """서버 상태 확인"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()

    def image_to_3d(self, image_path: str, extra_meta: dict = None):
        """이미지를 3D 모델로 변환 (multipart 방식)"""
        with open(image_path, 'rb') as f:
            files = {
                'image_file': (Path(image_path).name, f, 'image/png')
            }
            data = {
                'task': 'image_to_3d',
                'json': str(extra_meta or {})
            }
            response = requests.post(
                f"{self.base_url}/v1/process/modelling",
                files=files,
                data=data,
                timeout=1200  # 20분
            )

        result = response.json()
        if result['status'] == 'error':
            raise RuntimeError(f"API Error: {result['error']}")
        return result['data']

    def text_to_3d(self, prompt: str, quality: str = "medium"):
        """텍스트로 3D 모델 생성 시작"""
        payload = {
            "task": "text_to_3d",
            "prompt": prompt,
            "model": "flux-kontext",
            "quality": quality,
            "output": {"format": "glb", "unit": "mm", "scale": 1.0},
            "printer": {"device_uuid": "test-device", "auto_slice": False, "print": False},
            "metadata": {"session_id": "test", "source": "api", "user_id": "test"}
        }
        response = requests.post(
            f"{self.base_url}/v1/process/modelling",
            json=payload
        )
        result = response.json()
        if result['status'] == 'error':
            raise RuntimeError(f"API Error: {result['error']}")
        return result['data']

    def get_modelling_status(self, task_id: str):
        """모델링 작업 상태 조회"""
        response = requests.get(f"{self.base_url}/v1/process/modelling/{task_id}")
        result = response.json()
        if result['status'] == 'error':
            raise RuntimeError(f"API Error: {result['error']}")
        return result['data']

    def wait_for_completion(self, task_id: str, poll_interval: int = 5, timeout: int = 1200):
        """작업 완료까지 대기 (폴링)"""
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task {task_id} timeout after {timeout}s")

            status_data = self.get_modelling_status(task_id)
            status = status_data.get('status', '').upper()
            progress = status_data.get('progress', 0)

            print(f"Status: {status}, Progress: {progress}%")

            if status == 'SUCCEEDED':
                return status_data
            elif status == 'FAILED':
                raise RuntimeError(f"Task {task_id} failed")

            time.sleep(poll_interval)

    def clean_model(self, task_id: str = None, glb_path: str = None):
        """Blender 후처리 (모델 정리 및 STL 변환)"""
        if not task_id and not glb_path:
            raise ValueError("Either task_id or glb_path must be provided")

        payload = {}
        if task_id:
            payload['task_id'] = task_id
        if glb_path:
            payload['glb_path'] = glb_path

        response = requests.post(
            f"{self.base_url}/v1/process/clean-model",
            json=payload,
            timeout=300  # 5분
        )
        result = response.json()
        if result['status'] == 'error':
            raise RuntimeError(f"API Error: {result['error']}")
        return result['data']

    def download_file(self, url: str, save_path: str):
        """파일 다운로드"""
        if url.startswith('/'):
            url = f"{self.base_url}{url}"

        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded: {save_path}")


# ===== 사용 예제 =====

if __name__ == "__main__":
    client = FactorAIClient()

    # 예제 1: 헬스 체크
    print("=== 헬스 체크 ===")
    health = client.health_check()
    print(health)
    print()

    # 예제 2: 이미지 → 3D 모델 (자동 완료)
    print("=== 이미지 → 3D 모델 ===")
    try:
        result = client.image_to_3d("test_image.png")
        print(f"Task ID: {result['task_id']}")
        print(f"Download URL: {result['download_url']}")

        # 파일 다운로드
        client.download_file(result['download_url'], "output_model.glb")
    except Exception as e:
        print(f"Error: {e}")
    print()

    # 예제 3: 텍스트 → 3D 모델 (폴링 필요)
    print("=== 텍스트 → 3D 모델 ===")
    try:
        result = client.text_to_3d("a cute robot")
        task_id = result['task_id']
        print(f"Task ID: {task_id}")

        # 완료까지 대기
        completed = client.wait_for_completion(task_id)
        print(f"완료! Download URL: {completed['download_url']}")

        # 파일 다운로드
        client.download_file(completed['download_url'], "robot_model.glb")
    except Exception as e:
        print(f"Error: {e}")
    print()

    # 예제 4: Blender 후처리
    print("=== Blender 후처리 ===")
    try:
        # 이전 작업의 task_id 사용
        clean_result = client.clean_model(task_id="0199e0be-35eb-754a-a02c-642c480e63de")
        print(f"Cleaned GLB: {clean_result['cleaned_glb_url']}")
        print(f"STL: {clean_result['stl_url']}")

        # 파일 다운로드
        client.download_file(clean_result['cleaned_glb_url'], "cleaned_model.glb")
        client.download_file(clean_result['stl_url'], "model.stl")
    except Exception as e:
        print(f"Error: {e}")
