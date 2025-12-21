# Chat API 프론트엔드 통합 가이드

## 개요

Chat API는 단일 엔드포인트로 다양한 3D 프린팅 관련 기능을 제공합니다.
프론트엔드는 사용자 메시지와 첨부 파일을 보내면, 백엔드가 자동으로 의도를 파악하고 적절한 도구를 실행합니다.

---

## 기본 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                        프론트엔드 흐름                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 사용자 입력                                                       │
│     ↓                                                                │
│  2. POST /api/v1/chat 요청                                           │
│     ↓                                                                │
│  3. 응답 수신 (intent, tool_result, response)                         │
│     ↓                                                                │
│  4. intent별 UI 처리                                                  │
│     ├─ gcode_analysis → 3D 뷰어 렌더링 + 폴링 시작                     │
│     ├─ troubleshoot → 솔루션 카드 렌더링                               │
│     ├─ modelling_* → 3D 모델 상태 표시                                 │
│     └─ general_question → 마크다운 텍스트 렌더링                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. 기본 API 호출

### Endpoint

```
POST /api/v1/chat
Content-Type: application/json
```

### 기본 TypeScript 인터페이스

```typescript
// 요청 타입
interface ChatRequest {
  user_id: string;                    // 필수: 사용자 ID
  message: string;                    // 필수: 사용자 메시지
  user_plan?: 'free' | 'starter' | 'pro' | 'enterprise';
  conversation_id?: string;           // 대화 세션 유지용
  conversation_history?: { role: string; content: string }[];
  attachments?: Attachment[];
  selected_tool?: 'gcode' | 'troubleshoot' | 'modelling' | 'resolve_issue';
  selected_model?: string;
  printer_info?: PrinterInfo;
  filament_type?: string;
  analysis_id?: string;               // 이슈 해결 시 필요
  issue_to_resolve?: Issue;           // 이슈 해결 시 필요
  language?: 'ko' | 'en';
}

interface Attachment {
  type: 'gcode' | 'image' | 'stl' | 'text';
  content: string;    // Base64 인코딩된 콘텐츠
  filename: string;
  mime_type?: string;
}

// 응답 타입
interface ChatResponse {
  conversation_id: string;
  message_id: string;
  timestamp: string;
  intent: ChatIntent;
  confidence: number;
  response: string;           // 마크다운 형식 텍스트
  tool_result?: ToolResult;
  suggested_actions: SuggestedAction[];
  token_usage: TokenUsage;
  analysis_id?: string;       // G-code 분석 시
}

type ChatIntent =
  | 'gcode_analysis'      // G-code 파일 분석
  | 'gcode_general'       // G-code 일반 질문
  | 'gcode_issue_resolve' // G-code 이슈 해결
  | 'troubleshoot'        // 프린터 문제 진단
  | 'modelling_text'      // Text-to-3D
  | 'modelling_image'     // Image-to-3D
  | 'general_question'    // 일반 질문
  | 'greeting'            // 인사
  | 'help';               // 도움말
```

---

## 2. 사용 시나리오별 구현

### 2.1 일반 질문 (텍스트만)

```typescript
// 가장 간단한 케이스
async function sendMessage(message: string) {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: getUserId(),
      message: message,
      language: 'ko'
    })
  });

  const data: ChatResponse = await response.json();

  // 마크다운 응답을 UI에 렌더링
  renderMarkdown(data.response);
}
```

### 2.2 G-code 파일 분석

```typescript
async function analyzeGcode(file: File) {
  // 1. 파일을 Base64로 인코딩
  const base64Content = await fileToBase64(file);

  // 2. Chat API 요청
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: getUserId(),
      message: '이 G-code 파일 분석해줘',
      attachments: [{
        type: 'gcode',
        content: base64Content,
        filename: file.name
      }],
      selected_tool: 'gcode',  // 명시적 도구 선택 (선택사항)
      language: 'ko'
    })
  });

  const data: ChatResponse = await response.json();

  // 3. 즉시 응답 처리
  if (data.intent === 'gcode_analysis' && data.tool_result?.success) {
    const { segments, analysis_id } = data.tool_result;

    // 3D 뷰어에 세그먼트 렌더링
    render3DViewer(segments);

    // LLM 분석 완료까지 폴링 시작
    startPolling(analysis_id);
  }
}

// Base64 인코딩 헬퍼
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
```

### 2.3 분석 상태 폴링

```typescript
async function startPolling(analysisId: string) {
  const pollInterval = 2000; // 2초마다
  const maxAttempts = 60;    // 최대 2분
  let attempts = 0;

  const poll = async () => {
    const response = await fetch(`/api/v1/gcode/analysis/${analysisId}`);
    const data = await response.json();

    // 진행률 업데이트
    updateProgress(data.progress, data.progress_message);

    if (data.status === 'completed') {
      // 분석 완료 - 결과 표시
      displayAnalysisResult(data.result);
      return;
    }

    if (data.status === 'error') {
      // 오류 처리
      showError(data.error);
      return;
    }

    // 진행 중 - 계속 폴링
    if (++attempts < maxAttempts) {
      setTimeout(poll, pollInterval);
    }
  };

  poll();
}
```

### 2.4 세그먼트 데이터 디코딩 (3D 뷰어용)

