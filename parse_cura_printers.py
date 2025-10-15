import os
import json
import re
from pathlib import Path
from supabase import create_client, Client
from typing import Dict, List, Optional

# Supabase 설정
SUPABASE_URL = "https://ecmrkjwsjkthurwljhvp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"

# Cura 정의 파일 경로
CURA_DEFINITIONS_PATH = r"C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions"


def parse_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    파일명을 파싱하여 제조사, 시리즈, 모델명을 추출합니다.
    예: creality_ender3.def.json -> {"manufacturer": "creality", "series": "ender", "model": "ender3"}
    """
    # .def.json 제거
    name = filename.replace('.def.json', '')

    # 특수 케이스 처리 (base, common 등 제외)
    if any(skip in name for skip in ['_base', '_common', 'fdmprinter', 'fdmextruder', 'custom']):
        return None

    # 언더스코어로 분리
    parts = name.split('_')

    if len(parts) < 2:
        # 제조사가 명확하지 않은 경우
        return {
            "manufacturer": "unknown",
            "series": "unknown",
            "model": name
        }

    manufacturer = parts[0]

    # 두 번째 부분을 시리즈로, 전체 이름을 모델로 사용
    series = parts[1] if len(parts) > 1 else "unknown"
    model = '_'.join(parts[1:]) if len(parts) > 1 else name

    return {
        "manufacturer": manufacturer,
        "series": series,
        "model": model
    }


def read_printer_definition(filepath: str) -> Optional[Dict]:
    """
    프린터 정의 파일을 읽어서 필요한 정보를 추출합니다.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {
                "name": data.get("name", ""),
                "version": data.get("version", 2),
                "inherits": data.get("inherits", ""),
                "metadata": data.get("metadata", {}),
                "visible": data.get("metadata", {}).get("visible", True),
                "author": data.get("metadata", {}).get("author", ""),
                "manufacturer_from_file": data.get("metadata", {}).get("manufacturer", "")
            }
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None


def parse_all_printers() -> List[Dict]:
    """
    모든 프린터 정의 파일을 파싱합니다.
    """
    printers = []
    definitions_path = Path(CURA_DEFINITIONS_PATH)

    for def_file in definitions_path.glob("*.def.json"):
        # 파일명에서 정보 추출
        parsed = parse_filename(def_file.name)
        if not parsed:
            continue

        # 파일 내용 읽기
        file_data = read_printer_definition(str(def_file))
        if not file_data:
            continue

        # 파일에서 제조사 정보가 있으면 우선 사용
        if file_data.get("manufacturer_from_file"):
            parsed["manufacturer"] = file_data["manufacturer_from_file"]

        printer_info = {
            "manufacturer": parsed["manufacturer"],
            "series": parsed["series"],
            "model": parsed["model"],
            "display_name": file_data["name"],
            "filename": def_file.name,
            "version": file_data["version"],
            "inherits": file_data["inherits"],
            "visible": file_data["visible"],
            "author": file_data["author"],
            "metadata": file_data["metadata"]
        }

        printers.append(printer_info)

    return printers


def create_supabase_table_sql():
    """
    Supabase 테이블 생성을 위한 SQL을 반환합니다.
    """
    return """
-- Cura 프린터 정의 테이블 생성
CREATE TABLE IF NOT EXISTS cura_printers (
    id BIGSERIAL PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    series TEXT NOT NULL,
    model TEXT NOT NULL,
    display_name TEXT NOT NULL,
    filename TEXT NOT NULL UNIQUE,
    version INTEGER DEFAULT 2,
    inherits TEXT,
    visible BOOLEAN DEFAULT true,
    author TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_cura_printers_manufacturer ON cura_printers(manufacturer);
CREATE INDEX IF NOT EXISTS idx_cura_printers_series ON cura_printers(series);
CREATE INDEX IF NOT EXISTS idx_cura_printers_model ON cura_printers(model);
CREATE INDEX IF NOT EXISTS idx_cura_printers_filename ON cura_printers(filename);

-- RLS (Row Level Security) 활성화
ALTER TABLE cura_printers ENABLE ROW LEVEL SECURITY;

-- 모든 사용자가 읽을 수 있도록 정책 설정
CREATE POLICY "Allow public read access" ON cura_printers
    FOR SELECT USING (true);

-- 인증된 사용자만 삽입/수정/삭제 가능하도록 설정 (필요시 수정)
CREATE POLICY "Allow authenticated insert" ON cura_printers
    FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow authenticated update" ON cura_printers
    FOR UPDATE USING (true);

CREATE POLICY "Allow authenticated delete" ON cura_printers
    FOR DELETE USING (true);
"""


