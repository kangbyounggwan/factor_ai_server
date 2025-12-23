"""
Stringing 문제 진단 테스트
- LLM을 통한 문제 분석
- 컨텍스트 기반 Brave 이미지 검색 (augmented_query + 대화 히스토리 활용)
- 결과를 JSON 파일로 저장
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

import requests
from dotenv import load_dotenv

# UTF-8 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# gcode_analyzer 모듈 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gcode_analyzer.troubleshoot.solution_generator import SolutionGenerator
from gcode_analyzer.troubleshoot.models import (
    ProblemType, ImageAnalysisResult, SearchResult, Reference
)
from gcode_analyzer.troubleshoot.brave_image_searcher import BraveImageSearcher


class LegacyBraveImageSearcher:
    """Brave 이미지 검색 클래스"""

    def __init__(self):
        self.api_key = os.getenv('BRAVE_API_KEY')
        self.api_base = os.getenv('BRAVE_SEARCH_API_BASE', 'https://api.search.brave.com/res/v1')

    def search_images(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        이미지 검색 수행

        Args:
            query: 검색어
            count: 검색 결과 수 (최대 10)

        Returns:
            이미지 검색 결과 리스트
        """
        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': self.api_key
        }

        url = f'{self.api_base}/images/search'
        params = {
            'q': query,
            'count': min(count, 10),
            'safesearch': 'off'
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])

                # 결과 정리
                images = []
                for img in results:
                    images.append({
                        'title': img.get('title', ''),
                        'thumbnail_url': img.get('thumbnail', {}).get('src', ''),
                        'source_url': img.get('url', ''),
                        'page_url': img.get('page_url', ''),
                        'width': img.get('thumbnail', {}).get('width', 0),
                        'height': img.get('thumbnail', {}).get('height', 0),
                    })
                return images
            else:
                print(f'[ERROR] Brave API error: {response.status_code} - {response.text}')
                return []

        except Exception as e:
            print(f'[ERROR] Image search failed: {e}')
            return []

    def download_images(self, images: List[Dict[str, Any]], save_dir: str) -> List[Dict[str, Any]]:
        """
        이미지를 로컬에 다운로드

        Args:
            images: 이미지 정보 리스트
            save_dir: 저장 디렉토리

        Returns:
            다운로드된 이미지 정보 (로컬 경로 포함)
        """
        os.makedirs(save_dir, exist_ok=True)
        downloaded = []

        for i, img in enumerate(images, 1):
            thumbnail_url = img.get('thumbnail_url', '')
            if not thumbnail_url:
                continue

            try:
                # 파일 확장자 추출
                ext = '.jpg'  # 기본 확장자
                if '.png' in thumbnail_url.lower():
                    ext = '.png'
                elif '.gif' in thumbnail_url.lower():
                    ext = '.gif'
                elif '.webp' in thumbnail_url.lower():
                    ext = '.webp'

                # 파일명 생성 (안전한 파일명)
                safe_title = "".join(c for c in img.get('title', '')[:30] if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{i:02d}_{safe_title}{ext}" if safe_title else f"{i:02d}_image{ext}"
                filepath = os.path.join(save_dir, filename)

                # 이미지 다운로드
                response = requests.get(thumbnail_url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })

                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    # 다운로드 정보 추가
                    img_info = img.copy()
                    img_info['local_path'] = filepath
                    img_info['file_size'] = len(response.content)
                    downloaded.append(img_info)
                    print(f"  [OK] {i}. {filename} ({len(response.content) / 1024:.1f} KB)")
                else:
                    print(f"  [FAIL] {i}. HTTP {response.status_code}")

            except Exception as e:
                print(f"  [FAIL] {i}. {str(e)[:50]}")

        return downloaded


