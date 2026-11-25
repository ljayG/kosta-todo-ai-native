# CLAUDE.md

이 파일은 Claude Code(claude.ai/code)가 이 저장소에서 작업할 때 따르는 안내입니다.

# 언어규칙
- 모든 설명, 질문 및 답변은 한글로 한다.
- CLAUDE.md, `docs/` 문서, 코드 주석, 화면 문구 등 작성하는 모든 글은 한글로 쓴다. 코드 식별자, 명령어, 파일 경로는 원문 그대로 둔다.

## 프로젝트
AI 네이티브 ToDo 리스트. 할 일을 등록·조회·수정·완료·삭제하는 웹앱이며, 생산성 대시보드(완료율 링, 통계 카드, 오늘의 작업, 필터 탭, 우선순위)를 포함합니다.

현재 상태: React 프론트엔드와 FastAPI 백엔드가 연동되어 있습니다. 백엔드 저장소는 **In-Memory**라서 서버를 재시작하면 데이터가 사라집니다. `supabase/`는 비어 있고 배포는 구성되지 않았습니다.

## 기술 스택
- React 19 + Vite 7 (JavaScript/JSX, TypeScript 아님)
- FastAPI + Pydantic v2 (Python 3.15, `backend/.venv`)
- Supabase PostgreSQL: 미연결 (In-Memory 저장소 사용 중)
- Vercel: 배포 미구성

외부 UI 라이브러리, CSS 프레임워크, 상태 관리 라이브러리를 쓰지 않습니다. 의존성을 추가해야 하면 먼저 사용자에게 묻습니다.

## 구조

```text
frontend/
  src/App.jsx          상태와 레이아웃. 유일한 데이터 출처
  src/api/todos.js     FastAPI 호출, ApiError
  src/App.css          전체 스타일 (디자인 토큰 포함)
  src/constants.js     우선순위·필터 정의 (값, 라벨, 정렬 순서)
  src/components/      표시 전용 컴포넌트
backend/
  app/main.py          앱 생성, CORS, 500 처리, /api/health
  app/routers/         HTTP 계층: 요청/응답 변환, 404 변환
  app/services/        업무 규칙 계층: TodoNotFoundError 발생
  app/repositories/    저장 계층: TodoRepository 인터페이스 + InMemoryTodoRepository
  app/schemas.py       Pydantic 모델 (TodoCreate, TodoUpdate, Todo)
  app/dependencies.py  계층 조립. 저장소 구현 교체는 이 파일에서
  tests/               pytest
supabase/              DB 스키마·마이그레이션 (비어 있음)
docs/                  명세·가이드 (아래 "명세 문서" 참고), screenshots/
lession/               강의 자료. 프로젝트 코드 아님, 수정 금지
```

### 프론트엔드
- **상태는 `App.jsx`에만 둡니다.** `todos`, `filter`, `loadState`(loading/ready/error), `pendingIds`(요청 중인 id, 등록은 `'new'`), `notice`가 있습니다. 통계, 완료율, 필터된 목록, 오늘의 작업은 렌더링 중에 `todos`에서 계산합니다.
- **todo 형태:** `{ id, text, done, priority: 'high' | 'medium' | 'low', today: boolean, dueDate: 'YYYY-MM-DD' | null }`. API의 snake_case(`due_date`) ↔ camelCase(`dueDate`) 변환과 `created_at`, `updated_at` 제거는 `api/todos.js`에서만 합니다.
- **날짜:** 마감일은 시각 없는 날짜 문자열입니다. 오늘/내일/지남 판단과 표시 문구는 `src/dates.js`에서 브라우저 현지 날짜 기준으로 합니다. `new Date('YYYY-MM-DD')`는 UTC로 해석되므로 쓰지 않습니다.
- **변경 흐름:** 컴포넌트 → `App.jsx` 콜백(`onAdd`, `onToggle`, `onUpdate(id, changes)`, `onDelete`) → `mutate()` → API. 서버가 응답한 뒤에 화면에 반영합니다(비관적 업데이트). 콜백은 성공 여부를 `Promise<boolean>`으로 돌려주고, 컴포넌트는 실패하면 입력값을 유지합니다. 404는 화면에서 항목을 지우고 안내합니다.
- **요청 중 표시:** 카드의 버튼과 체크박스는 `disabled`가 아니라 `aria-disabled`를 쓰고 핸들러에서 무시합니다. 포커스를 잃지 않게 하기 위해서입니다.
- 개발 서버는 `/api`를 `http://localhost:8000`으로 프록시합니다(`vite.config.js`). `VITE_API_BASE_URL`을 비워 두면 같은 출처의 `/api`를 호출합니다.