```typescript
// Base64 → Float32Array 디코딩
function decodeSegmentData(base64String: string): Float32Array {
  const binaryString = atob(base64String);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Float32Array(bytes.buffer);
}

// 3D 뷰어 렌더링 (Three.js 예시)
function render3DViewer(segments: GCodeSegments) {
  const { layers, metadata } = segments;

  layers.forEach(layer => {
    // 압출 경로 (빨간색)
    const extrusionPoints = decodeSegmentData(layer.extrusionData);
    const extrusionGeometry = createLineGeometry(extrusionPoints);
    scene.add(new THREE.Line(extrusionGeometry, redMaterial));

    // 이동 경로 (파란색, 선택적)
    const travelPoints = decodeSegmentData(layer.travelData);
    const travelGeometry = createLineGeometry(travelPoints);
    scene.add(new THREE.Line(travelGeometry, blueMaterial));
  });
}

function createLineGeometry(points: Float32Array): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(points, 3));
  return geometry;
}
```

### 2.5 프린터 문제 진단 (이미지 첨부)

```typescript
async function diagnoseWithImage(symptom: string, imageFile: File) {
  const base64Image = await fileToBase64(imageFile);

  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: getUserId(),
      message: symptom,  // "첫 레이어가 베드에 안 붙어요"
      attachments: [{
        type: 'image',
        content: base64Image,
        filename: imageFile.name,
        mime_type: imageFile.type
      }],
      selected_tool: 'troubleshoot',
      printer_info: {
        manufacturer: 'Creality',
        model: 'Ender 3'
      },
      filament_type: 'PLA',
      language: 'ko'
    })
  });

  const data: ChatResponse = await response.json();

  if (data.intent === 'troubleshoot' && data.tool_result?.success) {
    // 솔루션 카드 렌더링
    renderTroubleshootResult(data.tool_result.data);
  }
}
```

### 2.6 G-code 이슈 해결 (AI 해결하기)

```typescript
async function resolveIssue(analysisId: string, issue: Issue, gcodeContext: string) {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: getUserId(),
      message: `${issue.title} 문제를 해결해줘`,
      selected_tool: 'resolve_issue',
      analysis_id: analysisId,
      issue_to_resolve: {
        line: issue.line,
        type: issue.type,
        severity: issue.severity,
        title: issue.title,
        description: issue.description
      },
      language: 'ko'
    })
  });

  const data: ChatResponse = await response.json();

  if (data.intent === 'gcode_issue_resolve' && data.tool_result?.success) {
    // 해결 방법 표시
    displayResolution(data.tool_result.data.resolution);
  }
}
```

---

## 3. UI 컴포넌트 구조

### 3.1 채팅 인터페이스 상태 관리

```typescript
interface ChatState {
  messages: ChatMessage[];
  currentAnalysis: {
    id: string;
    status: 'pending' | 'running' | 'completed' | 'error';
    progress: number;
    segments?: GCodeSegments;
    result?: AnalysisResult;
  } | null;
  isLoading: boolean;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  intent?: ChatIntent;
  toolResult?: ToolResult;
  suggestedActions?: SuggestedAction[];
}
```

### 3.2 Intent별 UI 렌더링

```tsx
function MessageRenderer({ message }: { message: ChatMessage }) {
  // 기본 텍스트 응답
  const textContent = <MarkdownRenderer content={message.content} />;

  // Intent별 추가 UI
  switch (message.intent) {
    case 'gcode_analysis':
      return (
        <div>
          {textContent}
          <GCodeViewer3D segments={message.toolResult?.segments} />
          <AnalysisProgress analysisId={message.toolResult?.analysis_id} />
        </div>
      );

    case 'troubleshoot':
      return (
        <div>
          {textContent}
          <SolutionCards solutions={message.toolResult?.data?.solutions} />
          <ReferenceLinks refs={message.toolResult?.data?.references} />
        </div>
      );

    case 'modelling_text':
    case 'modelling_image':
      return (
        <div>
          {textContent}
          <ModelPreview3D modelUrl={message.toolResult?.data?.glb_url} />
        </div>
      );

    default:
      return textContent;
  }
}
```

### 3.3 추천 액션 버튼

```tsx
function SuggestedActionsBar({ actions }: { actions: SuggestedAction[] }) {
  const handleAction = async (action: SuggestedAction) => {
    switch (action.action) {
      case 'check_status':
        // 분석 상태 확인
        await checkAnalysisStatus(action.data.analysis_id);
        break;

      case 'explore_layers':
        // 레이어 탐색 모드 활성화
        activateLayerExplorer(action.data.analysis_id);
        break;

      case 'apply_fix':
        // 수정 적용
        await applyFix(action.data);
        break;
    }
  };

  return (
    <div className="suggested-actions">
      {actions.map(action => (
        <button
          key={action.action}
          onClick={() => handleAction(action)}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
```

---

## 4. 대화 히스토리 관리

### 4.1 컨텍스트 유지

```typescript
class ChatSession {
  private conversationId: string | null = null;
  private history: { role: string; content: string }[] = [];

  async sendMessage(message: string, attachments?: Attachment[]) {
    const response = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: getUserId(),
        message,
        conversation_id: this.conversationId,
        conversation_history: this.history.slice(-10), // 최근 10개만
        attachments,
        language: 'ko'
      })
    });

    const data: ChatResponse = await response.json();

    // 세션 ID 저장 (첫 응답 시)
    if (!this.conversationId) {
      this.conversationId = data.conversation_id;
    }

    // 히스토리 업데이트
    this.history.push(
      { role: 'user', content: message },
      { role: 'assistant', content: data.response }
    );

    return data;
  }

  reset() {
    this.conversationId = null;
    this.history = [];
  }
}
```

---

## 5. 에러 처리

### 5.1 HTTP 상태 코드별 처리

