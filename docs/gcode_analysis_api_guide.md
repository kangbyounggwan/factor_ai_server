# G-code 분석 API 리턴 형식 및 UI 통합 가이드

## 목차
1. [API 응답 구조](#api-응답-구조)
2. [이슈-패치 ID 매핑](#이슈-패치-id-매핑)
3. [프론트엔드 접근 키](#프론트엔드-접근-키)
4. [UI 컴포넌트 설계 제안](#ui-컴포넌트-설계-제안)
5. [실제 응답 예시](#실제-응답-예시)

---

## API 응답 구조

### 최상위 구조

```typescript
interface AnalysisResponse {
  // 기본 정보
  file_name: string;
  filament_type: string;
  analysis_mode: string;

  // 핵심 결과
  final_summary: FinalSummary;

  // 패치 계획 (NEW)
  patch_plan: PatchPlan;

  // 상세 데이터
  comprehensive_summary: ComprehensiveSummary;
  issues_found: Issue[];

  // 메타데이터
  token_usage: TokenUsage;
  errors: string[];
}
```

### FinalSummary (최종 요약)

```typescript
interface FinalSummary {
  expert_assessment: {
    quality_score: number;        // 0-100 점수
    quality_grade: string;        // S, A, B, C, D, F 등급
    summary_text: string;         // 종합 평가 텍스트
    recommendations: string[];    // 권장 사항 목록
  };

  critical_issues: CriticalIssue[];  // 중요 이슈 목록 (패치 ID 포함)

  statistics: {
    total_lines: number;
    total_layers: number;
    estimated_time: string;
    filament_used: number;
  };
}
```

### CriticalIssue (중요 이슈)

```typescript
interface CriticalIssue {
  id: string;              // "ISSUE-1", "ISSUE-2", ...
  patch_id: string | null; // "PATCH-001" 또는 null (패치 없음)
  line: number;            // G-code 라인 번호
  type: string;            // 이슈 유형 코드
  severity: string;        // "critical" | "warning" | "info"
  title: string;           // 이슈 제목
  description: string;     // 상세 설명
  fix_proposal: string;    // 수정 제안
}
```

### PatchPlan (패치 계획)

```typescript
interface PatchPlan {
  file_path: string;              // 원본 파일 경로
  total_patches: number;          // 전체 패치 수
  patches: Patch[];               // 패치 목록
  estimated_improvement: number;  // 예상 품질 개선 점수 (0-100)
}

interface Patch {
  id: string;               // "PATCH-001", "PATCH-002", ...
  issue_id: string | null;  // "ISSUE-1" (연결된 이슈) 또는 null
  line_index: number;       // 대상 라인 번호 (line과 동일)
  line: number;             // 대상 라인 번호
  layer: number;            // 해당 레이어 번호
  original: string;         // 원본 라인 내용
  original_line: string;    // 원본 라인 (alias)
  action: PatchAction;      // 액션 유형
  modified: string | null;  // 추가/수정할 G-code 명령어 (핵심!)
  new_line: string | null;  // modified의 alias
  position: Position;       // 추가 위치: "before" | "after" | "replace"
  reason: string;           // 패치 이유/설명
  issue_type: string;       // 이슈 유형
  autofix_allowed: boolean; // 자동 패치 허용 여부
}

type PatchAction =
  | "modify"   // 기존 라인을 수정 (position: "replace")
  | "add"      // 새 라인 추가 (position: "before" | "after")
  | "delete"   // 라인 삭제
  | "review";  // 수동 검토 필요 (H 파라미터 등 벤더 확장)

type Position = "before" | "after" | "replace" | null;
```

---

## 이슈-패치 ID 매핑

### 양방향 연결 구조

```
┌─────────────┐         ┌─────────────┐
│   ISSUE-1   │◄───────►│  PATCH-001  │
│  patch_id:  │         │  issue_id:  │
│  "PATCH-001"│         │  "ISSUE-1"  │
└─────────────┘         └─────────────┘
```

### 매핑 규칙

1. **1:1 매핑**: 하나의 이슈에 하나의 패치
2. **ID 형식**:
   - 이슈: `ISSUE-{순번}` (예: ISSUE-1, ISSUE-2)
   - 패치: `PATCH-{순번:03d}` (예: PATCH-001, PATCH-002)
3. **null 허용**: 패치 불가능한 이슈는 `patch_id: null`

### 프론트엔드에서 매칭하기

```typescript
// 이슈에서 패치 찾기
function getPatchForIssue(issueId: string, patches: Patch[]): Patch | undefined {
  return patches.find(p => p.issue_id === issueId);
}

// 패치에서 이슈 찾기
function getIssueForPatch(patchId: string, issues: CriticalIssue[]): CriticalIssue | undefined {
  return issues.find(i => i.patch_id === patchId);
}

// 이슈와 패치 병합
function mergeIssueWithPatch(issue: CriticalIssue, patches: Patch[]) {
  const patch = patches.find(p => p.issue_id === issue.id);
  return {
    ...issue,
    patch: patch || null,
    hasPatch: !!patch,
    canAutoFix: patch?.can_auto_apply ?? false
  };
}
```

---

## 프론트엔드 접근 키

### 핵심 데이터 접근 경로

```typescript
// 1. 품질 점수
const score = response.final_summary.expert_assessment.quality_score;
const grade = response.final_summary.expert_assessment.quality_grade;

// 2. 이슈 목록 (패치 ID 포함)
const issues = response.final_summary.critical_issues;
issues.forEach(issue => {
  console.log(issue.id);        // "ISSUE-1"
  console.log(issue.patch_id);  // "PATCH-001" 또는 null
  console.log(issue.line);      // 라인 번호
  console.log(issue.severity);  // "critical" | "warning"
});

// 3. 패치 목록 (실제 응답 형식)
const patches = response.patch_plan.patches;
patches.forEach(patch => {
  console.log(patch.id);              // "PATCH-001"
  console.log(patch.issue_id);        // "ISSUE-1"
  console.log(patch.line);            // 525
  console.log(patch.action);          // "add" | "modify" | "review" | "delete"
  console.log(patch.original);        // "M140 S65"
  console.log(patch.modified);        // null 또는 수정된 라인
  console.log(patch.reason);          // "M140 전에 M104 S(권장온도) 명령 추가"
  console.log(patch.autofix_allowed); // true | false
  console.log(patch.issue_type);      // "bed_temp_no_wait"
  console.log(patch.layer);           // 0 (레이어 번호)
});

// 4. 패치 통계
const totalPatches = response.patch_plan.total_patches;     // 전체 패치 수
const autoApplicable = response.patch_plan.patches.filter(p => p.autofix_allowed).length;
const needsReview = response.patch_plan.patches.filter(p => p.action === 'review').length;
const estimatedImprovement = response.patch_plan.estimated_improvement; // 예상 품질 개선

// 5. 이슈-패치 매핑
function getIssuePatches(issueId: string) {
  return response.patch_plan.patches.filter(p => p.issue_id === issueId);
}

function getPatchIssue(patchId: string) {
  const patch = response.patch_plan.patches.find(p => p.id === patchId);
  if (!patch) return null;
  return response.final_summary.critical_issues.find(i => i.id === patch.issue_id);
}
```

---

## UI 컴포넌트 설계 제안

### 1. 대시보드 헤더

```
┌──────────────────────────────────────────────────────────────┐
│  📊 G-code 분석 결과                                          │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  품질 점수: 75/100 (B등급)     필라멘트: PLA                   │
│  이슈: 5개 (심각 2, 주의 3)    패치 가능: 4개                   │
└──────────────────────────────────────────────────────────────┘
```

### 2. 이슈 리스트 (카드 형태)

```
┌──────────────────────────────────────────────────────────────┐
│ 🔴 ISSUE-1: 베드 온도 대기 누락                    Line 525   │
│ ─────────────────────────────────────────────────────────── │
│ 베드 온도 설정 후 대기 없이 프린팅 시작                         │
│                                                              │
│ [📝 패치 보기] [✅ 자동 적용 가능]                PATCH-001    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ 🟡 ISSUE-2: 벤더 확장 코드 감지                    Line 589   │
│ ─────────────────────────────────────────────────────────── │
│ Bambu/Orca H 파라미터 사용 (M109 S25 H140)                   │
│                                                              │
│ [📝 패치 보기] [⚠️ 수동 검토 필요]                PATCH-002    │
└──────────────────────────────────────────────────────────────┘
```

### 3. 패치 상세 뷰 (Diff 스타일)

```
┌──────────────────────────────────────────────────────────────┐
│ 🔧 PATCH-001 - 베드 온도 대기 추가                            │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 액션: add_after │ 위험도: high │ 자동 적용: ✅                │
├──────────────────────────────────────────────────────────────┤
│ 원본 (Line 525)                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │  520:                                                   │  │
│ │  521: ;===== start to heat heatbead&hotend====         │  │
│ │  522: M1002 gcode_claim_action : 2                     │  │
│ │  523: M1002 set_filament_type:PLA                      │  │
│ │  524: M104 S140                                        │  │
│ │► 525: M140 S65                                         │  │
│ │  526:                                                   │  │
│ │  527: ;=====start printer sound ===================    │  │
│ └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│ 패치 후                                                       │
│ ┌────────────────────────────────────────────────────────┐  │
│ │  524: M104 S140                                        │  │
│ │  525: M140 S65                                         │  │
│ │+ 526: M190 S65    ← 추가됨                              │  │
│ │  527:                                                   │  │
│ │  528: ;=====start printer sound ===================    │  │
│ └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│ 설명: 베드 온도가 65도에 도달할 때까지 대기하는 M190 명령 추가  │
│                                                              │
│         [적용] [건너뛰기] [모두 적용]                          │
└──────────────────────────────────────────────────────────────┘
```

### 4. 코드 에디터 통합 (Monaco/CodeMirror)

```typescript
// 이슈 하이라이트 마커 생성
function createIssueMarkers(issues: CriticalIssue[]) {
  return issues.map(issue => ({
    startLineNumber: issue.line,
    endLineNumber: issue.line,
    message: `${issue.title}\n${issue.description}`,
    severity: issue.severity === 'critical' ? 8 : 4, // Error : Warning
    source: issue.id,
    // 패치 연결
    relatedInformation: issue.patch_id ? [{
      message: `패치 가능: ${issue.patch_id}`,
      resource: issue.patch_id
    }] : []
  }));
}

// Gutter decoration (라인 번호 옆 아이콘)
function createGutterDecorations(issues: CriticalIssue[]) {
  return issues.map(issue => ({
    range: { startLineNumber: issue.line, startColumn: 1, endLineNumber: issue.line, endColumn: 1 },
    options: {
      glyphMarginClassName: issue.severity === 'critical' ? 'error-glyph' : 'warning-glyph',
      glyphMarginHoverMessage: { value: `**${issue.title}**\n\n${issue.description}` }
    }
  }));
}
```

### 5. 사이드 패널 구조

```
┌─────────────────────┐
│ 📋 이슈 목록 (5)     │
├─────────────────────┤
│ ● ISSUE-1  L.525    │ ← 클릭 시 해당 라인으로 이동
│   🔧 PATCH-001      │ ← 클릭 시 패치 상세 보기
├─────────────────────┤
│ ● ISSUE-2  L.589    │
│   🔧 PATCH-002      │
├─────────────────────┤
│ ● ISSUE-3  L.598    │
│   🔧 PATCH-003      │
├─────────────────────┤
│ ○ ISSUE-4  L.628    │ ← 회색: 패치 불가
│   ⚠️ 수동 검토 필요  │
├─────────────────────┤
│ ● ISSUE-5  L.650    │
│   🔧 PATCH-005      │
└─────────────────────┘
```

---

## 실제 응답 예시

### 전체 응답 구조

```json
{
  "file_name": "cup2_14_2_A1.gcode",
  "filament_type": "PLA",
  "analysis_mode": "full",

  "final_summary": {
    "expert_assessment": {
      "quality_score": 75,
      "quality_grade": "B",
      "summary_text": "전반적으로 양호하나 온도 관리 개선 필요",
      "recommendations": [
        "베드 온도 대기 명령 추가 권장",
        "노즐 온도 250도는 PLA에 과도함"
      ]
    },
    "critical_issues": [
      {
        "id": "ISSUE-1",
        "patch_id": "PATCH-001",
        "line": 525,
        "type": "bed_temp_no_wait",
        "severity": "critical",
        "title": "베드 온도 대기 누락",
        "description": "베드 온도 설정 후 대기 없이 프린팅 시작",
        "fix_proposal": "M140 S65 후 M190 S65 추가"
      },
      {
        "id": "ISSUE-2",
        "patch_id": "PATCH-002",
        "line": 589,
        "type": "vendor_extension",
        "severity": "warning",
        "title": "벤더 확장 코드 감지",
        "description": "Bambu/Orca H 파라미터 사용",
        "fix_proposal": "수동 검토 권장"
      }
    ]
  },

  "patch_plan": {
    "patches": [...],
    "summary": {
      "total_patches": 5,
      "auto_applicable": 4,
      "needs_review": 1
    }
  }
}
```

---

## 패치 계획 (patch_plan) 상세 예시

실제 `cup2_14_2_A1.gcode` 분석 결과에서 생성된 패치 데이터입니다.

### 실제 API 응답 (수정된 형식)

```json
{
  "patch_plan": {
    "file_path": "C:\\Users\\USER\\Downloads\\cup2_14_2_A1.gcode",
    "total_patches": 10,
    "patches": [
      {
        "id": "PATCH-001",
        "issue_id": "ISSUE-1",
        "line": 525,
        "line_index": 525,
        "layer": 0,
        "action": "add",
        "modified": "M190 S65",
        "position": "after",
        "reason": "베드 온도 대기 명령 추가",
        "original": "M140 S65",
        "issue_type": "bed_temp_no_wait",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-002",
        "issue_id": "ISSUE-2",
        "line": 589,
        "line_index": 589,
        "layer": 0,
        "action": "review",
        "modified": null,
        "position": null,
        "reason": "M109 S220(권장 온도) 대기 명령 추가 [BAMBU 벤더 확장 감지: H=140, 신뢰도=high]",
        "original": "M109 S25 H140",
        "issue_type": "vendor_extension",
        "autofix_allowed": false
      },
      {
        "id": "PATCH-003",
        "issue_id": "ISSUE-3",
        "line": 598,
        "line_index": 598,
        "layer": 0,
        "action": "modify",
        "modified": "M109 S220",
        "position": "replace",
        "reason": "M104→M109 온도 대기 명령으로 변경",
        "original": "M104 S220",
        "issue_type": "temp_no_wait",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-004",
        "issue_id": "ISSUE-4",
        "line": 628,
        "line_index": 628,
        "layer": 0,
        "action": "review",
        "reason": "M104 S220, M109 S220으로 수정",
        "modified": null,
        "original": "M104 S250",
        "issue_type": "excessive_temp",
        "autofix_allowed": false
      },
      {
        "id": "PATCH-005",
        "issue_id": "ISSUE-5",
        "line": 874,
        "line_index": 874,
        "layer": 0,
        "action": "add",
        "reason": "M109 S200 (PLA 권장 온도) 대기 추가",
        "modified": null,
        "original": "M104 S140 ; prepare to abl",
        "issue_type": "temp_no_wait",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-006",
        "issue_id": "ISSUE-6",
        "line": 993,
        "line_index": 993,
        "layer": 0,
        "action": "add",
        "reason": "M190 후 M104/M109 대기 명령 추가",
        "modified": null,
        "original": "M190 S65; ensure bed temp",
        "issue_type": "bed_temp_sequence",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-007",
        "issue_id": "ISSUE-7",
        "line": 994,
        "line_index": 994,
        "layer": 0,
        "action": "review",
        "reason": "M109 S200 (권장 온도) 또는 S180 이상으로 변경",
        "modified": null,
        "original": "M109 S140",
        "issue_type": "low_temp",
        "autofix_allowed": false
      },
      {
        "id": "PATCH-008",
        "issue_id": "ISSUE-8",
        "line": 1024,
        "line_index": 1024,
        "layer": 0,
        "action": "add",
        "reason": "M109 S220 명령어로 온도 도달 대기 추가",
        "modified": null,
        "original": "M104 S220 ; prepare to print",
        "issue_type": "temp_no_wait",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-009",
        "issue_id": "ISSUE-9",
        "line": 593,
        "line_index": 593,
        "layer": 0,
        "action": "add",
        "reason": "압출 명령 전 M109 명령으로 온도 대기 추가",
        "modified": null,
        "original": "G1 E10 F1200",
        "issue_type": "extrusion_before_temp",
        "autofix_allowed": true
      },
      {
        "id": "PATCH-010",
        "issue_id": "ISSUE-10",
        "line": 26602,
        "line_index": 26602,
        "layer": 245,
        "action": "add",
        "reason": "M109 S200 (권장 온도) 추가",
        "modified": null,
        "original": "G1 X167.744 Y107.192 E.00072",
        "issue_type": "temp_drop",
        "autofix_allowed": true
      }
    ],
    "estimated_improvement": 15
  }
}
```

---

### 패치 액션 유형별 예시

#### 1. `add` - 명령어 추가

온도 대기 명령이 누락된 경우, 해당 위치에 M109/M190 명령을 추가합니다.

```json
{
  "id": "PATCH-001",
  "issue_id": "ISSUE-1",
  "line": 525,
  "action": "add",
  "reason": "M140 전에 M104 S(권장온도) 명령 추가",
  "modified": null,
  "original": "M140 S65",
  "autofix_allowed": true
}
```

**UI 렌더링:**
```diff
  524: M104 S140
  525: M140 S65
+ M190 S65          ← 추가될 명령
  526:
```

---

#### 2. `review` - 수동 검토 필요 (벤더 확장)

Bambu/Orca 슬라이서의 H 파라미터가 포함된 경우, 자동 수정이 위험하여 수동 검토를 권장합니다.

```json
{
  "id": "PATCH-002",
  "issue_id": "ISSUE-2",
  "line": 589,
  "action": "review",
  "reason": "M109 S220(권장 온도) 대기 명령 추가 [BAMBU 벤더 확장 감지: H=140, 신뢰도=high]",
  "modified": null,
  "original": "M109 S25 H140",
  "autofix_allowed": false
}
```

**UI 렌더링:**
- 수정 버튼 **비활성화** (`autofix_allowed: false`)
- "수동 검토 필요" 배지 표시
- 벤더 확장 설명 툴팁: "BAMBU 벤더 확장 감지: H=140"

---

#### 3. `modify` - 기존 라인 수정

온도 값을 변경하거나, M104를 M109로 변경합니다.

```json
{
  "id": "PATCH-004",
  "issue_id": "ISSUE-4",
  "line": 628,
  "action": "review",
  "reason": "M104 S220, M109 S220으로 수정",
  "modified": "M104 S220",
  "original": "M104 S250",
  "autofix_allowed": false
}
```

**UI 렌더링:**
```diff
  627: M109 S220
- 628: M104 S250     ← 원본
+ 628: M104 S220     ← 수정됨 (250→220)
  629: M400
```

---

### 액션 타입별 UI 처리 가이드

| action | UI 표시 | 버튼 상태 | autofix_allowed | 설명 |
|--------|---------|-----------|-----------------|------|
| `add` | ➕ 추가 | 활성화 | `true` | 대상 라인 앞/뒤에 새 명령 삽입 |
| `modify` | 🔄 수정 | 활성화 | `true` | 기존 라인을 새 값으로 대체 |
| `delete` | 🗑️ 삭제 | 활성화 | `true` | 불필요한 라인 제거 |
| `review` | ⚠️ 검토 | **비활성화** | `false` | 수동 검토 필요 (벤더 확장 등) |

---

### 프론트엔드 접근 예시

```typescript
// 패치 목록 순회
response.patch_plan.patches.forEach(patch => {
  console.log(patch.id);              // "PATCH-001"
  console.log(patch.issue_id);        // "ISSUE-1"
  console.log(patch.line);            // 525
  console.log(patch.action);          // "add" | "modify" | "review" | "delete"
  console.log(patch.original);        // "M140 S65"
  console.log(patch.modified);        // null 또는 수정된 라인
  console.log(patch.reason);          // 패치 이유
  console.log(patch.autofix_allowed); // true | false
});

// 자동 적용 가능한 패치만 필터링
const autofixPatches = response.patch_plan.patches.filter(p => p.autofix_allowed);

// review 액션인 패치 (수동 검토 필요)
const reviewPatches = response.patch_plan.patches.filter(p => p.action === 'review');
```

---

### Diff 렌더링 로직

```typescript
interface Patch {
  id: string;
  line: number;
  action: 'add' | 'modify' | 'delete' | 'review';
  original: string;
  modified: string | null;
  reason: string;
  autofix_allowed: boolean;
}

function renderPatchDiff(patch: Patch): JSX.Element {
  const { action, original, modified, line } = patch;

  return (
    <div className="diff-view">
      {/* 원본 라인 */}
      {action === 'delete' || action === 'modify' ? (
        <div className="deleted">- {line}: {original}</div>
      ) : (
        <div className="context">{line}: {original}</div>
      )}

      {/* 수정/추가된 라인 */}
      {action === 'modify' && modified && (
        <div className="added">+ {line}: {modified}</div>
      )}

      {action === 'add' && (
        <div className="added">+ [새 명령 추가 위치]</div>
      )}

      {/* review 액션은 특별 표시 */}
      {action === 'review' && (
        <div className="warning">⚠️ 수동 검토 필요</div>
      )}
    </div>
  );
}

// 자동 적용 버튼 활성화 여부
function canAutoApply(patch: Patch): boolean {
  return patch.autofix_allowed && patch.action !== 'review';
}
```

---

## React 컴포넌트 예시

### IssueCard 컴포넌트

```tsx
interface IssueCardProps {
  issue: CriticalIssue;
  patch?: Patch;
  onViewPatch: (patchId: string) => void;
  onGoToLine: (line: number) => void;
}

function IssueCard({ issue, patch, onViewPatch, onGoToLine }: IssueCardProps) {
  const severityIcon = issue.severity === 'critical' ? '🔴' : '🟡';

  return (
    <div className={`issue-card severity-${issue.severity}`}>
      <div className="issue-header">
        <span className="severity-icon">{severityIcon}</span>
        <span className="issue-id">{issue.id}</span>
        <span className="issue-title">{issue.title}</span>
        <button onClick={() => onGoToLine(issue.line)}>
          Line {issue.line}
        </button>
      </div>

      <p className="issue-description">{issue.description}</p>

      {patch && (
        <div className="patch-info">
          <button onClick={() => onViewPatch(patch.patch_id)}>
            📝 패치 보기
          </button>
          {patch.can_auto_apply ? (
            <span className="auto-apply">✅ 자동 적용 가능</span>
          ) : (
            <span className="manual-review">⚠️ 수동 검토 필요</span>
          )}
          <span className="patch-id">{patch.patch_id}</span>
        </div>
      )}
    </div>
  );
}
```

### PatchDiffViewer 컴포넌트

```tsx
interface PatchDiffViewerProps {
  patch: Patch;
  onApply: (patchId: string) => void;
  onSkip: (patchId: string) => void;
}

function PatchDiffViewer({ patch, onApply, onSkip }: PatchDiffViewerProps) {
  return (
    <div className="patch-diff-viewer">
      <header>
        <h3>🔧 {patch.patch_id}</h3>
        <div className="meta">
          <span className={`action action-${patch.action}`}>
            {patch.action}
          </span>
          <span className={`risk risk-${patch.risk_level}`}>
            위험도: {patch.risk_level}
          </span>
        </div>
      </header>

      <div className="diff-container">
        <div className="original">
          <h4>원본 (Line {patch.line_number})</h4>
          <pre>
            {patch.original_code.context_before.map((line, i) => (
              <div key={i} className="context">{line}</div>
            ))}
            <div className="target-line">► {patch.original_code.line}</div>
            {patch.original_code.context_after.map((line, i) => (
              <div key={i} className="context">{line}</div>
            ))}
          </pre>
        </div>

        <div className="patched">
          <h4>패치 후</h4>
          <pre>
            {patch.patched_code.context_before.slice(-2).map((line, i) => (
              <div key={i} className="context">{line}</div>
            ))}

            {patch.action === 'add_before' && patch.additional_lines.map((line, i) => (
              <div key={i} className="added">+ {line}</div>
            ))}

            {patch.action === 'delete' ? (
              <div className="deleted">- {patch.original_code.line}</div>
            ) : (
              <div className={patch.action === 'modify' ? 'modified' : 'target-line'}>
                {patch.patched_code.line}
              </div>
            )}

            {patch.action === 'add_after' && patch.additional_lines.map((line, i) => (
              <div key={i} className="added">+ {line}</div>
            ))}

            {patch.patched_code.context_after.slice(0, 2).map((line, i) => (
              <div key={i} className="context">{line}</div>
            ))}
          </pre>
        </div>
      </div>

      <p className="explanation">{patch.explanation}</p>

      <div className="actions">
        <button
          className="apply"
          onClick={() => onApply(patch.patch_id)}
          disabled={!patch.can_auto_apply}
        >
          적용
        </button>
        <button className="skip" onClick={() => onSkip(patch.patch_id)}>
          건너뛰기
        </button>
      </div>
    </div>
  );
}
```

---

## 스타일 가이드

### 색상 코드

| 요소 | 색상 | 용도 |
|------|------|------|
| Critical | `#dc3545` (빨강) | 심각한 이슈 |
| Warning | `#ffc107` (노랑) | 주의 필요 |
| Info | `#17a2b8` (파랑) | 정보성 |
| Success | `#28a745` (초록) | 해결됨/적용됨 |
| High Risk | `#dc3545` | 위험도 높음 |
| Medium Risk | `#ffc107` | 위험도 중간 |
| Low Risk | `#28a745` | 위험도 낮음 |

### Diff 하이라이트

```css
.added { background: #e6ffed; color: #22863a; }
.deleted { background: #ffeef0; color: #cb2431; }
.modified { background: #fff3cd; color: #856404; }
.context { color: #6a737d; }
.target-line { background: #fffbdd; font-weight: bold; }
```

---

## API 엔드포인트

### 분석 요청

```
POST /api/analyze
Content-Type: multipart/form-data

Body:
  - file: G-code 파일
  - filament_type: "PLA" | "ABS" | "PETG" | ...
  - analysis_mode: "full" | "summary_only"
```

### 패치 적용

```
POST /api/apply-patches
Content-Type: application/json

Body:
{
  "file_id": "abc123",
  "patches": ["PATCH-001", "PATCH-003", "PATCH-005"]
}

Response:
{
  "success": true,
  "patched_file_url": "/downloads/abc123_patched.gcode",
  "applied_patches": ["PATCH-001", "PATCH-003", "PATCH-005"],
  "skipped_patches": []
}
```

---

## 체크리스트

### 프론트엔드 구현 시 확인사항

- [ ] 이슈 목록에서 `issue.patch_id`로 패치 연결
- [ ] 패치 목록에서 `patch.issue_id`로 이슈 연결
- [ ] `severity`에 따른 색상/아이콘 구분
- [ ] `can_auto_apply` false인 경우 수동 검토 표시
- [ ] `action` 타입별 UI 처리 (modify/add/delete/no_action)
- [ ] `additional_lines` 배열 렌더링 (add_before/add_after)
- [ ] `risk_level`에 따른 경고 표시
- [ ] 라인 번호 클릭 시 에디터 이동
- [ ] 패치 적용/건너뛰기 버튼 동작

---

## 델타 기반 G-code 내보내기 API

### 개요

클라이언트에서 수정한 **델타(변경사항)만** 서버로 전송하면, 서버에서 원본 G-code와 병합하여 스트리밍 다운로드를 제공합니다.

**장점:**
- 메모리 효율적: 클라이언트는 델타만 관리 (~2KB)
- 대용량 지원: 50만 줄 G-code도 문제없이 처리
- 즉시 다운로드: 스트리밍 방식으로 대기 시간 최소화

### 델타 액션 유형

| action | 설명 | 예시 |
|--------|------|------|
| `modify` | 해당 라인 내용 변경 | `M104 S200` → `M104 S210` |
| `delete` | 해당 라인 삭제 | 라인 42 삭제 |
| `insert_before` | 해당 라인 앞에 삽입 | 라인 42 앞에 `G4 P500` 추가 |
| `insert_after` | 해당 라인 뒤에 삽입 | 라인 42 뒤에 `M106 S255` 추가 |

### API 엔드포인트

#### 1. 내보내기 (다운로드)

```
POST /api/v1/gcode/export
Content-Type: application/json

Request:
{
  "analysis_id": "abc123",
  "deltas": [
    {"line_index": 42, "action": "modify", "new_content": "M109 S220"},
    {"line_index": 100, "action": "delete"},
    {"line_index": 50, "action": "insert_after", "new_content": "M190 S65"}
  ],
  "filename": "my_model_modified.gcode",
  "include_header_comment": true
}

Response: StreamingResponse (text/plain)
Headers:
  Content-Disposition: attachment; filename="my_model_modified.gcode"
  X-Applied-Deltas: 3
```

#### 2. 미리보기 (통계만)

```
POST /api/v1/gcode/export/preview
Content-Type: application/json

Request:
{
  "analysis_id": "abc123",
  "deltas": [...]
}

Response:
{
  "analysis_id": "abc123",
  "original_filename": "model.gcode",
  "output_filename": "model_modified.gcode",
  "total_lines": 50000,
  "delta_summary": {
    "total": 5,
    "modify": 2,
    "delete": 1,
    "insert_before": 1,
    "insert_after": 1
  },
  "warnings": [],
  "ready_to_export": true
}
```

### TypeScript 타입 정의

```typescript
// 델타 액션 유형
type DeltaAction = 'modify' | 'delete' | 'insert_before' | 'insert_after';

// 단일 라인 변경사항
interface LineDelta {
  line_index: number;        // 원본 기준 라인 인덱스 (0-based)
  action: DeltaAction;
  original_content?: string; // modify/delete 시 원본 (검증용)
  new_content?: string;      // modify/insert 시 새 내용
  reason?: string;           // 변경 이유 (선택적)
  patch_id?: string;         // 연결된 패치 ID (선택적)
}

// 내보내기 요청
interface DeltaExportRequest {
  analysis_id: string;
  deltas: LineDelta[];
  filename?: string;
  include_header_comment?: boolean;
}
```

### React 연동 예시

```tsx
import { useState } from 'react';

interface LineDelta {
  line_index: number;
  action: 'modify' | 'delete' | 'insert_before' | 'insert_after';
  original_content?: string;
  new_content?: string;
  reason?: string;
  patch_id?: string;
}

// 델타 상태 관리 훅
function useDeltaManager() {
  const [deltas, setDeltas] = useState<LineDelta[]>([]);

  // 패치를 델타로 변환하여 추가
  const applyPatch = (patch: Patch) => {
    const delta: LineDelta = {
      line_index: patch.line - 1,  // 0-based로 변환
      action: patch.action === 'add'
        ? (patch.position === 'before' ? 'insert_before' : 'insert_after')
        : patch.action === 'modify' ? 'modify' : 'delete',
      original_content: patch.original,
      new_content: patch.modified || undefined,
      reason: patch.reason,
      patch_id: patch.id
    };
    setDeltas(prev => [...prev, delta]);
  };

  // 델타 제거 (사용자가 취소한 경우)
  const removeDelta = (lineIndex: number) => {
    setDeltas(prev => prev.filter(d => d.line_index !== lineIndex));
  };

  // 모든 델타 초기화
  const clearDeltas = () => setDeltas([]);

  return { deltas, applyPatch, removeDelta, clearDeltas };
}

// 내보내기 버튼 컴포넌트
function ExportButton({ analysisId, deltas, originalFilename }: {
  analysisId: string;
  deltas: LineDelta[];
  originalFilename: string;
}) {
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    if (deltas.length === 0) {
      alert('적용할 변경사항이 없습니다.');
      return;
    }

    setIsExporting(true);
    try {
      const response = await fetch('/api/v1/gcode/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analysis_id: analysisId,
          deltas: deltas,
          filename: `${originalFilename.replace('.gcode', '')}_modified.gcode`,
          include_header_comment: true
        })
      });

      if (!response.ok) {
        throw new Error('내보내기 실패');
      }

      // 스트리밍 다운로드
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = response.headers.get('Content-Disposition')
        ?.split('filename=')[1]?.replace(/"/g, '') || 'modified.gcode';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export failed:', error);
      alert('내보내기 중 오류가 발생했습니다.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={isExporting || deltas.length === 0}
      className="export-button"
    >
      {isExporting ? '내보내는 중...' : `내보내기 (${deltas.length}개 변경)`}
    </button>
  );
}
```

### 메모리 비교

| 항목 | 기존 방식 | 델타 방식 |
|------|-----------|-----------|
| 클라이언트 메모리 | ~50MB (전체 문자열) | ~2KB (델타만) |
| 서버 메모리 | ~100MB (전체 로드) | ~10KB (스트리밍) |
| 다운로드 속도 | 전체 join 후 | 즉시 스트리밍 |
| 50만 줄 처리 | 브라우저 멈춤 가능 | 문제 없음 |
