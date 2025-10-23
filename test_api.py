"""
API 테스트 스크립트

printer_name을 사용하여 G-code 생성 테스트
"""

import requests
import json
import os


def test_upload_and_slice(
    stl_file_path: str,
    printer_name: str,
    cura_settings: dict = None,
    server_url: str = "http://localhost:7000"
):
    """
    STL 파일 업로드 및 슬라이싱 테스트

    Args:
        stl_file_path: STL 파일 경로
        printer_name: 프린터 이름 (예: "elegoo_neptune_x")
        cura_settings: Cura 설정 dict (선택)
        server_url: 서버 URL
    """

    print("="*80)
    print("API Test: upload-stl-and-slice")
    print("="*80)

    # 파일 존재 확인
    if not os.path.exists(stl_file_path):
        print(f"[ERROR] STL file not found: {stl_file_path}")
        return None

    print(f"\n[INFO] Test Parameters:")
    print(f"  - STL file: {stl_file_path}")
    print(f"  - Printer name: {printer_name}")
    print(f"  - Cura settings: {cura_settings}")
    print(f"  - Server URL: {server_url}")

    # API 요청 준비
    endpoint = f"{server_url}/v1/process/upload-stl-and-slice"

    # Form-data 구성
    with open(stl_file_path, 'rb') as f:
        files = {
            'model_file': (os.path.basename(stl_file_path), f, 'application/octet-stream')
        }

        data = {
            'printer_name': printer_name
        }

        # Cura 설정 추가 (있으면)
        if cura_settings:
            data['cura_settings_json'] = json.dumps(cura_settings)

        print(f"\n[INFO] Sending POST request to {endpoint}")
        print(f"[INFO] Request data: {data}")

        try:
            # API 요청
            response = requests.post(
                endpoint,
                files=files,
                data=data,
                timeout=120  # 2분 타임아웃
            )

            print(f"\n[INFO] Response status: {response.status_code}")

            # 응답 처리
            if response.status_code == 200:
                result = response.json()

                if result.get('status') == 'ok':
                    data = result['data']

                    print("\n" + "="*80)
                    print("[SUCCESS] G-code generated successfully!")
                    print("="*80)
                    print(f"\n[Response Data]")
                    print(f"  Original file: {data['original_filename']}")
                    print(f"  Original format: {data['original_format']}")
                    print(f"  Converted to STL: {data['converted_to_stl']}")
                    print(f"  STL file: {data['stl_filename']}")
                    print(f"  STL size: {data['file_size']['stl_bytes']:,} bytes")
                    print(f"  G-code file: {data['gcode_filename']}")
                    print(f"  G-code size: {data['file_size']['gcode_bytes']:,} bytes")
                    print(f"  G-code URL: {data['gcode_url']}")
                    print(f"  Printer name: {data.get('printer_name', 'N/A')}")
                    print(f"  Printer source: {data.get('printer_source', 'N/A')}")

                    # G-code 다운로드 테스트
                    print(f"\n[INFO] Testing G-code download...")
                    gcode_url = data['gcode_url']
                    gcode_response = requests.get(gcode_url, timeout=10)

                    if gcode_response.status_code == 200:
                        gcode_content = gcode_response.text
                        print(f"[SUCCESS] G-code downloaded: {len(gcode_content):,} characters")
                        print(f"\n[G-code Preview (first 500 chars)]:")
                        print(gcode_content[:500])
                        print("...")

                        # 로컬에 저장 (선택)
                        output_gcode = f"./test_output_{printer_name}.gcode"
                        with open(output_gcode, 'w') as f:
                            f.write(gcode_content)
                        print(f"\n[INFO] G-code saved to: {output_gcode}")

                    else:
                        print(f"[WARNING] Failed to download G-code: {gcode_response.status_code}")

                    return result

                else:
                    print(f"\n[FAIL] API returned error status")
                    print(f"Error: {result.get('error', 'Unknown error')}")
                    return None

            else:
                print(f"\n[FAIL] HTTP {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return None

        except requests.Timeout:
            print(f"\n[ERROR] Request timeout (>120s)")
            return None
        except requests.ConnectionError:
            print(f"\n[ERROR] Connection failed. Is the server running?")
            print(f"Try: uvicorn main:app --reload --port 7000")
            return None
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {str(e)}")
            return None


def test_multiple_printers():
    """여러 프린터로 테스트"""

    # 테스트용 STL 파일
    stl_file = "./output/test_cube_20mm.stl"

    # 테스트할 프린터 목록 (CSV에서 가져온 실제 프린터)
    printers = [
        "elegoo_neptune_x",
        "creality_ender3pro",
        "ultimaker2_plus",
    ]

    # Cura 설정
    cura_settings = {
        "layer_height": "0.2",
        "infill_sparse_density": "20",
        "wall_line_count": "3"
    }

    print("\n" + "="*80)
    print("Testing Multiple Printers")
    print("="*80)

    results = []

    for printer_name in printers:
        print(f"\n\n{'='*80}")
        print(f"Testing: {printer_name}")
        print(f"{'='*80}")

        result = test_upload_and_slice(
            stl_file_path=stl_file,
            printer_name=printer_name,
            cura_settings=cura_settings
        )

        results.append({
            "printer_name": printer_name,
            "success": result is not None
        })

        print("\n" + "-"*80)

    # 요약
    print("\n" + "="*80)
    print("Test Summary")
    print("="*80)

    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)

    print(f"\nTotal: {total_count}")
    print(f"Success: {success_count}")
    print(f"Failed: {total_count - success_count}")

    print("\nResults:")
    for r in results:
        status = "[OK]" if r['success'] else "[FAIL]"
        print(f"  {status} {r['printer_name']}")


if __name__ == "__main__":
    import sys

    # 사용법
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Single test:")
        print("    python test_api.py <stl_file> <printer_name>")
        print("  Example:")
        print('    python test_api.py ./output/test_cube_20mm.stl elegoo_neptune_x')
        print("\n  Multiple printers test:")
        print("    python test_api.py --multiple")
        print()

        # 기본 테스트 실행
        print("Running default test with elegoo_neptune_x...\n")
        test_upload_and_slice(
            stl_file_path="./output/test_cube_20mm.stl",
            printer_name="elegoo_neptune_x",
            cura_settings={"layer_height": "0.2"}
        )

    elif sys.argv[1] == "--multiple":
        # 여러 프린터 테스트
        test_multiple_printers()

    else:
        # 단일 테스트
        stl_file = sys.argv[1]
        printer_name = sys.argv[2]

        cura_settings = None
        if len(sys.argv) > 3:
            # 3번째 인자로 Cura 설정 JSON 받기
            cura_settings = json.loads(sys.argv[3])

        test_upload_and_slice(
            stl_file_path=stl_file,
            printer_name=printer_name,
            cura_settings=cura_settings
        )