```typescript
async function handleChatResponse(response: Response) {
  if (response.ok) {
    return await response.json();
  }

  switch (response.status) {
    case 400:
      throw new Error('잘못된 요청입니다. 입력을 확인해주세요.');

    case 404:
      throw new Error('분석 데이터를 찾을 수 없습니다.');

    case 429:
      const retryAfter = response.headers.get('Retry-After');
      throw new Error(`요청 한도 초과. ${retryAfter}초 후 다시 시도해주세요.`);

    case 500:
      const error = await response.json();
      throw new Error(error.detail || '서버 오류가 발생했습니다.');

    default:
      throw new Error('알 수 없는 오류가 발생했습니다.');
  }
}
```

### 5.2 Rate Limit 처리

```typescript
async function sendWithRetry(request: ChatRequest, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });

      if (response.status === 429) {
        const retryAfter = parseInt(response.headers.get('Retry-After') || '5');
        showRateLimitWarning(retryAfter);
        await sleep(retryAfter * 1000);
        continue;
      }

      return await handleChatResponse(response);
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(1000 * (i + 1)); // 백오프
    }
  }
}
```

---

## 6. 파일 첨부 처리

### 6.1 파일 타입 감지 및 인코딩

```typescript
function detectAttachmentType(file: File): AttachmentType {
  const ext = file.name.split('.').pop()?.toLowerCase();

  if (ext === 'gcode' || ext === 'gco' || ext === 'nc') {
    return 'gcode';
  }
  if (['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext || '')) {
    return 'image';
  }
  if (ext === 'stl') {
    return 'stl';
  }
  return 'text';
}

async function createAttachment(file: File): Promise<Attachment> {
  const type = detectAttachmentType(file);
  const content = await fileToBase64(file);

  return {
    type,
    content,
    filename: file.name,
    mime_type: file.type || undefined
  };
}
```

### 6.2 드래그 앤 드롭 처리

```typescript
function setupDropZone(element: HTMLElement, onFiles: (files: File[]) => void) {
  element.addEventListener('dragover', (e) => {
    e.preventDefault();
    element.classList.add('drag-over');
  });

  element.addEventListener('dragleave', () => {
    element.classList.remove('drag-over');
  });

  element.addEventListener('drop', async (e) => {
    e.preventDefault();
    element.classList.remove('drag-over');

    const files = Array.from(e.dataTransfer?.files || []);
    onFiles(files);
  });
}
```

---

## 7. API 엔드포인트 요약

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/chat` | POST | 메인 채팅 API |
| `/api/v1/chat/intents` | GET | 지원 의도 목록 |
| `/api/v1/chat/attachment-types` | GET | 지원 첨부 파일 타입 |
| `/api/v1/chat/models` | GET | 지원 LLM 모델 목록 |
| `/api/v1/chat/plans` | GET | 사용자 플랜별 기능 |
| `/api/v1/gcode/analysis/{id}` | GET | G-code 분석 상태/결과 조회 |
| `/api/v1/gcode/analysis/{id}/segments` | GET | 세그먼트 데이터만 조회 |
| `/api/v1/gcode/analysis/{id}/dashboard` | GET | 대시보드용 플랫 데이터 |
| `/api/v1/gcode/analysis/{id}/resolve-issue` | POST | G-code 이슈 해결 |

---

## 8. 완전한 React 예시

```tsx
import React, { useState, useCallback } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
  toolResult?: any;
}

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const sendMessage = useCallback(async () => {
    if (!input.trim() && files.length === 0) return;

    setIsLoading(true);

    // 사용자 메시지 추가
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');

    try {
      // 첨부 파일 처리
      const attachments = await Promise.all(
        files.map(async (file) => ({
          type: detectAttachmentType(file),
          content: await fileToBase64(file),
          filename: file.name,
          mime_type: file.type
        }))
      );
      setFiles([]);

      // API 요청
      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'user_123',
          message: input,
          conversation_id: conversationId,
          attachments: attachments.length > 0 ? attachments : undefined,
          language: 'ko'
        })
      });

      const data = await response.json();

      // 세션 ID 저장
      if (!conversationId) {
        setConversationId(data.conversation_id);
      }

      // AI 응답 추가
      const assistantMessage: Message = {
        id: data.message_id,
        role: 'assistant',
        content: data.response,
        intent: data.intent,
        toolResult: data.tool_result
      };
      setMessages(prev => [...prev, assistantMessage]);

      // G-code 분석인 경우 폴링 시작
      if (data.intent === 'gcode_analysis' && data.analysis_id) {
        startPolling(data.analysis_id);
      }

    } catch (error) {
      console.error('Chat error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [input, files, conversationId]);

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      <div className="input-area">
        <FileDropZone files={files} onFilesChange={setFiles} />
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyPress={e => e.key === 'Enter' && sendMessage()}
          placeholder="메시지를 입력하세요..."
          disabled={isLoading}
        />
        <button onClick={sendMessage} disabled={isLoading}>
          {isLoading ? '전송 중...' : '전송'}
        </button>
      </div>
    </div>
  );
}
```

---

## 9. LLM 분석 결과 구조 (완료 시)

분석이 `status: "completed"`가 되면 `result` 필드에 상세 분석 결과가 포함됩니다.

### 9.1 전체 구조

```typescript
interface AnalysisResult {
  // 종합 요약 (Python 통계 기반)
  comprehensive_summary: ComprehensiveSummary;

  // 프린팅 정보 (LLM 기반)
  printing_info: PrintingInfo;

  // 최종 요약
  final_summary: FinalSummary;

  // 발견된 이슈 목록 (개별 이슈)
  issues_found: Issue[];

