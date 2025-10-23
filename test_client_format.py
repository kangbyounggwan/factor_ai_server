"""
클라이언트 요청 형식으로 API 테스트

실제 클라이언트가 보내는 형식:
- stl_file (not model_file)
- cura_settings_json as JSON object (not string)
- printer_definition_json as JSON object (not string)
"""

import requests
import json


def test_client_request():
    """클라이언트 요청 형식대로 테스트"""

    # 서버 URL
    url = "http://127.0.0.1:7000/v1/process/upload-stl-and-slice"

    # 테스트용 STL 파일
    stl_file_path = "./output/test_cube_20mm.stl"

    # Cura 설정 (JSON 객체)
    cura_settings = {
        "layer_height": "0.2",
        "line_width": "0.4",
        "infill_sparse_density": "15",
        "wall_line_count": "2",
        "top_layers": "4",
        "bottom_layers": "4",
        "speed_print": "50",
        "support_enable": "true",
        "support_angle": "50",
        "adhesion_type": "none",
        "material_diameter": "1.75",
        "material_flow": "100"
    }

    # 프린터 정의 (JSON 객체)
    printer_definition = {
        "version": 2,
        "name": "Creality Ender-3 / Ender-3 v2",
        "overrides": {
            "machine_width": {
                "default_value": 220
            },
            "machine_depth": {
                "default_value": 220
            },
            "machine_height": {
                "default_value": 250
            }
        }
    }

    print("="*80)
    print("Client Format API Test")
    print("="*80)
    print(f"\n[INFO] Request Details:")
    print(f"  - URL: {url}")
    print(f"  - STL file: {stl_file_path}")
    print(f"  - Cura settings: {len(cura_settings)} parameters")
    print(f"  - Printer definition: Provided")

    # FormData 구성
    with open(stl_file_path, 'rb') as f:
        files = {
            'model_file': (f'model_{1761213206012}.glb', f, 'model/gltf-binary')
        }

        data = {
            # JSON 객체를 JSON 문자열로 변환
            'cura_settings_json': json.dumps(cura_settings),
            'printer_definition_json': json.dumps(printer_definition)
        }

        print(f"\n[INFO] Sending request...")
        print(f"[INFO] Files: model_file = {stl_file_path}")
        print(f"[INFO] Data keys: {list(data.keys())}")

        try:
            response = requests.post(url, files=files, data=data, timeout=120)

            print(f"\n[RESPONSE] Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()

                if result.get('status') == 'ok':
                    data = result['data']

                    print("\n" + "="*80)
                    print("[SUCCESS] ✅ Request succeeded!")
                    print("="*80)

                    print(f"\n[Response Data]:")
                    print(f"  Original filename: {data['original_filename']}")
                    print(f"  Original format: {data['original_format']}")
                    print(f"  Converted to STL: {data['converted_to_stl']}")
                    print(f"  STL size: {data['file_size']['stl_bytes']:,} bytes")
                    print(f"  G-code size: {data['file_size']['gcode_bytes']:,} bytes")
                    print(f"  G-code URL: {data['gcode_url']}")
                    print(f"  Printer source: {data.get('printer_source', 'N/A')}")

                    # G-code 다운로드
                    print(f"\n[INFO] Downloading G-code...")
                    gcode_response = requests.get(data['gcode_url'], timeout=10)

                    if gcode_response.status_code == 200:
                        gcode_content = gcode_response.text
                        print(f"[SUCCESS] ✅ G-code downloaded: {len(gcode_content):,} characters")

                        # 로컬에 저장
                        output_file = "./test_output_client_format.gcode"
                        with open(output_file, 'w') as f:
                            f.write(gcode_content)
                        print(f"[INFO] Saved to: {output_file}")

                        # 미리보기
                        print(f"\n[G-code Preview]:")
                        print(gcode_content[:300])
                        print("...")

                    return result

                else:
                    print(f"\n[FAIL] ❌ API error")
                    print(f"Error: {result.get('error', 'Unknown')}")
                    return None

            else:
                print(f"\n[FAIL] ❌ HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"Error detail: {json.dumps(error_detail, indent=2)}")
                except:
                    print(f"Response text: {response.text[:500]}")
                return None

        except requests.ConnectionError:
            print(f"\n[ERROR] ❌ Connection failed!")
            print(f"Make sure server is running:")
            print(f"  uvicorn main:app --reload --port 7000")
            return None
        except Exception as e:
            print(f"\n[ERROR] ❌ {type(e).__name__}: {str(e)}")
            return None


def test_with_printer_name():
    """printer_name 사용 테스트"""

    url = "http://127.0.0.1:7000/v1/process/upload-stl-and-slice"
    stl_file_path = "./output/test_cube_20mm.stl"

    # Cura 설정
    cura_settings = {
        "layer_height": "0.2",
        "infill_sparse_density": "20"
    }

    print("\n\n" + "="*80)
    print("Test with printer_name (권장 방식)")
    print("="*80)

    with open(stl_file_path, 'rb') as f:
        files = {
            'model_file': ('model.stl', f, 'application/octet-stream')
        }

        data = {
            'printer_name': 'elegoo_neptune_x',  # DB의 filename에서 .def.json 제거
            'cura_settings_json': json.dumps(cura_settings)
        }

        print(f"\n[INFO] Using printer_name: elegoo_neptune_x")
        print(f"[INFO] Sending request...")

        try:
            response = requests.post(url, files=files, data=data, timeout=120)

            print(f"\n[RESPONSE] Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()

                if result.get('status') == 'ok':
                    data = result['data']
                    print(f"\n[SUCCESS] ✅ Slicing succeeded!")
                    print(f"  Printer name: {data.get('printer_name', 'N/A')}")
                    print(f"  Printer source: {data.get('printer_source', 'N/A')}")
                    print(f"  G-code size: {data['file_size']['gcode_bytes']:,} bytes")
                    print(f"  G-code URL: {data['gcode_url']}")

                    return result
                else:
                    print(f"\n[FAIL] ❌ {result.get('error', 'Unknown')}")
            else:
                print(f"\n[FAIL] ❌ HTTP {response.status_code}")
                print(response.text[:500])

        except Exception as e:
            print(f"\n[ERROR] ❌ {str(e)}")


if __name__ == "__main__":
    import sys

    # 테스트 1: printer_definition_json 사용 (클라이언트 현재 방식)
    print("\n📋 Test 1: With printer_definition_json")
    test_client_request()

    # 테스트 2: printer_name 사용 (권장 방식)
    print("\n📋 Test 2: With printer_name (recommended)")
    test_with_printer_name()

    print("\n" + "="*80)
    print("All tests completed!")
    print("="*80)
