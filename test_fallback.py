"""
Test fallback logic: custom definition -> fdmprinter + bed size
"""
import requests
import json

def test_fallback():
    """Test that custom printer definition falls back to fdmprinter + bed size"""

    # 클라이언트가 보내는 형식 (bed size만 포함)
    printer_definition = {
        "version": 2,
        "name": "Creality Ender-3",
        "overrides": {
            "machine_width": {"default_value": 220},
            "machine_depth": {"default_value": 220},
            "machine_height": {"default_value": 250}
        }
    }

    cura_settings = {
        "layer_height": "0.2",
        "infill_sparse_density": "15"
    }

    # Prepare request
    url = "http://localhost:7000/v1/process/upload-stl-and-slice"

    files = {
        'model_file': ('test_cube.stl', open('./output/test_cube_20mm.stl', 'rb'), 'application/octet-stream')
    }

    data = {
        'cura_settings_json': json.dumps(cura_settings),
        'printer_definition_json': json.dumps(printer_definition)
    }

    print("="*80)
    print("Testing Fallback Logic")
    print("="*80)
    print(f"\n[INFO] Sending request to {url}")
    print(f"[INFO] Printer definition: {printer_definition['name']}")
    print(f"[INFO] Bed size: {printer_definition['overrides']['machine_width']['default_value']}x{printer_definition['overrides']['machine_depth']['default_value']}x{printer_definition['overrides']['machine_height']['default_value']}")
    print(f"[INFO] Cura settings: {cura_settings}")

    try:
        response = requests.post(url, files=files, data=data, timeout=120)

        print(f"\n[INFO] Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\n[SUCCESS] Slicing succeeded!")
            print(f"[INFO] Response: {json.dumps(result, indent=2)}")

            if 'data' in result and 'download_url' in result['data']:
                print(f"\n[INFO] Download URL: {result['data']['download_url']}")
        else:
            print(f"\n[FAIL] HTTP {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        print(f"\n[ERROR] Request timeout (>120s)")
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    test_fallback()