  // 전문가 평가 (LLM 분석 종합)
  expert_assessment: ExpertAssessment;

  // 패치 계획 (수정 제안)
  patch_plan?: PatchPlan;

  // 토큰 사용량
  token_usage: TokenUsage;

  // 분석 타임라인
  timeline: TimelineEntry[];
}
```

### 9.2 ExpertAssessment (전문가 평가 - 핵심)

```typescript
interface ExpertAssessment {
  // 품질 점수 (0-100)
  quality_score: number;

  // 품질 등급 (S, A, B, C, F)
  quality_grade: string;

  // 출력 특성
  print_characteristics: {
    complexity: 'High' | 'Medium' | 'Low';    // 복잡도
    difficulty: 'Advanced' | 'Intermediate' | 'Beginner';  // 난이도
    tags: string[];  // ["Support Heavy", "High Retraction", "Stable Temp"]
  };

  // 전체 총평 (300자 이내)
  summary_text: string;

  // 체크포인트별 상태
  check_points: {
    temperature: CheckPoint;
    speed: CheckPoint;
    retraction: CheckPoint;
    structure?: CheckPoint;
    [key: string]: CheckPoint | undefined;
  };

  // 중요 이슈 목록 (그룹화된 이슈)
  critical_issues: IssueDetail[];

  // 전체 권장사항
  overall_recommendations: string[];
}

interface CheckPoint {
  status: 'ok' | 'warning' | 'error';
  comment: string;  // 한 줄 평가 (30자 이내)
}

interface IssueDetail {
  id: string;           // "ISSUE-001"
  line: number;         // 발생 라인 번호
  type: string;         // 이슈 유형 코드
  severity: Severity;   // 심각도
  title: string;        // 문제 제목 (30자 이내)
  description: string;  // 상세 설명 (50자 이내)
  fix_proposal: string; // 수정 제안 (50자 이내)
}
```

### 9.3 품질 등급 기준

| 등급 | 점수 | 기준 | UI 색상 |
|------|------|------|---------|
| **S** | 90-100 | 이슈 없음. 바로 출력 가능. | 🟢 Green |
| **A** | 75-89 | 경미한 이슈만 있음 (low/medium). 출력 가능. | 🔵 Blue |
| **B** | 60-74 | 경고 다수 또는 심각(high) 이슈 1개. 수정 권장. | 🟡 Yellow |
| **C** | 40-59 | 심각(high) 이슈 2-3개. 수정 필수. | 🟠 Orange |
| **F** | 0-39 | **치명적(critical) 이슈** 또는 심각 이슈 4개+. 출력 금지. | 🔴 Red |

### 9.4 이슈 심각도 (Severity)

```typescript
type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
```

| Severity | 의미 | 점수 영향 | UI 표시 |
|----------|------|----------|---------|
| **critical** | 즉시 출력 금지, 재슬라이싱 필수 | -60점 이상 (즉시 F등급) | 🔴 빨강 배지, 경고 아이콘 |
| **high** | 출력 실패 가능성 높음, 수정 필수 | -20점 | 🟠 주황 배지 |
| **medium** | 출력 품질 저하 가능, 수정 권장 | -7점 | 🟡 노랑 배지 |
| **low** | 경미한 문제, 선택적 수정 | -3점 | 🔵 파랑 배지 |
| **info** | 정보성 알림, 감점 없음 | 0점 | ⚪ 회색 배지 |

### 9.5 issues_found (개별 이슈 목록)

```typescript
interface Issue {
  // 기본 정보
  line: number;              // 이슈 발생 라인 번호
  type: string;              // 이슈 유형 코드
  severity: Severity;        // 심각도

  // 분석 결과
  has_issue: boolean;        // 실제 이슈 여부 (false면 정상)
  title: string;             // 이슈 제목
  description: string;       // 상세 설명
  fix_proposal?: string;     // 수정 제안

  // 컨텍스트
  source: 'temperature' | 'motion' | 'structure' | 'rule';  // 탐지 출처
  layer?: number;            // 해당 레이어 번호
  position?: {               // 위치 정보
    x?: number;
    y?: number;
    z?: number;
  };

  // 제조사 확장 코드 관련
  vendor_extension?: boolean;  // 제조사 확장 코드 여부
  h_value?: number;            // Bambu Lab H 파라미터 값

  // 자동 수정 가능 여부
  autofix_allowed: boolean;    // false면 수동 검토 필요

  // 원본 데이터
  original_line?: string;      // 원본 G-code 라인
  context_before?: string[];   // 이전 라인들
  context_after?: string[];    // 이후 라인들
}
```

### 9.6 이슈 유형 (Type) 목록

```typescript
// 온도 관련
type TempIssueType =
  | 'cold_extrusion'        // 저온 압출 (노즐 가열 전 압출)
  | 'early_temp_off'        // 조기 온도 OFF
  | 'rapid_temp_change'     // 급격한 온도 변화
  | 'low_temp'              // 저온 설정
  | 'bed_temp_off_early'    // 베드 조기 OFF
  | 'missing_bed_temp'      // 베드 온도 미설정
  | 'missing_temp_wait';    // M109 없이 압출 시작

// 속도 관련
type SpeedIssueType =
  | 'excessive_speed'       // 과도한 속도
  | 'inconsistent_speed'    // 일관성 없는 속도
  | 'zero_speed_extrusion'; // 속도 0에서 압출

// 리트랙션 관련
type RetractionIssueType =
  | 'excessive_retraction'  // 과도한 리트랙션
  | 'missing_retraction';   // 리트랙션 누락