async def run_stringing_diagnosis():
    """스트링 문제 진단 테스트 실행"""

    print("=" * 60)
    print("3D 프린터 Stringing 문제 진단 테스트")
    print("=" * 60)

    # 테스트 케이스 정의
    symptom_text = "출력중 실이 생기는 문제가 있어요. 노즐이 이동할 때마다 가는 실이 늘어지고 출력물에 거미줄 같은 것이 생겨요."

    manufacturer = "Creality"
    model = "Ender 3 V2"
    filament_type = "PLA"

    print(f"\n[증상] {symptom_text}")
    print(f"[프린터] {manufacturer} {model}")
    print(f"[필라멘트] {filament_type}")

    # 1. LLM 솔루션 생성
    print("\n" + "-" * 40)
    print("[1/2] LLM 솔루션 생성 중...")
    print("-" * 40)

    generator = SolutionGenerator(language="ko")

    # 이미지 분석 결과 시뮬레이션 (실제로는 이미지 분석 모듈 사용)
    image_analysis = ImageAnalysisResult(
        detected_problems=[ProblemType.STRINGING],
        confidence_scores={"stringing": 0.95},
        description="노즐 이동 시 가는 필라멘트 실이 늘어지는 스트링 현상이 관찰됩니다.",
        visual_evidence=["가는 실 형태의 필라멘트", "거미줄 패턴", "이동 경로에 잔여물"],
        augmented_query="3D printer stringing oozing retraction settings PLA"
    )

    # 검색 결과 시뮬레이션
    search_results = [
        SearchResult(
            query="3D printer stringing solution",
            results=[
                Reference(
                    title="How to Fix Stringing in 3D Printing",
                    url="https://all3dp.com/2/3d-print-stringing-easy-ways-to-prevent-it/",
                    source="all3dp",
                    relevance=0.95,
                    snippet="리트랙션 거리와 속도 조정이 가장 효과적입니다."
                ),
                Reference(
                    title="Retraction Settings Guide",
                    url="https://www.simplify3d.com/resources/articles/retraction/",
                    source="simplify3d",
                    relevance=0.90,
                    snippet="Direct Drive는 1-2mm, Bowden은 4-7mm 리트랙션 권장"
                )
            ]
        )
    ]

    try:
        solution_result = await generator.generate_solution(
            manufacturer=manufacturer,
            model=model,
            symptom_text=symptom_text,
            image_analysis=image_analysis,
            search_results=search_results,
            filament_type=filament_type
        )

        print("\n[LLM 분석 결과]")

        # Verdict
        if solution_result.get("verdict"):
            verdict = solution_result["verdict"]
            print(f"\n>>> {verdict.headline}")
            print(f"    {verdict.reason}")

        # Problem
        problem = solution_result.get("problem")
        if problem:
            print(f"\n[문제 유형] {problem.type.value}")
            print(f"[확신도] {problem.confidence * 100:.0f}%")
            print(f"[설명] {problem.description}")

        # Solutions
        solutions = solution_result.get("solutions", [])
        print(f"\n[해결책] {len(solutions)}개 발견")
        for sol in solutions[:3]:
            print(f"\n  {sol.priority}. {sol.title} (난이도: {sol.difficulty.value})")
            for i, step in enumerate(sol.steps[:5], 1):
                print(f"     {i}. {step}")

        # Expert Opinion
        expert = solution_result.get("expert_opinion")
        if expert:
            print(f"\n[전문가 의견] {expert.summary[:200]}...")

    except Exception as e:
        print(f"[ERROR] LLM 분석 실패: {e}")
        solution_result = {"error": str(e)}

    # 2. 컨텍스트 기반 Brave 이미지 검색
    print("\n" + "-" * 40)
    print("[2/3] 컨텍스트 기반 이미지 검색 중...")
    print("-" * 40)

    # 대화 히스토리 시뮬레이션 (실제로는 채팅에서 전달됨)
    conversation_history = [
        {"role": "user", "content": "출력중에 실이 생겨요"},
        {"role": "assistant", "content": "스트링 현상으로 보입니다. 노즐 온도와 리트랙션 설정을 확인해보세요."},
        {"role": "user", "content": symptom_text}
    ]

    # 새로운 컨텍스트 기반 이미지 검색기 사용
    searcher = BraveImageSearcher()

    # LLM이 이미지 분석 + 대화 컨텍스트를 활용하여 최적의 검색 쿼리 생성
    print("\n[쿼리 생성] LLM이 컨텍스트 기반 검색 쿼리 생성 중...")
    search_query = await searcher.generate_search_query(
        problem_type=ProblemType.STRINGING,
        image_analysis=image_analysis,
        symptom_text=symptom_text,
        conversation_history=conversation_history
    )
    print(f"[생성된 쿼리] {search_query}")

    # 이미지 검색 실행
    print(f"\n[검색 실행] Brave API로 이미지 검색 중...")
    unique_images = searcher.search_images(search_query, count=10)

    print(f"\n[이미지 검색 결과] 총 {len(unique_images)}개")
    for i, img in enumerate(unique_images, 1):
        print(f"  {i}. {img['title'][:50]}...")
        print(f"     URL: {img['source_url'][:60]}...")

    # 3. 이미지 다운로드
    print("\n" + "-" * 40)
    print("[3/4] 이미지 로컬 다운로드 중...")
    print("-" * 40)

    # 이미지 저장 디렉토리 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    image_save_dir = os.path.join(os.path.dirname(__file__), "output", f"stringing_images_{timestamp}")

    downloaded_images = searcher.download_images(unique_images, image_save_dir)
    print(f"\n[다운로드 완료] {len(downloaded_images)}/{len(unique_images)}개 이미지 저장")
    print(f"[저장 경로] {image_save_dir}")

    # 4. 결과 저장
    print("\n" + "-" * 40)
    print("[저장] 결과를 JSON 파일로 저장 중...")
    print("-" * 40)

    # 결과 구조화
    result = {
        "test_info": {
            "test_name": "Stringing 문제 진단 테스트",
            "timestamp": datetime.now().isoformat(),
            "symptom_text": symptom_text,
            "printer": {
                "manufacturer": manufacturer,
                "model": model
            },
            "filament_type": filament_type
        },
        "llm_analysis": {
            "verdict": {
                "action": solution_result.get("verdict").action.value if solution_result.get("verdict") else None,
                "headline": solution_result.get("verdict").headline if solution_result.get("verdict") else None,
                "reason": solution_result.get("verdict").reason if solution_result.get("verdict") else None,
            } if solution_result.get("verdict") else None,
            "problem": {
                "type": solution_result.get("problem").type.value if solution_result.get("problem") else None,
                "confidence": solution_result.get("problem").confidence if solution_result.get("problem") else None,
                "description": solution_result.get("problem").description if solution_result.get("problem") else None,
            } if solution_result.get("problem") else None,
            "solutions": [
                {
                    "priority": sol.priority,
                    "title": sol.title,
                    "steps": sol.steps,
                    "difficulty": sol.difficulty.value,
                    "estimated_time": sol.estimated_time,
                    "tools_needed": sol.tools_needed,
                    "warnings": sol.warnings
                }
                for sol in solution_result.get("solutions", [])
            ],
            "expert_opinion": {
                "summary": solution_result.get("expert_opinion").summary if solution_result.get("expert_opinion") else None,
                "prevention_tips": solution_result.get("expert_opinion").prevention_tips if solution_result.get("expert_opinion") else [],
                "when_to_seek_help": solution_result.get("expert_opinion").when_to_seek_help if solution_result.get("expert_opinion") else None,
            } if solution_result.get("expert_opinion") else None
        },
        "image_search": {
            "generated_query": search_query,  # LLM이 컨텍스트 기반으로 생성한 쿼리
            "total_count": len(unique_images),
            "downloaded_count": len(downloaded_images),
            "image_save_dir": image_save_dir,
            "images": downloaded_images  # 다운로드된 이미지 정보 (로컬 경로 포함)
        }
    }

    # 파일 저장
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"stringing_diagnosis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 결과 저장 완료: {output_file}")

    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(run_stringing_diagnosis())