### 백엔드
- 계층 의존은 router → service → repository 한 방향입니다.
  - router만 HTTP를 압니다.
  - service는 `TodoNotFoundError`를 던지고, router가 이를 404로 바꿉니다.
  - repository는 업무 규칙을 모릅니다.
- **Supabase 연결:** `TodoRepository` Protocol을 구현한 클래스를 추가하고 `dependencies.get_repository`만 바꿉니다.
- **In-Memory 저장소의 시각 처리:** 시각이 같아지지 않도록 단조 증가로 보정합니다. 목록 정렬(`created_at`, `id`)과 `updated_at` 증가를 보장하기 위해서입니다.

## 명령어

```bash
# 백엔드 (backend/에서)
python -m venv .venv && ./.venv/Scripts/python -m pip install -r requirements-dev.txt
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
./.venv/Scripts/python -m pytest -q                                    # 전체 테스트
./.venv/Scripts/python -m pytest tests/test_todos_api.py -k ac34 -q    # 단일 테스트

# 프론트엔드 (frontend/에서). 백엔드를 먼저 실행
npm install
npm run dev       # http://localhost:5173
npm run build     # 프로덕션 빌드. 변경 후 반드시 통과 확인
```

린터는 설정되어 있지 않습니다. pytest 실행 시 `httpx` 관련 deprecation 경고가 하나 나오며, 결과에는 영향이 없습니다.

## UI 디자인 규칙
상세 규칙은 `docs/ui-guidelines.md`를 따릅니다. 핵심만 요약합니다.
- 색·반경·폰트는 `App.css`의 `:root` CSS 변수로만 씁니다. 다크 모드 블록에도 같은 토큰을 정의합니다.
- 강조 요소는 완료율 링 하나입니다. 그림자, 그라데이션, 장식을 추가하지 않습니다.
- 우선순위는 색과 텍스트를 함께 씁니다.
- DOM 순서는 모바일 순서(입력 → 요약 → 목록)로 두고, 데스크톱 2열은 `grid-template-areas`로 배치합니다. 기준점은 880px와 560px입니다.
- 전역 `:focus-visible` outline을 제거하지 않습니다. 삭제 후와 수정 저장·취소 후의 포커스 이동 규칙을 유지합니다.
- 로딩, 오류, 요청 중 상태는 가이드의 "서버 상태 표시"를 따릅니다.

