# G-code 변환 API 클라이언트 가이드

## 개요

STL 파일을 G-code로 변환하는 API입니다.
**프린터 정의 파일(.def.json)을 클라이언트가 직접 body에 포함해서 전송**하는 방식입니다.

---

## API 엔드포인트

### POST `/v1/process/generate-gcode`

---

## Request Body

### 방법 1: 기본 프린터 사용 (서버 설정)

서버에 설정된 기본 프린터 정의를 사용합니다.

```json
{
  "task_id": "0199e86c-5074-7883-ba58-e6445e486c70",
  "cura_settings": {
    "layer_height": "0.2",
    "infill_sparse_density": "20",
    "support_enable": "true"
  }
}
```

---

### 방법 2: 커스텀 프린터 정의 전송 (권장)

클라이언트가 프린터 정의 JSON을 직접 전송합니다.

```json
{
  "task_id": "0199e86c-5074-7883-ba58-e6445e486c70",
  "printer_definition": {
    "version": 2,
    "name": "Creality Ender-3 Pro",
    "inherits": "creality_base",
    "metadata": {
      "visible": true,
      "platform": "creality_ender3.3mf",
      "quality_definition": "creality_base"
    },
    "overrides": {
      "machine_width": { "default_value": 220 },
      "machine_depth": { "default_value": 220 },
      "machine_height": { "default_value": 250 },
      "machine_name": { "default_value": "Creality Ender-3 Pro" },
      "machine_start_gcode": {
        "default_value": "G28 ; Home\nG1 Z5.0 F3000 ; Lift Z"
      }
    }
  },
  "cura_settings": {
    "layer_height": "0.15",
    "infill_sparse_density": "30"
  }
}
```

---

## Request 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `task_id` | string | 조건부* | 이전 작업의 task_id |
| `stl_path` | string | 조건부* | STL 파일 직접 경로 |
| `printer_definition` | object | 선택 | 프린터 정의 JSON (전체 .def.json 내용) |
| `cura_settings` | object | 선택 | 커스텀 슬라이싱 설정 |

\* `task_id` 또는 `stl_path` 중 하나는 필수

---

## Response

### 성공 응답

```json
{
  "status": "ok",
  "data": {
    "task_id": "0199e86c-5074-7883-ba58-e6445e486c70",
    "input_stl": "./output/cleaned_0199e86c-5074-7883-ba58-e6445e486c70.stl",
    "gcode_path": "./output/cleaned_0199e86c-5074-7883-ba58-e6445e486c70.gcode",
    "gcode_url": "http://localhost:7000/files/cleaned_0199e86c-5074-7883-ba58-e6445e486c70.gcode",
    "cura_settings": {
      "layer_height": "0.15",
      "infill_sparse_density": "30"
    }
  }
}
```

### 실패 응답

```json
{
  "status": "error",
  "error": "STL file not found"
}
```

---

## 프린터 정의 JSON 구조

프린터 정의 파일은 **Cura .def.json 형식**을 따릅니다.

### 최소 구조

```json
{
  "version": 2,
  "name": "My Custom Printer",
  "metadata": {
    "visible": true
  },
  "overrides": {
    "machine_width": { "default_value": 200 },
    "machine_depth": { "default_value": 200 },
    "machine_height": { "default_value": 200 },
    "machine_name": { "default_value": "My Custom Printer" },
    "machine_nozzle_size": { "default_value": 0.4 },
    "machine_center_is_zero": { "default_value": false }
  }
}
```

### 주요 설정 항목

