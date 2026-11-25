---
name: todo-feature
description: ToDo 앱의 기능 추가·수정 시 React, FastAPI, DB 및 테스트를 함께 점검하는 개발 절차.
---

# ToDo Feature Skill

## 1. Analyze
- `CLAUDE.md`, PRD, 수용 기준, 기존 코드와 테스트를 확인한다.
- `references/`의 관련 규칙을 읽는다.

## 2. Plan
- 수정할 파일, API·DB 변경 여부, 수용 기준을 정리한다.
- 구현 전 계획을 제시한다.

## 3. Implement
- 필요시 DB → FastAPI → React 순서로 구현한다.
- 기존 CRUD·마감일 기능을 유지하고 문서를 갱신한다.

## 4. Verify
- `python .claude/skills/todo-feature/scripts/check-feature.py` 실행.
- API 테스트, 프론트엔드 빌드, 기존 CRUD 회귀 테스트 수행.
- 실패한 항목은 수정 후 재검증한다.

## Rules
- 기존 기능 유지, 명세와 코드 일치, 비밀 정보 보호.
- 배포·DB 삭제 등 위험한 변경은 사전 승인.
