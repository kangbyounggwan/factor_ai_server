# Troubleshoot API 응답 형식

## API 엔드포인트

```
POST /api/v1/troubleshoot/diagnose
```

## 요청 형식

```json
{
  "manufacturer": "Creality",
  "model": "Ender 3 V2",
  "symptom_text": "출력중 실이 생기는 문제가 있어요",
  "images": ["base64_encoded_image..."],
  "language": "ko",
  "filament_type": "PLA",
  "user_plan": "free"
}
```

## 응답 형식

```json
{
  "diagnosis_id": "diag_abc123def456",

  "verdict": {
    "action": "continue",
    "headline": "지금은 멈출 필요 없어 보입니다.",
    "reason": "스트링 현상은 출력물 품질에 영향을 주지만 심각한 문제는 아닙니다."
  },

  "problem": {
    "type": "stringing",
    "confidence": 0.95,
    "description": "노즐 이동 시 필라멘트가 실처럼 늘어지는 현상입니다.",
    "detected_from": "both"
  },

  "solutions": [
    {
      "priority": 1,
      "title": "리트랙션 설정 최적화",
      "steps": [
        "슬라이서에서 리트랙션 거리를 4-7mm로 설정",
        "리트랙션 속도를 40-60mm/s로 설정",
        "테스트 출력으로 확인"
      ],
      "difficulty": "medium",
      "estimated_time": "30분",
      "tools_needed": ["슬라이서 소프트웨어"],
      "warnings": ["너무 긴 리트랙션은 노즐 막힘 유발 가능"],
      "source_refs": ["all3dp.com", "simplify3d.com"]
    }
  ],

  "references": [
    {
      "title": "How to Fix Stringing",
      "url": "https://all3dp.com/stringing-fix",
      "source": "perplexity",
      "relevance": 0.95,
      "snippet": "리트랙션 거리와 속도 조정이 가장 효과적입니다."
    }
  ],

  "reference_images": {
    "search_query": "3D printer stringing oozing retraction settings PLA example",
    "total_count": 10,
    "images": [
      {
        "title": "3D Printing Troubleshooting: Stringing / Oozing",
        "thumbnail_url": "https://imgs.search.brave.com/...",
        "source_url": "https://www.3dxtech.com/blogs/stringing",
        "width": 500,
        "height": 334
      },
      {
        "title": "How to Prevent Stringing in 3D Printing",
        "thumbnail_url": "https://imgs.search.brave.com/...",
        "source_url": "https://www.sovol3d.com/blogs/stringing",
        "width": 500,
        "height": 333
      }
    ]
  },

  "expert_opinion": {
    "summary": "스트링 현상은 리트랙션 설정과 온도 조정으로 대부분 해결됩니다.",
    "prevention_tips": [
      "필라멘트 건조 상태 유지",
      "정기적인 노즐 청소"
    ],
    "when_to_seek_help": "위 방법으로 해결되지 않을 경우"
  },

  "printer_info": {
    "firmware_type": "marlin",
    "follow_up_questions": [
      "현재 리트랙션 설정은 어떻게 되어 있나요?",
      "노즐 온도는 몇 도로 설정하셨나요?"
    ],
    "search_skipped": false,
    "kb_matches": [...]
  },

  "token_usage": {
    "image_analysis": 500,
    "search_query": 100,
    "search_summary": 800,
    "solution_generation": 1200,
    "total": 2600
  },

  "query_augmentation": {
    "original_symptom": "출력중 실이 생기는 문제",
    "augmented_query": "3D printer stringing oozing retraction PLA",
    "detected_problems": ["stringing"],
    "visual_evidence": ["가는 실 형태의 필라멘트", "거미줄 패턴"],
    "specific_symptoms": ["thin strings between parts"],
    "follow_up_questions": ["리트랙션 설정은?"],
    "search_decision": "recommended"
  }
}
```

## 주요 필드 설명

### `reference_images` (NEW)

사용자 문제와 유사한 참조 이미지를 제공합니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `search_query` | string | LLM이 컨텍스트 기반으로 생성한 검색 쿼리 |
| `total_count` | number | 검색된 이미지 수 (최대 10개) |
| `images` | array | 이미지 목록 |
| `images[].title` | string | 이미지 제목 |
| `images[].thumbnail_url` | string | 썸네일 이미지 URL (바로 표시 가능) |
| `images[].source_url` | string | 원본 페이지 URL (클릭 시 이동) |
| `images[].width` | number | 썸네일 너비 |
| `images[].height` | number | 썸네일 높이 |

### 프론트엔드 사용 예시

```tsx
// React 예시
function ReferenceImageGallery({ referenceImages }) {
  if (!referenceImages || referenceImages.images.length === 0) {
    return null;
  }

  return (
    <div className="reference-images">
      <h3>유사 문제 참조 이미지</h3>
      <p className="search-query">검색: {referenceImages.search_query}</p>

      <div className="image-grid">
        {referenceImages.images.map((img, idx) => (
          <a
            key={idx}
            href={img.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <img
              src={img.thumbnail_url}
              alt={img.title}
              width={img.width}
              height={img.height}
            />
            <span className="title">{img.title}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
```

### 이미지 검색 로직

1. **이미지 분석 결과 활용**: `augmented_query` 사용
2. **문제 유형 기반 템플릿**: `stringing` → "3D print stringing oozing example"
3. **대화 컨텍스트 활용**: 이전 대화 히스토리 참조
4. **LLM 쿼리 생성**: 컨텍스트 기반 최적 검색어 생성

### 문제 유형별 이미지 검색 예시

| 문제 유형 | 생성되는 검색 쿼리 |
|----------|------------------|
| `stringing` | "3D print stringing oozing retraction example" |
| `warping` | "3D print warping curling lifting example" |
| `bed_adhesion` | "3D print first layer adhesion problem example" |
| `layer_shifting` | "3D print layer shift misalignment example" |
| `under_extrusion` | "3D print under extrusion gaps example" |

## 주의사항

- `reference_images`가 `null`일 수 있음 (API 키 미설정 또는 검색 실패 시)
- 썸네일 URL은 Brave CDN에서 제공 (CORS 허용됨)
- 이미지는 최대 10개까지 반환
- Rate limit: Free 플랜 기준 초당 1회 요청