```json
{
  "overrides": {
    // 프린터 크기
    "machine_width": { "default_value": 220 },
    "machine_depth": { "default_value": 220 },
    "machine_height": { "default_value": 250 },

    // 노즐 설정
    "machine_nozzle_size": { "default_value": 0.4 },

    // 원점 위치
    "machine_center_is_zero": { "default_value": false },

    // 시작 G-code
    "machine_start_gcode": {
      "default_value": "G28 ; Home all axes\nG1 Z5.0 F3000 ; Lift Z\nM104 S{material_print_temperature} ; Set nozzle temp\nM190 S{material_bed_temperature} ; Wait for bed temp\nM109 S{material_print_temperature} ; Wait for nozzle temp"
    },

    // 종료 G-code
    "machine_end_gcode": {
      "default_value": "M104 S0 ; Turn off nozzle\nM140 S0 ; Turn off bed\nG28 X0 Y0 ; Home X and Y\nM84 ; Disable motors"
    },

    // 가속도 설정
    "machine_max_acceleration_x": { "default_value": 500 },
    "machine_max_acceleration_y": { "default_value": 500 },
    "machine_max_acceleration_z": { "default_value": 100 },
    "machine_max_acceleration_e": { "default_value": 5000 },

    // 속도 제한
    "machine_max_feedrate_x": { "default_value": 500 },
    "machine_max_feedrate_y": { "default_value": 500 },
    "machine_max_feedrate_z": { "default_value": 10 },
    "machine_max_feedrate_e": { "default_value": 50 }
  }
}
```

---

## Cura 슬라이싱 설정 (`cura_settings`)

### 기본 프린트 설정

```json
{
  "layer_height": "0.2",              // 레이어 높이 (mm): 0.1~0.3
  "wall_line_count": "3",             // 벽 레이어 수: 2~5
  "wall_thickness": "1.2",            // 벽 두께 (mm)
  "top_layers": "4",                  // 상단 레이어 수
  "bottom_layers": "4",               // 하단 레이어 수
  "infill_sparse_density": "20",      // 인필 밀도 (%): 0~100
  "infill_pattern": "grid"            // 패턴: grid, lines, cubic, gyroid
}
```

### 속도 설정 (mm/s)

```json
{
  "speed_print": "50",                // 기본 프린트 속도
  "speed_infill": "60",               // 인필 속도
  "speed_wall": "40",                 // 벽 속도
  "speed_wall_0": "30",               // 외벽 속도
  "speed_topbottom": "40",            // 상하단 속도
  "speed_travel": "150",              // 이동 속도
  "speed_layer_0": "20"               // 첫 레이어 속도
}
```

### 온도 설정 (°C)

```json
{
  "material_print_temperature": "200",           // 노즐 온도
  "material_bed_temperature": "60",              // 베드 온도
  "material_print_temperature_layer_0": "205"    // 첫 레이어 노즐 온도
}
```

### 서포트 설정

```json
{
  "support_enable": "true",           // 서포트 활성화 (true/false)
  "support_type": "everywhere",       // buildplate 또는 everywhere
  "support_angle": "50",              // 서포트 각도 (°)
  "support_infill_rate": "20",        // 서포트 밀도 (%)
  "support_z_distance": "0.2"         // Z 간격 (mm)
}
```

### 접착 설정

```json
{
  "adhesion_type": "brim",            // none, skirt, brim, raft
  "brim_width": "8",                  // Brim 너비 (mm)
  "skirt_line_count": "3",            // Skirt 라인 수
  "skirt_gap": "3"                    // Skirt 간격 (mm)
}
```

### 리트랙션 설정

```json
{
  "retraction_enable": "true",        // 리트랙션 활성화
  "retraction_amount": "5",           // 거리 (mm)
  "retraction_speed": "45",           // 속도 (mm/s)
  "retraction_min_travel": "1.5"      // 최소 이동 거리 (mm)
}
```

---

## 프린터별 정의 예시

### Creality Ender-3 Pro

```json
{
  "version": 2,
  "name": "Creality Ender-3 Pro",
  "inherits": "creality_base",
  "metadata": {
    "visible": true,
    "platform": "creality_ender3.3mf"
  },
  "overrides": {
    "machine_width": { "default_value": 220 },
    "machine_depth": { "default_value": 220 },
    "machine_height": { "default_value": 250 },
    "machine_nozzle_size": { "default_value": 0.4 },
    "machine_center_is_zero": { "default_value": false },
    "machine_heated_bed": { "default_value": true },
    "machine_start_gcode": {
      "default_value": "G92 E0\nG28\nG1 Z5.0 F3000\nM104 S{material_print_temperature}\nM190 S{material_bed_temperature_layer_0}\nM109 S{material_print_temperature_layer_0}\nG1 Z2.0 F3000\nG1 X0.1 Y20 Z0.3 F5000.0\nG1 X0.1 Y200.0 Z0.3 F1500.0 E15\nG1 X0.4 Y200.0 Z0.3 F5000.0\nG1 X0.4 Y20 Z0.3 F1500.0 E30\nG92 E0"
    },
    "machine_end_gcode": {
      "default_value": "G91\nG1 E-2 F2700\nG1 E-2 Z0.2 F2400\nG1 X5 Y5 F3000\nG1 Z10\nG90\nG1 X0 Y220\nM106 S0\nM104 S0\nM140 S0\nM84 X Y E"
    }
  }
}
```