## API 개발 규칙
엔드포인트, 요청·응답, 오류의 세부 사항은 `docs/api-spec.md`를 따르고, 아래는 핵심 원칙만 요약합니다.
- **연결 구조:** 프론트엔드는 FastAPI만 호출하고, Supabase에 직접 접근하지 않습니다. Supabase 키는 백엔드 환경 변수(`backend/.env`, git 제외)에만 둡니다.
- **엔드포인트:** 리소스 단위로 만듭니다. `GET /api/todos`, `POST /api/todos`, `PATCH /api/todos/{id}`, `DELETE /api/todos/{id}`, `GET /api/health`.
- **스키마 검증:** Pydantic 모델에 `extra="forbid"`를 씁니다. `text`는 앞뒤 공백을 제거한 뒤 1~200자입니다. PATCH는 필드가 하나 이상 있어야 하고 null은 받지 않습니다. 예외로 `due_date: null`은 마감일 지우기입니다.
- **오류:** 없는 id는 404(`"할 일을 찾을 수 없습니다."`), 검증 실패는 422, 처리하지 못한 오류는 500(`"서버 오류가 발생했습니다."`)이며 내부 정보는 노출하지 않습니다.
- **CORS:** 허용 출처는 `ALLOWED_ORIGINS` 환경 변수(기본값 `http://localhost:5173`)로 정합니다.
- **DB 변경:** SQL 마이그레이션 파일로 `supabase/migrations/`에 추가합니다.

## 테스트 정책
- 모든 변경 후 `npm run build`가 통과해야 하고, 백엔드를 바꾸면 `pytest`가 통과해야 합니다.
- 백엔드 테스트 이름에는 수용 기준 번호를 붙입니다(예: `test_ac34_...`). `conftest.py`의 `client` fixture가 테스트마다 새 In-Memory 저장소를 주입합니다.
- UI·동작을 바꾸면 아래 회귀 시나리오가 그대로 동작하는지 확인합니다.
  - 등록(Enter / 추가 버튼, 빈 값 무시)
  - 완료 체크와 통계·완료율·오늘의 작업 연동
  - 수정(Enter 저장 / 저장 버튼 / Esc 취소, 우선순위 변경)
  - 삭제
  - 두 입력창의 × 버튼
  - 필터 탭(클릭, 방향키)
  - 키보드만으로 등록 → 완료 → 삭제
  - 새로고침 후 데이터 유지
  - 불러오기·등록 실패 처리
  - 390px에서 가로 스크롤 없음
- 프론트엔드 E2E 테스트는 아직 저장소에 없습니다(`docs/TASKS.md` T-11). 테스트 도구를 프로젝트에 추가하려면 먼저 사용자에게 묻습니다.
- 결과는 실행한 명령과 통과/실패 수를 그대로 보고합니다. 실패를 숨기거나, 실행하지 않은 테스트를 통과했다고 하지 않습니다.
- UI를 크게 바꾸면 같은 화면 크기(1280px, 390px)로 변경 전후를 캡처해 `docs/screenshots/`에 둡니다.

## 개발 규칙
1. 기존 코드 구조를 먼저 확인한다.
2. 변경 전 구현 계획을 제시한다.
3. PRD와 API 명세를 준수한다. 명세에 없는 결정이 필요하면 사용자에게 묻고, 확정되면 해당 문서와 `docs/spec-review.md`를 갱신한다.
4. UI는 `docs/ui-guidelines.md`를 따른다.
5. 기존 기능을 유지한다.
6. 구현 후 테스트 결과를 보고한다.
7. 비밀 키를 코드에 포함하지 않는다. `.env` 파일은 커밋하지 않는다.

## 명세 문서

모든 문서는 요구사항 ID로 연결됩니다: FR-xx·NFR-xx(요구사항) → API-xx → AC-xx(수용 기준) → T-xx(작업). 코드나 명세를 바꾸면 연결된 문서도 함께 고칩니다.

| 문서 | 내용 |
| --- | --- |
| `docs/PRD.md` | 요구사항 (FR, NFR), 범위 |
| `docs/api-spec.md` | API 명세 (API-01~05), 프론트엔드 반영 규칙 |
| `docs/db-schema.md` | `todos` 테이블, RLS, 마이그레이션 초안 |
| `docs/acceptance-criteria.md` | 수용 기준 (AC) |
| `docs/TASKS.md` | 구현 순서, 완료 조건, 진행 상태 |
| `docs/spec-review.md` | 추적표, 결정 필요(D), 충돌(C), 누락(G) |
| `docs/ui-guidelines.md` | 디자인 규칙 |