def upload_to_supabase(printers: List[Dict]):
    """
    파싱된 프린터 정보를 Supabase에 업로드합니다.
    """
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        print(f"\n총 {len(printers)}개의 프린터를 업로드합니다...")

        # 배치로 업로드 (한 번에 너무 많이 업로드하면 실패할 수 있음)
        batch_size = 50
        success_count = 0
        error_count = 0

        for i in range(0, len(printers), batch_size):
            batch = printers[i:i + batch_size]
            try:
                response = supabase.table('cura_printers').upsert(
                    batch,
                    on_conflict='filename'
                ).execute()
                success_count += len(batch)
                print(f"업로드 진행중: {success_count}/{len(printers)}")
            except Exception as e:
                error_count += len(batch)
                print(f"배치 업로드 오류 (항목 {i}-{i+len(batch)}): {e}")

        print(f"\n업로드 완료!")
        print(f"성공: {success_count}개")
        print(f"실패: {error_count}개")

    except Exception as e:
        print(f"Supabase 연결 오류: {e}")


def main():
    print("=" * 60)
    print("Cura 프린터 정의 파일 파싱 및 Supabase 업로드")
    print("=" * 60)

    print("\n1. Supabase 테이블 생성 SQL:")
    print("-" * 60)
    print(create_supabase_table_sql())
    print("\n위 SQL을 Supabase SQL Editor에서 먼저 실행해주세요!")
    print("-" * 60)

    input("\n테이블 생성 후 Enter를 눌러 계속하세요...")

    print("\n2. 프린터 정의 파일 파싱 중...")
    printers = parse_all_printers()

    print(f"\n총 {len(printers)}개의 프린터를 파싱했습니다.")

    # 제조사별 통계 출력
    manufacturers = {}
    for printer in printers:
        mfr = printer['manufacturer']
        if mfr not in manufacturers:
            manufacturers[mfr] = []
        manufacturers[mfr].append(printer)

    print("\n제조사별 프린터 수:")
    for mfr in sorted(manufacturers.keys()):
        print(f"  - {mfr}: {len(manufacturers[mfr])}개")

    # 샘플 데이터 출력
    print("\n샘플 데이터 (처음 5개):")
    for i, printer in enumerate(printers[:5]):
        print(f"\n{i+1}. {printer['display_name']}")
        print(f"   제조사: {printer['manufacturer']}")
        print(f"   시리즈: {printer['series']}")
        print(f"   모델: {printer['model']}")
        print(f"   파일명: {printer['filename']}")

    # Supabase 업로드 확인
    confirm = input("\nSupabase에 업로드하시겠습니까? (y/n): ")
    if confirm.lower() == 'y':
        upload_to_supabase(printers)
    else:
        print("업로드를 취소했습니다.")

        # JSON 파일로 저장 옵션
        save_json = input("JSON 파일로 저장하시겠습니까? (y/n): ")
        if save_json.lower() == 'y':
            output_file = "cura_printers.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(printers, f, indent=2, ensure_ascii=False)
            print(f"{output_file}에 저장되었습니다.")


if __name__ == "__main__":
    main()