---

### Prusa i3 MK3S

```json
{
  "version": 2,
  "name": "Prusa i3 MK3S",
  "metadata": {
    "visible": true
  },
  "overrides": {
    "machine_width": { "default_value": 250 },
    "machine_depth": { "default_value": 210 },
    "machine_height": { "default_value": 210 },
    "machine_nozzle_size": { "default_value": 0.4 },
    "machine_center_is_zero": { "default_value": false },
    "machine_heated_bed": { "default_value": true },
    "machine_start_gcode": {
      "default_value": "G28 W\nG80\nG1 Y-3.0 F1000.0\nG1 Z0.4 F1000.0\nG1 X55.0 E32.0 F1073.0\nG1 X5.0 E32.0 F1800.0\nG92 E0.0"
    },
    "machine_end_gcode": {
      "default_value": "G4\nG1 E-1 F2100\nG91\nG1 Z1 F7200\nG90\nG1 X0 Y210\nM84\nM107"
    }
  }
}
```

---

## 사용 예시

### Python 예시

```python
import requests
import json

# 프린터 정의 JSON 로드
with open('ender3pro.def.json', 'r') as f:
    printer_def = json.load(f)

# API 요청
response = requests.post(
    'http://localhost:7000/v1/process/generate-gcode',
    json={
        'task_id': '0199e86c-5074-7883-ba58-e6445e486c70',
        'printer_definition': printer_def,
        'cura_settings': {
            'layer_height': '0.15',
            'infill_sparse_density': '25',
            'support_enable': 'true',
            'adhesion_type': 'brim'
        }
    }
)

result = response.json()
if result['status'] == 'ok':
    gcode_url = result['data']['gcode_url']
    print(f'G-code generated: {gcode_url}')
else:
    print(f'Error: {result["error"]}')
```

---

### cURL 예시

```bash
curl -X POST http://localhost:7000/v1/process/generate-gcode \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "0199e86c-5074-7883-ba58-e6445e486c70",
    "printer_definition": {
      "version": 2,
      "name": "My Printer",
      "metadata": {"visible": true},
      "overrides": {
        "machine_width": {"default_value": 220},
        "machine_depth": {"default_value": 220},
        "machine_height": {"default_value": 250}
      }
    },
    "cura_settings": {
      "layer_height": "0.2",
      "infill_sparse_density": "20"
    }
  }'
```

---

### JavaScript/TypeScript 예시

```typescript
async function generateGCode(taskId: string) {
  // 프린터 정의
  const printerDefinition = {
    version: 2,
    name: "Creality Ender-3 Pro",
    metadata: { visible: true },
    overrides: {
      machine_width: { default_value: 220 },
      machine_depth: { default_value: 220 },
      machine_height: { default_value: 250 },
      machine_nozzle_size: { default_value: 0.4 }
    }
  };

  // 슬라이싱 설정
  const curaSettings = {
    layer_height: "0.15",
    infill_sparse_density: "30",
    support_enable: "true",
    adhesion_type: "brim",
    speed_print: "50"
  };

  const response = await fetch('http://localhost:7000/v1/process/generate-gcode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task_id: taskId,
      printer_definition: printerDefinition,
      cura_settings: curaSettings
    })
  });

  const result = await response.json();

  if (result.status === 'ok') {
    const gcodeUrl = result.data.gcode_url;
    console.log('G-code URL:', gcodeUrl);

    // G-code 다운로드
    const gcodeResponse = await fetch(gcodeUrl);
    const gcodeContent = await gcodeResponse.text();
    return gcodeContent;
  } else {
    throw new Error(result.error);
  }
}
```

