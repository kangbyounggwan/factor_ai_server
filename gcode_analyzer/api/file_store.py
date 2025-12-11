"""
파일 기반 분석 상태 저장소
멀티 워커 환경에서 상태를 공유하기 위한 파일 기반 저장소
"""
import os
import json
import fcntl
import time
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger("uvicorn.error")

# 저장소 디렉토리
STORE_DIR = os.getenv("GCODE_STORE_DIR", "/var/www/factor_ai_server/output/analysis_store")


def _ensure_store_dir():
    """저장소 디렉토리 생성"""
    os.makedirs(STORE_DIR, exist_ok=True)


def _get_file_path(analysis_id: str) -> str:
    """분석 ID에 대한 파일 경로 반환"""
    _ensure_store_dir()
    return os.path.join(STORE_DIR, f"{analysis_id}.json")


def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
    """
    분석 상태 조회

    Args:
        analysis_id: 분석 ID

    Returns:
        분석 데이터 딕셔너리 또는 None
    """
    file_path = _get_file_path(analysis_id)

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # 공유 잠금
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data
    except Exception as e:
        logger.error(f"[FileStore] Failed to read {analysis_id}: {e}")
        return None


def set_analysis(analysis_id: str, data: Dict[str, Any]) -> bool:
    """
    분석 상태 저장

    Args:
        analysis_id: 분석 ID
        data: 저장할 데이터

    Returns:
        성공 여부
    """
    file_path = _get_file_path(analysis_id)

    try:
        # 임시 파일에 먼저 쓰고 원자적으로 이동
        temp_path = f"{file_path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # 배타적 잠금
            try:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # 원자적 이동
        os.replace(temp_path, file_path)
        return True
    except Exception as e:
        logger.error(f"[FileStore] Failed to write {analysis_id}: {e}")
        return False


def update_analysis(analysis_id: str, updates: Dict[str, Any]) -> bool:
    """
    분석 상태 부분 업데이트

    Args:
        analysis_id: 분석 ID
        updates: 업데이트할 필드들

    Returns:
        성공 여부
    """
    data = get_analysis(analysis_id)
    if data is None:
        return False

    data.update(updates)
    data["updated_at"] = datetime.now().isoformat()
    return set_analysis(analysis_id, data)


def delete_analysis(analysis_id: str) -> bool:
    """
    분석 상태 삭제

    Args:
        analysis_id: 분석 ID

    Returns:
        성공 여부
    """
    file_path = _get_file_path(analysis_id)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        logger.error(f"[FileStore] Failed to delete {analysis_id}: {e}")
        return False


def exists(analysis_id: str) -> bool:
    """분석 ID 존재 여부 확인"""
    file_path = _get_file_path(analysis_id)
    return os.path.exists(file_path)


def list_analyses() -> list:
    """모든 분석 ID 목록 반환"""
    _ensure_store_dir()

    try:
        files = os.listdir(STORE_DIR)
        return [f.replace('.json', '') for f in files if f.endswith('.json')]
    except Exception as e:
        logger.error(f"[FileStore] Failed to list analyses: {e}")
        return []


def cleanup_old_analyses(max_age_hours: int = 24) -> int:
    """
    오래된 분석 정리

    Args:
        max_age_hours: 최대 보관 시간 (시간)

    Returns:
        삭제된 분석 수
    """
    _ensure_store_dir()
    deleted = 0
    cutoff_time = time.time() - (max_age_hours * 3600)

    try:
        for analysis_id in list_analyses():
            file_path = _get_file_path(analysis_id)
            if os.path.getmtime(file_path) < cutoff_time:
                if delete_analysis(analysis_id):
                    deleted += 1
                    logger.info(f"[FileStore] Cleaned up old analysis: {analysis_id}")
    except Exception as e:
        logger.error(f"[FileStore] Cleanup failed: {e}")

    return deleted


# 호환성을 위한 Dict-like 인터페이스
class FileBasedStore:
    """Dict처럼 사용 가능한 파일 기반 저장소"""

    def __contains__(self, analysis_id: str) -> bool:
        return exists(analysis_id)

    def __getitem__(self, analysis_id: str) -> Dict[str, Any]:
        data = get_analysis(analysis_id)
        if data is None:
            raise KeyError(analysis_id)
        return data

    def __setitem__(self, analysis_id: str, data: Dict[str, Any]):
        set_analysis(analysis_id, data)

    def __delitem__(self, analysis_id: str):
        if not delete_analysis(analysis_id):
            raise KeyError(analysis_id)

    def get(self, analysis_id: str, default=None) -> Optional[Dict[str, Any]]:
        data = get_analysis(analysis_id)
        return data if data is not None else default

    def keys(self):
        return list_analyses()


# 전역 인스턴스
gcode_analysis_store = FileBasedStore()
