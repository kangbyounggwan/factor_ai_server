"""
Supabase gcode-files 버킷에서 G-code 파일들을 다운로드하고 분석 테스트
"""
import sys
import os
import tempfile
import json
import time
from pathlib import Path

sys.path.insert(0, 'c:/Users/USER/factor_AI_python')

import os
from dotenv import load_dotenv
from supabase import create_client
from gcode_analyzer.segment_extractor import extract_segments

load_dotenv()

def get_admin_supabase_client():
    """Service Role Key를 사용하여 관리자 권한 클라이언트 생성"""
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not service_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    return create_client(url, service_key)

BUCKET_NAME = "gcode-files"

# 알려진 사용자 ID 목록
KNOWN_USER_IDS = [
    "be61c171-e84a-4652-949d-8db5f64b8b18",
    "b39f68be-b39c-4f19-846e-d0004241be78",
    "a90b65bc-afdb-43c1-9f2b-a84a22c2d8a1",
    "9b19b606-54ce-4c62-be76-66414a5fabb4",
    "635a5e0b-7fa4-4ed1-9f85-edb97bbcfe55",
    "53f3ac1c-02b4-416b-b9c9-0a6d64774f13",
    "3fc7b7e3-5ce2-4035-bfd9-f5bcf182340b",
]

def list_all_gcode_files(supabase):
    """버킷의 모든 G-code 파일 경로 수집"""
    all_files = []

    # 알려진 사용자 ID로 직접 접근
    for user_id in KNOWN_USER_IDS:
        print(f"\n[User: {user_id[:20]}...]")

        try:
            # gcode_analysis 폴더 직접 접근
            gcode_path = f"{user_id}/gcode_analysis"
            gcode_files = supabase.storage.from_(BUCKET_NAME).list(gcode_path)

            print(f"  Found {len(gcode_files)} items in gcode_analysis")

            for gcode_file in gcode_files:
                fname = gcode_file.get('name', '')
                if fname.endswith('.gcode'):
                    file_path = f"{gcode_path}/{fname}"
                    all_files.append({
                        'path': file_path,
                        'name': fname,
                        'user_id': user_id,
                        'metadata': gcode_file.get('metadata', {})
                    })
                    print(f"    + {fname}")

        except Exception as e:
            print(f"  Error: {str(e)[:80]}")

    return all_files


def download_and_analyze(supabase, file_info):
    """파일 다운로드 후 분석"""
    file_path = file_info['path']
    file_name = file_info['name']

    try:
        # 다운로드
        response = supabase.storage.from_(BUCKET_NAME).download(file_path)

        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.gcode', delete=False) as tmp:
            tmp.write(response)
            tmp_path = tmp.name

        try:
            # 분석 (parser.py에서 인코딩 폴백 처리)
            start_time = time.time()
            result = extract_segments(tmp_path)
            elapsed = time.time() - start_time

            return {
                'success': True,
                'file_name': file_name,
                'path': file_path,
                'elapsed': elapsed,
                'metadata': result['metadata'],
                'layer_count': result['metadata']['layerCount'],
                'total_extrusions': sum(len(l['extrusions']) for l in result['layers']),
                'total_travels': sum(len(l['travels']) for l in result['layers'])
            }
        except Exception as e:
            return {
                'success': False,
                'file_name': file_name,
                'path': file_path,
                'error': str(e)[:200]
            }
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        return {
            'success': False,
            'file_name': file_name,
            'path': file_path,
            'error': f'Download failed: {str(e)[:100]}'
        }


def main():
    print("=" * 70)
    print("Supabase G-code Files Analysis Test")
    print("=" * 70)

    # Supabase 관리자 클라이언트 (Service Role Key 사용)
    supabase = get_admin_supabase_client()

    # 모든 G-code 파일 목록
    print("\n[1] Listing all G-code files...")
    all_files = list_all_gcode_files(supabase)

    print(f"\n{'='*70}")
    print(f"Total G-code files found: {len(all_files)}")
    print("=" * 70)

    if not all_files:
        print("No G-code files found!")
        return

    # 분석 결과
    results = {
        'success': [],
        'failed': []
    }

    print("\n[2] Analyzing files...")
    print("-" * 70)

    for i, file_info in enumerate(all_files, 1):
        print(f"\n[{i}/{len(all_files)}] {file_info['name']}")

        result = download_and_analyze(supabase, file_info)

        if result['success']:
            results['success'].append(result)
            meta = result['metadata']
            print(f"  [OK] {meta['slicer']} | "
                  f"Layers: {meta['layerCount']} | "
                  f"Filament: {meta['totalFilament']:.0f}mm | "
                  f"Time: {result['elapsed']:.2f}s")
        else:
            results['failed'].append(result)
            print(f"  [FAIL] {result['error']}")

    # 최종 결과 요약
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files: {len(all_files)}")
    print(f"Success: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")

    if results['failed']:
        print("\n[Failed files]")
        for f in results['failed']:
            print(f"  - {f['file_name']}: {f['error']}")

    if results['success']:
        print("\n[Slicer distribution]")
        slicers = {}
        for r in results['success']:
            slicer = r['metadata']['slicer']
            slicers[slicer] = slicers.get(slicer, 0) + 1
        for slicer, count in sorted(slicers.items(), key=lambda x: -x[1]):
            print(f"  - {slicer}: {count}")

        print("\n[Stats]")
        total_layers = sum(r['layer_count'] for r in results['success'])
        total_extrusions = sum(r['total_extrusions'] for r in results['success'])
        total_travels = sum(r['total_travels'] for r in results['success'])
        print(f"  Total layers processed: {total_layers:,}")
        print(f"  Total extrusion segments: {total_extrusions:,}")
        print(f"  Total travel segments: {total_travels:,}")

    # 결과 저장
    output_path = 'c:/Users/USER/factor_AI_python/gcode_analysis_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(all_files),
            'success_count': len(results['success']),
            'failed_count': len(results['failed']),
            'success': results['success'],
            'failed': results['failed']
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