---

## 전체 워크플로우

```
1. 이미지 업로드
   POST /v1/process/modelling
   body: { task: "image_to_3d", image_file: ... }
   → response: { task_id: "abc123", stl_download_url: "..." }

2. G-code 생성
   POST /v1/process/generate-gcode
   body: {
     task_id: "abc123",
     printer_definition: { ... },  // 프린터 정의 JSON
     cura_settings: { ... }        // 슬라이싱 설정
   }
   → response: { gcode_url: "..." }

3. G-code 다운로드
   GET /files/cleaned_abc123.gcode
```

---

## 주요 설정 파라미터 전체 목록

90개 이상의 설정 파라미터 전체 목록은 [GCODE_API_GUIDE.md](./GCODE_API_GUIDE.md) 참조

---

## FAQ

### Q1: 프린터 정의 파일은 어디서 구하나요?

**A**: Cura 설치 디렉토리에서 가져올 수 있습니다.

Windows:
```
C:\Program Files\UltiMaker Cura 5.7.1\share\cura\resources\definitions\
```

또는 Cura GitHub:
https://github.com/Ultimaker/Cura/tree/main/resources/definitions

---

### Q2: 프린터 정의를 매번 전송해야 하나요?

**A**: 아니오. 두 가지 방법이 있습니다:
- **방법 1**: `printer_definition` 없이 요청 → 서버 기본 프린터 사용
- **방법 2**: `printer_definition` 포함 → 해당 프린터로 슬라이싱

클라이언트 쪽에서 프린터 정의를 캐싱하고 필요할 때만 다른 프린터로 변경 가능합니다.

---

### Q3: 슬라이싱 설정 값은 문자열인가요 숫자인가요?

**A**: **모두 문자열**입니다.

```json
// 올바른 예
{
  "layer_height": "0.2",
  "infill_sparse_density": "20",
  "support_enable": "true"
}

// 잘못된 예
{
  "layer_height": 0.2,          // ❌ 숫자
  "infill_sparse_density": 20,  // ❌ 숫자
  "support_enable": true        // ❌ boolean
}
```

---

### Q4: G-code 생성 시간은 얼마나 걸리나요?

**A**: 모델 크기에 따라 다르지만:
- 소형 모델 (< 10MB STL): 1-5초
- 중형 모델 (10-50MB STL): 5-30초
- 대형 모델 (> 50MB STL): 30-180초

타임아웃은 기본 300초 (5분)로 설정되어 있습니다.

---

### Q5: 여러 프린터를 동시에 지원하려면?

**A**: 클라이언트 쪽에서 프린터 정의를 관리하고, 요청 시 해당 프린터 정의를 전송하면 됩니다.

예시:
```javascript
const printers = {
  'ender3pro': { /* 정의 */ },
  'prusa_mk3s': { /* 정의 */ },
  'custom': { /* 정의 */ }
};

// 사용자가 선택한 프린터로 슬라이싱
const selectedPrinter = 'ender3pro';
const response = await fetch('/v1/process/generate-gcode', {
  method: 'POST',
  body: JSON.stringify({
    task_id: taskId,
    printer_definition: printers[selectedPrinter],
    cura_settings: { ... }
  })
});
```

---

## 에러 코드

| 상태 코드 | 설명 | 해결 방법 |
|-----------|------|-----------|
| 400 | task_id 또는 stl_path 누락 | 둘 중 하나 제공 |
| 404 | STL 파일 없음 | task_id 확인 또는 올바른 경로 제공 |
| 503 | CuraEngine 없음 | 서버 관리자에게 문의 |
| 500 | 슬라이싱 실패 | 로그 확인, 설정 값 검증 |

---

## 구현 완료!

**클라이언트가 프린터 정의 JSON을 직접 전송**하는 방식으로 구현 완료되었습니다.

- DB 불필요
- 프린터 정의 관리 유연성
- 클라이언트 캐싱 가능
- 즉시 사용 가능

더 자세한 내용은 [GCODE_API_GUIDE.md](./GCODE_API_GUIDE.md) 참조하세요.
