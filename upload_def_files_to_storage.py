import os
import sys
import io
from pathlib import Path
from supabase import create_client, Client

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Supabase 설정
SUPABASE_URL = "https://ecmrkjwsjkthurwljhvp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"

# Cura 정의 파일 경로
CURA_DEFINITIONS_PATH = r"C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions"

# Storage 버킷 이름
BUCKET_NAME = "printer-definitions"


def check_bucket_exists(supabase: Client) -> bool:
    """
    printer-definitions 버킷이 존재하는지 확인합니다.
    """
    try:
        buckets = supabase.storage.list_buckets()
        print(f"   사용 가능한 버킷 목록:")
        for bucket in buckets:
            print(f"     - {bucket.get('name', bucket.get('id', 'unknown'))}")
        bucket_names = [bucket.get('name', bucket.get('id', '')) for bucket in buckets]
        return BUCKET_NAME in bucket_names
    except Exception as e:
        print(f"✗ 버킷 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def upload_def_files(supabase: Client, definitions_path: str):
    """
    모든 .def.json 파일을 Supabase Storage에 업로드합니다.
    """
    definitions_path = Path(definitions_path)

    if not definitions_path.exists():
        print(f"✗ 경로를 찾을 수 없습니다: {definitions_path}")
        return

    # 모든 .def.json 파일 찾기
    def_files = list(definitions_path.glob("*.def.json"))

    if not def_files:
        print(f"✗ .def.json 파일을 찾을 수 없습니다: {definitions_path}")
        return

    print(f"\n총 {len(def_files)}개의 DEF 파일을 찾았습니다.")

    success_count = 0
    error_count = 0
    skipped_count = 0
    errors = []

    for i, def_file in enumerate(def_files, 1):
        filename = def_file.name
        storage_path = f"definitions/{filename}"

        try:
            # 파일 읽기
            with open(def_file, 'rb') as f:
                file_content = f.read()

            # Supabase Storage에 업로드
            try:
                response = supabase.storage.from_(BUCKET_NAME).upload(
                    storage_path,
                    file_content,
                    {
                        "content-type": "application/json",
                        "upsert": "true"  # 이미 존재하면 덮어쓰기
                    }
                )
                success_count += 1
                if i % 50 == 0 or i == len(def_files):
                    print(f"✓ 업로드 진행: {i}/{len(def_files)} ({int(i/len(def_files)*100)}%)")
            except Exception as upload_error:
                # 이미 존재하는 파일인 경우 스킵
                if 'already exists' in str(upload_error).lower() or 'duplicate' in str(upload_error).lower():
                    skipped_count += 1
                    if i % 50 == 0:
                        print(f"⊘ 이미 존재: {i}/{len(def_files)}")
                else:
                    error_count += 1
                    error_msg = f"{filename}: {str(upload_error)[:100]}"
                    errors.append(error_msg)
                    if error_count <= 5:  # 처음 5개 오류만 출력
                        print(f"✗ {error_msg}")

        except Exception as e:
            error_count += 1
            error_msg = f"{filename} (읽기 오류): {str(e)[:100]}"
            errors.append(error_msg)
            if error_count <= 5:
                print(f"✗ {error_msg}")

    print(f"\n{'='*60}")
    print(f"업로드 완료!")
    print(f"✓ 성공: {success_count}개")
    if skipped_count > 0:
        print(f"⊘ 스킵 (이미 존재): {skipped_count}개")
    if error_count > 0:
        print(f"✗ 실패: {error_count}개")
        if errors:
            print(f"\n오류 목록 (최대 5개):")
            for err in errors[:5]:
                print(f"  - {err}")
    print(f"{'='*60}")

    return success_count, skipped_count, error_count


def update_database_with_urls(supabase: Client):
    """
    업로드된 파일의 URL을 데이터베이스에 업데이트합니다.
    """
    print(f"\n데이터베이스 URL 업데이트 중...")

    try:
        # 모든 프린터 조회
        response = supabase.table('manufacturing_printers').select('id, filename').execute()
        printers = response.data

        print(f"✓ {len(printers)}개의 프린터 레코드를 찾았습니다.")

        success_count = 0
        error_count = 0

        for printer in printers:
            printer_id = printer['id']
            filename = printer['filename']
            storage_path = f"definitions/{filename}"

            try:
                # Public URL 생성
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{storage_path}"

                # 데이터베이스 업데이트
                supabase.table('manufacturing_printers').update({
                    'def_file_url': public_url,
                    'def_file_path': storage_path
                }).eq('id', printer_id).execute()

                success_count += 1

                if success_count % 50 == 0:
                    print(f"✓ URL 업데이트 진행: {success_count}/{len(printers)} ({int(success_count/len(printers)*100)}%)")

            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"✗ URL 업데이트 오류 ({filename}): {str(e)[:100]}")

        print(f"\n{'='*60}")
        print(f"URL 업데이트 완료!")
        print(f"✓ 성공: {success_count}개")
        if error_count > 0:
            print(f"✗ 실패: {error_count}개")
        print(f"{'='*60}")

    except Exception as e:
        print(f"✗ 데이터베이스 조회 오류: {e}")


def main():
    print("=" * 80)
    print("Cura DEF 파일 → Supabase Storage 업로드")
    print("=" * 80)

    # Supabase 연결
    print("\n1. Supabase 연결 중...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Supabase 연결 성공!")
    except Exception as e:
        print(f"✗ Supabase 연결 실패: {e}")
        return

    # 버킷 확인
    print(f"\n2. '{BUCKET_NAME}' 버킷 확인 중...")
    bucket_exists = check_bucket_exists(supabase)
    if not bucket_exists:
        print(f"⚠ 버킷 목록 조회 실패 (권한 문제일 수 있음)")
        print(f"   '{BUCKET_NAME}' 버킷이 존재한다고 가정하고 계속 진행합니다...")
    else:
        print(f"✓ '{BUCKET_NAME}' 버킷이 존재합니다!")

    # 기존 파일 목록 확인
    print(f"\n3. 기존 업로드된 파일 확인 중...")
    try:
        files = supabase.storage.from_(BUCKET_NAME).list('definitions')
        print(f"✓ 현재 {len(files)}개의 파일이 업로드되어 있습니다.")
    except Exception as e:
        print(f"⚠ 파일 목록 조회 오류 (폴더가 비어있을 수 있음): {e}")

    # DEF 파일 업로드
    print(f"\n4. DEF 파일 업로드")
    print("=" * 80)
    success, skipped, errors = upload_def_files(supabase, CURA_DEFINITIONS_PATH)

    # 데이터베이스 URL 업데이트
    if success > 0 or skipped > 0:
        print(f"\n5. 데이터베이스 URL 업데이트")
        print("=" * 80)
        update_database_with_urls(supabase)

    print(f"\n{'='*80}")
    print("모든 작업 완료!")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
