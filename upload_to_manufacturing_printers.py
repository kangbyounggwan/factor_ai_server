import json
import sys
import io
from supabase import create_client, Client
from typing import Dict, List

# UTF-8 출력 설정 (Windows 한글 문제 해결)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Supabase 설정
SUPABASE_URL = "https://ecmrkjwsjkthurwljhvp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"


def transform_to_manufacturing_printer(cura_printer: Dict) -> Dict:
    """
    cura_printers 형식을 manufacturing_printers 테이블 형식으로 변환합니다.
    """
    metadata = cura_printer.get('metadata', {})

    # Build volume 추출
    build_volume = None
    if 'machine_width' in metadata:
        build_volume = {
            'x': metadata.get('machine_width'),
            'y': metadata.get('machine_depth'),
            'z': metadata.get('machine_height')
        }

    # Extruder count 추출
    extruder_count = 1
    if 'machine_extruder_trains' in metadata:
        extruder_count = len(metadata['machine_extruder_trains'])

    # File formats 추출
    file_formats = []
    if 'file_formats' in metadata:
        formats_str = metadata['file_formats']
        if isinstance(formats_str, str):
            file_formats = [f.strip() for f in formats_str.split(';')]
        elif isinstance(formats_str, list):
            file_formats = formats_str

    # Heated bed 여부
    heated_bed = metadata.get('has_heated_bed', True)

    # USB/Network connection 지원 여부
    supports_usb = metadata.get('supports_usb_connection', False)
    supports_network = metadata.get('supports_network_connection', False)

    # Material flow sensor 지원 여부
    supports_material_flow = metadata.get('has_material_flow_sensor', False)

    # Category 추정
    category = 'consumer'
    manufacturer_lower = cura_printer.get('manufacturer', '').lower()
    if any(word in manufacturer_lower for word in ['ultimaker', 'stratasys', 'markforged', '3d systems']):
        category = 'professional'

    # Nozzle diameter
    nozzle_diameter = metadata.get('machine_nozzle_size', 0.4)
    if isinstance(nozzle_diameter, (int, float)):
        nozzle_diameter = float(nozzle_diameter)
    else:
        nozzle_diameter = 0.4

    return {
        'manufacturer': cura_printer.get('manufacturer', 'Unknown'),
        'series': cura_printer.get('series', 'unknown'),
        'model': cura_printer.get('model', ''),
        'display_name': cura_printer.get('display_name', ''),
        'filename': cura_printer.get('filename', ''),
        'version': cura_printer.get('version', 2),
        'inherits': cura_printer.get('inherits', ''),
        'visible': cura_printer.get('visible', True),
        'author': cura_printer.get('author', ''),
        'metadata': metadata,
        'build_volume': build_volume,
        'extruder_count': extruder_count,
        'heated_bed': heated_bed,
        'file_formats': file_formats if file_formats else None,
        'technology': 'FDM',
        'nozzle_diameter': nozzle_diameter,
        'supports_usb_connection': supports_usb,
        'supports_network_connection': supports_network,
        'supports_material_flow_sensor': supports_material_flow,
        'category': category,
        'usage_count': 0
    }


def upload_to_supabase(printers: List[Dict]):
    """
    변환된 프린터 정보를 Supabase manufacturing_printers 테이블에 업로드합니다.
    """
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        print(f"\n총 {len(printers)}개의 프린터를 manufacturing_printers 테이블에 업로드합니다...")

        # 테이블 존재 확인
        try:
            test_response = supabase.table('manufacturing_printers').select('id').limit(1).execute()
            print("✓ manufacturing_printers 테이블 연결 성공!")
        except Exception as e:
            print(f"✗ manufacturing_printers 테이블 연결 실패: {e}")
            return

        # 배치로 업로드
        batch_size = 50
        success_count = 0
        error_count = 0
        errors = []

        for i in range(0, len(printers), batch_size):
            batch = printers[i:i + batch_size]
            try:
                response = supabase.table('manufacturing_printers').upsert(
                    batch,
                    on_conflict='filename'
                ).execute()
                success_count += len(batch)
                print(f"✓ 업로드 진행: {success_count}/{len(printers)} ({int(success_count/len(printers)*100)}%)")
            except Exception as e:
                error_count += len(batch)
                error_msg = f"배치 {i}-{i+len(batch)}: {str(e)[:100]}"
                errors.append(error_msg)
                print(f"✗ {error_msg}")

                # 첫 번째 배치 오류 시 상세 정보
                if i == 0:
                    print(f"  첫 번째 항목 샘플:")
                    print(f"  {json.dumps(batch[0], indent=2, ensure_ascii=False)[:500]}")

        print(f"\n{'='*60}")
        print(f"업로드 완료!")
        print(f"✓ 성공: {success_count}개")
        if error_count > 0:
            print(f"✗ 실패: {error_count}개")
            print(f"\n오류 목록:")
            for err in errors[:5]:  # 처음 5개만 표시
                print(f"  - {err}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"Supabase 연결 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("=" * 80)
    print("Cura 프린터 → manufacturing_printers 테이블 업로드")
    print("=" * 80)

    # 1. cura_printers.json 읽기
    print("\n1. cura_printers.json 파일 읽기...")
    try:
        with open("cura_printers.json", 'r', encoding='utf-8') as f:
            cura_printers = json.load(f)
        print(f"✓ {len(cura_printers)}개의 프린터 데이터를 읽었습니다.")
    except Exception as e:
        print(f"✗ cura_printers.json 파일을 찾을 수 없습니다: {e}")
        print("먼저 parse_cura_printers.py를 실행해주세요.")
        return

    # 2. manufacturing_printers 형식으로 변환
    print("\n2. manufacturing_printers 형식으로 변환 중...")
    manufacturing_printers = []
    for cp in cura_printers:
        try:
            mp = transform_to_manufacturing_printer(cp)
            manufacturing_printers.append(mp)
        except Exception as e:
            print(f"✗ 변환 실패 ({cp.get('filename', 'unknown')}): {e}")

    print(f"✓ {len(manufacturing_printers)}개의 프린터를 변환했습니다.")

    # 샘플 출력
    print("\n샘플 데이터 (처음 3개):")
    for i, printer in enumerate(manufacturing_printers[:3]):
        print(f"\n  {i+1}. {printer['display_name']}")
        print(f"     제조사: {printer['manufacturer']}")
        print(f"     모델: {printer['model']}")
        print(f"     출력 부피: {printer['build_volume']}")
        print(f"     익스트루더: {printer['extruder_count']}개")

    # 변환된 데이터를 JSON으로 저장
    output_file = "manufacturing_printers.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(manufacturing_printers, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 변환된 데이터가 '{output_file}'에 저장되었습니다.")

    # 3. Supabase 업로드
    print("\n" + "=" * 80)
    print("3. Supabase에 데이터 업로드")
    print("=" * 80)
    upload_to_supabase(manufacturing_printers)


if __name__ == "__main__":
    main()
