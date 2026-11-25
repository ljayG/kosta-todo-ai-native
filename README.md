# todo-ai-native

React, FastAPI, Supabase, Vercel로 만드는 ToDo List 프로젝트입니다.

> 현재 상태: React 프론트엔드와 FastAPI 백엔드(메모리 저장소)가 연동되어 있습니다. Supabase 연결과 배포는 아직입니다. 요구사항과 진행 상황은 [docs/PRD.md](docs/PRD.md), [docs/TASKS.md](docs/TASKS.md)를 참고하세요.

## 프로젝트 목적

- 할 일을 추가, 조회, 수정, 완료, 삭제하는 간단한 ToDo List 웹 앱을 만듭니다.
- 프론트엔드(React)와 백엔드(FastAPI)를 나누고 Supabase(PostgreSQL)에 데이터를 저장하는 풀스택 구조를 익힙니다.
- Vercel로 배포까지 이어지는 개발 흐름을 실습합니다.
- Claude Code와 함께 AI 네이티브 방식으로 개발하는 과정을 연습합니다.

## 기술 스택

| 영역 | 기술 | 역할 |
| --- | --- | --- |
| Frontend | React | 사용자 화면(UI) |
| Backend | FastAPI (Python) | REST API 서버 |
| Database | Supabase (PostgreSQL) | 데이터 저장, 인증(필요 시) |
| Deploy | Vercel | 프론트엔드 및 API 배포 |

## 초기 디렉터리 구조

```text
todo-ai-native/
├── frontend/     # React 앱 (UI)
├── backend/      # FastAPI 서버 (API)
├── supabase/     # DB 스키마, 마이그레이션, 시드 데이터
└── README.md
```

> `lession/`은 강의 자료 폴더이며 프로젝트 코드와는 별개입니다.

## 실행

백엔드를 먼저 실행합니다. 백엔드는 아직 DB 대신 메모리에 저장하므로, 서버를 재시작하면 데이터가 사라집니다.

```bash
# 백엔드 (http://localhost:8000, API 문서: /docs)
cd backend
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements-dev.txt
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드 (http://localhost:5173, /api 요청은 백엔드로 프록시)
cd frontend
npm install
npm run dev
```

백엔드 테스트는 `backend/`에서 `./.venv/Scripts/python -m pytest -q`로 실행합니다.

## Git 브랜치

- `main`: 기본 브랜치
- `feature/todo-init`: 현재 작업 중인 초기 설정 브랜치

## 다음 단계

1. `frontend/`에 React 프로젝트 생성
2. `backend/`에 FastAPI 프로젝트 생성
3. `supabase/`에 todos 테이블 스키마 정의
4. 환경 변수(.env) 설정 및 Vercel 배포 구성