// 구조 관련
type StructureIssueType =
  | 'missing_start_gcode'   // 시작 G-code 누락
  | 'missing_end_gcode'     // 종료 G-code 누락
  | 'duplicate_commands';   // 중복 명령어
```

### 9.7 ComprehensiveSummary (종합 요약)

```typescript
interface ComprehensiveSummary {
  // 파일 정보
  file_name?: string;
  total_lines: number;
  slicer_info?: string;
  filament_type?: string;

  // 온도 정보
  temperature: {
    nozzle_min: number;
    nozzle_max: number;
    nozzle_avg: number;
    nozzle_changes: number;  // 온도 변경 횟수
    bed_min: number;
    bed_max: number;
    bed_avg: number;
  };

  // 피드레이트 정보
  feed_rate: {
    min_speed: number;
    max_speed: number;
    avg_speed: number;
    travel_speed_avg: number;
    print_speed_avg: number;
  };

  // 압출 정보
  extrusion: {
    total_extrusion: number;      // mm
    total_filament_used: number;  // meters
    retraction_count: number;
    avg_retraction: number;
  };

  // 레이어 정보
  layer: {
    total_layers: number;
    avg_layer_height: number;
    first_layer_height: number;
  };

  // 서포트 정보
  support: {
    has_support: boolean;
    support_ratio: number;  // %
    support_layers: number;
  };

  // 팬 정보
  fan: {
    max_fan_speed: number;  // 0-255
    fan_on_layer: number;
  };

  // 출력 시간
  print_time: {
    estimated_seconds: number;
    formatted_time: string;  // "01:51:06"
  };

  // 구간 정보
  start_gcode_lines: number;
  body_lines: number;
  end_gcode_lines: number;
}
```

### 9.8 PrintingInfo (프린팅 개요)

```typescript
interface PrintingInfo {
  // LLM 생성 개요
  overview: string;

  // 특성
  characteristics: {
    complexity: string;
    difficulty: string;
    tags: string[];
    estimated_quality: string;  // "Grade A (85)"
  };

  // 분석 코멘트
  temperature_analysis: string;
  speed_analysis: string;
  material_usage: string;

  // 경고 및 권장사항
  warnings: string[];
  recommendations: string[];

  // 총평
  summary_text: string;
}
```

### 9.9 UI 렌더링 예시

```tsx
function AnalysisResultPanel({ result }: { result: AnalysisResult }) {
  const { expert_assessment, issues_found, comprehensive_summary } = result;

  return (
    <div className="analysis-result">
      {/* 품질 점수 카드 */}
      <QualityScoreCard
        score={expert_assessment.quality_score}
        grade={expert_assessment.quality_grade}
      />

      {/* 체크포인트 */}
      <CheckPointsGrid checkPoints={expert_assessment.check_points} />

      {/* 이슈 목록 (심각도별 그룹화) */}
      <IssuesList issues={expert_assessment.critical_issues} />

      {/* 종합 요약 */}
      <SummaryCard summary={expert_assessment.summary_text} />

      {/* 권장사항 */}
      <RecommendationsList items={expert_assessment.overall_recommendations} />

      {/* 상세 통계 (접이식) */}
      <CollapsibleStats summary={comprehensive_summary} />
    </div>
  );
}

// 품질 점수 카드
function QualityScoreCard({ score, grade }: { score: number; grade: string }) {
  const gradeColors = {
    S: 'bg-green-500',
    A: 'bg-blue-500',
    B: 'bg-yellow-500',
    C: 'bg-orange-500',
    F: 'bg-red-500'
  };

  return (
    <div className={`quality-card ${gradeColors[grade]}`}>
      <div className="score">{score}</div>
      <div className="grade">Grade {grade}</div>
    </div>
  );
}

// 이슈 목록 (심각도별 그룹화)
function IssuesList({ issues }: { issues: IssueDetail[] }) {
  const grouped = groupBy(issues, 'severity');
  const order = ['critical', 'high', 'medium', 'low', 'info'];

  return (
    <div className="issues-list">
      {order.map(severity => {
        const items = grouped[severity] || [];
        if (items.length === 0) return null;

        return (
          <div key={severity} className={`issue-group ${severity}`}>
            <h4>{getSeverityLabel(severity)} ({items.length})</h4>
            {items.map(issue => (
              <IssueCard key={issue.id} issue={issue} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

### 9.10 폴링 응답 예시 (완료 시)

```json
{
  "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
  "status": "completed",
  "progress": 100,
  "current_step": "completed",
  "progress_message": "분석 완료",
  "timeline": [
    {"step": 1, "label": "세그먼트 추출", "status": "done"},
    {"step": 2, "label": "온도 분석", "status": "done"},
    {"step": 3, "label": "LLM 분석", "status": "done"},
    {"step": 4, "label": "전문가 평가", "status": "done"}
  ],
  "result": {
    "comprehensive_summary": {
      "total_lines": 125432,
      "temperature": {
        "nozzle_min": 200,
        "nozzle_max": 210,
        "bed_min": 60,
        "bed_max": 60
      },
      "layer": {
        "total_layers": 998,
        "avg_layer_height": 0.1
      },
      "print_time": {
        "formatted_time": "01:51:06",
        "estimated_seconds": 6666
      }
    },
    "expert_assessment": {
      "quality_score": 85,
      "quality_grade": "A",
      "print_characteristics": {
        "complexity": "Medium",
        "difficulty": "Intermediate",
        "tags": ["Stable Temp", "Normal Retraction", "Support Used"]
      },
      "summary_text": "PLA 소재 중간 복잡도 모델입니다. 온도 설정이 안정적이며 출력 품질이 양호할 것으로 예상됩니다.",
      "check_points": {
        "temperature": {"status": "ok", "comment": "노즐 210°C 안정 유지"},
        "speed": {"status": "ok", "comment": "적정 속도 범위"},
        "retraction": {"status": "warning", "comment": "리트랙션 다소 많음"}
      },
      "critical_issues": [
        {
          "id": "ISSUE-1",
          "line": 137,
          "type": "cold_extrusion",
          "severity": "medium",
          "title": "저온 압출 확인 필요",
          "description": "노즐 온도 도달 전 압출 명령이 감지되었습니다.",
          "fix_proposal": "M109 S200 대기 명령 추가 권장"
        }
      ],
      "overall_recommendations": [
        "첫 레이어 속도를 30mm/s로 설정 권장",
        "리트랙션 거리를 0.5mm 줄여보세요",
        "출력 전 베드 레벨링 확인"
      ]
    },
    "issues_found": [
      {
        "line": 137,
        "type": "cold_extrusion",
        "severity": "medium",
        "has_issue": true,
        "title": "저온 압출 확인 필요",
        "source": "temperature",
        "autofix_allowed": false,
        "vendor_extension": true
      }
    ],
    "token_usage": {
      "input_tokens": 15420,
      "output_tokens": 2340,
      "total_tokens": 17760
    }
  },
  "error": null
}
```

---

## 10. 이슈 해결하기 API (AI 해결하기)

G-code 분석 결과에서 발견된 이슈에 대해 AI가 상세 분석 및 해결 방법을 제공하는 기능입니다.

### 10.1 API 엔드포인트

이슈 해결 API는 두 가지 방식으로 호출할 수 있습니다.

| 엔드포인트 | 용도 |
|------------|------|
| `POST /api/v1/gcode/analysis/{analysis_id}/resolve-issue` | 분석 ID로 호출 (서버에서 G-code 컨텍스트 추출) |
| `POST /api/v1/gcode/resolve-issue` | 독립 호출 (클라이언트에서 G-code 컨텍스트 직접 전달) |

### 10.2 요청 방법

#### 방법 1: 분석 ID 기반 호출 (권장)

```typescript
const resolveIssue = async (analysisId: string, issue: Issue) => {
  const response = await fetch(`/api/v1/gcode/analysis/${analysisId}/resolve-issue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis_id: analysisId,
      issue: issue,                    // 해결할 이슈 객체
      conversation_id: 'conv_abc123',  // 선택: 대화 세션 ID
      language: 'ko'
    })
  });
  return response.json();
};
```

#### 방법 2: 독립 호출 (G-code 컨텍스트 직접 전달)

```typescript
const resolveIssueStandalone = async (issue: Issue, gcodeContext: string) => {
  const response = await fetch('/api/v1/gcode/resolve-issue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis_id: 'optional-id',      // 선택
      issue: issue,
      gcode_context: gcodeContext,     // 앞뒤 50줄 (총 100줄) 컨텍스트
      language: 'ko'
    })
  });
  return response.json();
};
```

### 10.3 요청 파라미터

```typescript
interface IssueResolveRequest {
  analysis_id: string;               // 분석 ID
  conversation_id?: string;          // 대화 세션 ID (선택)
  issue: Issue;                      // 해결할 이슈 객체
  gcode_context?: string;            // 클라이언트 전달 G-code 컨텍스트 (앞뒤 50줄)
  language?: 'ko' | 'en';            // 응답 언어
}

// 독립 이슈 (단일 라인)
interface SingleIssue {
  id: string;                        // "ISSUE-1"
  line: number;                      // 문제 라인 번호
  type: string;                      // 이슈 타입
  severity: string;                  // critical|high|medium|low
  title: string;                     // 이슈 제목
  description: string;               // 상세 설명
  gcode_context?: string;            // 주변 G-code (선택)
}

// 그룹 이슈 (동일 유형 여러 건)
interface GroupedIssue {
  id: string;                        // "ISSUE-1"
  type: string;                      // 이슈 타입
  severity: string;
  title: string;
  description: string;
  count: number;                     // 총 건수
  is_grouped: true;                  // 그룹 이슈 표시
  lines: number[];                   // [524, 589, 746, ...]
  all_issues: SingleIssue[];         // 개별 이슈 배열
}
```

### 10.4 응답 구조

```typescript
// REST API 응답
interface IssueResolveResponse {
  success: boolean;
  conversation_id: string;           // 대화 세션 ID
  analysis_id: string;               // 분석 ID
  issue_line: number;                // 이슈 라인 번호
  resolution: IssueResolution;       // AI 분석 결과
  updated_issue: UpdatedIssue;       // 업데이트된 이슈
}

// IssueResolution (3섹션 구조)
interface IssueResolution {
  explanation: Explanation;          // 1. 문제 해설
  solution: Solution;                // 2. 해결 방안
  tips: string[];                    // 3. 추가 팁
}
```

### 10.5 Explanation (문제 해설)

```typescript
interface Explanation {
  summary: string;          // 핵심 설명 (1-2문장)
  cause: string;            // 원인 분석 (2-3문장)
  is_false_positive: boolean;  // 오탐 여부 (true면 실제 문제 아님)
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical';
}
```

**오탐 처리:**
- `is_false_positive: true` → 실제 문제가 아님 (무시 가능)
- `severity: 'none'` → 조치 불필요

### 10.6 Solution (해결 방안)

```typescript
interface Solution {
  action_needed: boolean;      // 조치 필요 여부
  steps: string[];             // 해결 단계 (순서대로)
  code_fix?: CodeFix;          // 대표 코드 수정 (1건)
  code_fixes?: CodeFix[];      // 모든 코드 수정 (배열)
}

interface CodeFix {
  has_fix: boolean;            // 수정 가능 여부
  line_number: number | null;  // 라인 번호
  original: string | null;     // 원본 코드 (형식: "라인번호: G-code")
  fixed: string | null;        // 수정 코드 (형식: "라인번호: G-code")
}
```

**code_fix vs code_fixes:**

| 이슈 유형 | code_fix | code_fixes |
|-----------|----------|------------|
| 독립 이슈 (1건) | 해당 수정 | 1개 배열 `[{...}]` |
| 그룹 이슈 (N건) | 대표 (첫 번째) | 모든 수정 `[{...}, {...}]` |

```typescript
// 예시: 그룹 이슈 응답
{
  "solution": {
    "action_needed": true,
    "steps": ["노즐 온도 확인", "M109 S200 추가"],
    "code_fix": {
      "has_fix": true,
      "line_number": 524,
      "original": "524: G1 X100 Y100 E50",
      "fixed": "524: M109 S200\n525: G1 X100 Y100 E50"
    },
    "code_fixes": [
      {
        "has_fix": true,
        "line_number": 524,
        "original": "524: G1 X100 Y100 E50",
        "fixed": "524: M109 S200\n525: G1 X100 Y100 E50"
      },
      {
        "has_fix": true,
        "line_number": 589,
        "original": "589: G1 X120 Y80 E52",
        "fixed": "589: M109 S200\n590: G1 X120 Y80 E52"
      }
    ]
  }
}
```

### 10.7 Updated Issue (업데이트된 이슈)

AI 분석 후 원본 이슈가 업데이트됩니다.

```typescript
interface UpdatedIssue extends OriginalIssue {
  // 오탐 관련
  has_issue: boolean;           // false면 문제 아님
  is_false_positive: boolean;   // 오탐 여부
  false_positive_reason?: string;  // 오탐 사유

  // 심각도 (재평가됨)
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical';

  // AI 해결 정보
  ai_resolution: {
    summary: string;
    cause: string;
    action_needed: boolean;
    steps: string[];
    tips: string[];
  };

  // 코드 수정 정보
  code_fix: CodeFix;            // 대표 수정
  code_fixes: CodeFix[];        // 모든 수정 (그룹용)

  // 그룹 이슈인 경우: all_issues도 업데이트됨
  all_issues?: UpdatedIssue[];
}
```

### 10.8 전체 응답 예시

```json
{
  "success": true,
  "conversation_id": "conv_abc123def456",
  "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
  "issue_line": 524,
  "resolution": {
    "explanation": {
      "summary": "노즐 온도가 충분히 오르기 전 압출이 시작되었습니다.",
      "cause": "M109 대기 명령 없이 G1 E 명령이 실행되어 냉간 압출이 발생할 수 있습니다. 다만 이 슬라이서(OrcaSlicer)는 별도 매크로로 온도를 관리할 수 있습니다.",
      "is_false_positive": false,
      "severity": "medium"
    },
    "solution": {
      "action_needed": true,
      "steps": [
        "슬라이서의 시작 G-code에서 온도 대기 매크로 확인",
        "필요시 M109 S200 명령을 압출 전에 추가",
        "첫 레이어 온도 설정 확인"
      ],
      "code_fix": {
        "has_fix": true,
        "line_number": 524,
        "original": "524: G1 X100 Y100 E50 F1500",
        "fixed": "524: M109 S200 ; 온도 대기\n525: G1 X100 Y100 E50 F1500"
      },
      "code_fixes": [
        {
          "has_fix": true,
          "line_number": 524,
          "original": "524: G1 X100 Y100 E50 F1500",
          "fixed": "524: M109 S200 ; 온도 대기\n525: G1 X100 Y100 E50 F1500"
        }
      ]
    },
    "tips": [
      "PLA 권장 노즐 온도: 190-220°C",
      "첫 레이어는 5-10°C 높게 설정하면 접착력 향상",
      "온도 대기 없이 압출 시 필라멘트 막힘 위험"
    ]
  },
  "updated_issue": {
    "id": "ISSUE-1",
    "line": 524,
    "type": "cold_extrusion",
    "severity": "medium",
    "has_issue": true,
    "is_false_positive": false,
    "title": "저온 압출 감지",
    "description": "노즐 온도 180°C에서 압출 시작",
    "ai_resolution": {
      "summary": "노즐 온도가 충분히 오르기 전 압출이 시작되었습니다.",
      "cause": "M109 대기 명령 없이 G1 E 명령이 실행되어 냉간 압출이 발생할 수 있습니다.",
      "action_needed": true,
      "steps": ["슬라이서 시작 G-code 확인", "M109 S200 추가"],
      "tips": ["PLA 권장 온도: 190-220°C"]
    },
    "code_fix": {
      "has_fix": true,
      "line_number": 524,
      "original": "524: G1 X100 Y100 E50 F1500",
      "fixed": "524: M109 S200\n525: G1 X100 Y100 E50 F1500"
    },
    "code_fixes": [
      {
        "has_fix": true,
        "line_number": 524,
        "original": "524: G1 X100 Y100 E50 F1500",
        "fixed": "524: M109 S200\n525: G1 X100 Y100 E50 F1500"
      }
    ]
  }
}
```

### 10.9 프론트엔드 UI 구현 예시

```tsx
import React, { useState } from 'react';

interface IssueResolverProps {
  analysisId: string;
  issue: Issue;
  onResolved: (result: IssueResolveResponse) => void;
}

const IssueResolver: React.FC<IssueResolverProps> = ({
  analysisId,
  issue,
  onResolved
}) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IssueResolveResponse | null>(null);

  const handleResolve = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/gcode/analysis/${analysisId}/resolve-issue`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            analysis_id: analysisId,
            issue: issue,
            language: 'ko'
          })
        }
      );

      const data = await response.json();
      if (data.success) {
        setResult(data);
        onResolved(data);
      }
    } catch (error) {
      console.error('Issue resolution failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="issue-resolver">
      {/* 해결하기 버튼 */}
      <button
        onClick={handleResolve}
        disabled={loading}
        className="resolve-button"
      >
        {loading ? '분석 중...' : '🤖 AI 해결하기'}
      </button>

      {/* 결과 표시 */}
      {result && (
        <div className="resolution-result">
          {/* 오탐 여부 배지 */}
          {result.resolution.explanation.is_false_positive && (
            <div className="false-positive-badge">
              ✅ 오탐 - 실제 문제 아님
            </div>
          )}

          {/* 문제 해설 */}
          <div className="explanation-section">
            <h4>📋 문제 분석</h4>
            <p className="summary">{result.resolution.explanation.summary}</p>
            <p className="cause">{result.resolution.explanation.cause}</p>
            <span className={`severity-badge ${result.resolution.explanation.severity}`}>
              {result.resolution.explanation.severity.toUpperCase()}
            </span>
          </div>

          {/* 해결 방안 */}
          {result.resolution.solution.action_needed && (
            <div className="solution-section">
              <h4>🔧 해결 방법</h4>
              <ol>
                {result.resolution.solution.steps.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ol>

              {/* 코드 수정 제안 */}
              {result.resolution.solution.code_fixes?.map((fix, idx) => (
                fix.has_fix && (
                  <div key={idx} className="code-fix">
                    <h5>라인 {fix.line_number} 수정</h5>
                    <div className="diff-view">
                      <pre className="original">- {fix.original}</pre>
                      <pre className="fixed">+ {fix.fixed}</pre>
                    </div>
                  </div>
                )
              ))}
            </div>
          )}

          {/* 팁 */}
          <div className="tips-section">
            <h4>💡 팁</h4>
            <ul>
              {result.resolution.tips.map((tip, idx) => (
                <li key={idx}>{tip}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};
```

### 10.10 코드 수정 Diff 뷰어 컴포넌트

```tsx
interface CodeDiffViewerProps {
  codeFixes: CodeFix[];
  onApply?: (fix: CodeFix) => void;
}

const CodeDiffViewer: React.FC<CodeDiffViewerProps> = ({
  codeFixes,
  onApply
}) => {
  return (
    <div className="code-diff-container">
      {codeFixes.filter(fix => fix.has_fix).map((fix, idx) => (
        <div key={idx} className="diff-block">
          <div className="diff-header">
            <span className="line-number">Line {fix.line_number}</span>
            {onApply && (
              <button
                onClick={() => onApply(fix)}
                className="apply-button"
              >
                적용
              </button>
            )}
          </div>

          <div className="diff-content">
            {/* 원본 코드 */}
            <div className="line removed">
              <span className="prefix">-</span>
              <code>{fix.original?.split(': ').slice(1).join(': ')}</code>
            </div>

            {/* 수정 코드 (여러 줄일 수 있음) */}
            {fix.fixed?.split('\n').map((line, lineIdx) => (
              <div key={lineIdx} className="line added">
                <span className="prefix">+</span>
                <code>{line.split(': ').slice(1).join(': ')}</code>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// 스타일 예시
const diffStyles = `
.code-diff-container {
  font-family: 'Fira Code', monospace;
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.diff-block {
  border-bottom: 1px solid #333;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: #252525;
  color: #888;
}

.diff-content {
  padding: 12px;
}

.line {
  display: flex;
  padding: 2px 0;
}

.line.removed {
  background: rgba(248, 81, 73, 0.1);
  color: #f85149;
}

.line.added {
  background: rgba(63, 185, 80, 0.1);
  color: #3fb950;
}

.prefix {
  width: 20px;
  text-align: center;
  font-weight: bold;
}

.apply-button {
  background: #238636;
  color: white;
  border: none;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
}
`;
```

---

## 11. 체크리스트

### 구현 전 확인사항

- [ ] user_id 생성/관리 로직 구현
- [ ] Base64 인코딩 유틸리티 준비
- [ ] 마크다운 렌더러 라이브러리 선택 (react-markdown 등)
- [ ] 3D 뷰어 라이브러리 준비 (Three.js, Babylon.js 등)

### 기능별 구현 체크

- [ ] 기본 채팅 (텍스트 메시지)
- [ ] 파일 첨부 (드래그 앤 드롭)
- [ ] G-code 분석 + 3D 뷰어
- [ ] 분석 상태 폴링
- [ ] 프린터 문제 진단
- [ ] 이슈 해결 (AI 해결하기)
- [ ] 에러 처리 및 Rate Limit
- [ ] 대화 히스토리 관리

### LLM 결과 UI 체크

- [ ] 품질 점수/등급 카드
- [ ] 체크포인트 그리드
- [ ] 이슈 목록 (심각도별 그룹화)
- [ ] 이슈 상세 모달 (AI 해결하기 버튼)
- [ ] 권장사항 목록
- [ ] 종합 요약 패널
- [ ] 상세 통계 (접이식)
