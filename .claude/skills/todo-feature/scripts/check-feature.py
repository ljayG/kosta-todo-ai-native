"""
ToDo 프로젝트 자동 품질 검증 스크립트

[목적]
AI Agent가 개발한 React + FastAPI 프로젝트의 코드 품질을
자동으로 검증하기 위한 Harness Engineering 도구입니다.

[검사 항목]
1. Frontend : npm run build (빌드 및 설정된 타입 검사)
2. Backend  : compileall (Python 문법 검사)
3. Backend  : Ruff (Python 정적 코드 분석)

[실행 조건]
- 프로젝트 루트 디렉터리에서 실행
- 설치된 검사기만 실행
- 검사 실패 시 종료 코드 1 반환
- 모든 실행 검사가 성공하면 종료 코드 0 반환

주의: 검사기가 없어서 건너뛴 경우에도 PASS가 나올 수 있습니다.
"""

# 파일 및 디렉터리 경로를 다루는 표준 라이브러리
from pathlib import Path

# npm, Ruff 등의 실행 파일 설치 여부 및 경로 확인
import shutil

# 외부 프로그램(빌드, 린터 등)을 실행하기 위한 라이브러리
import subprocess

# 현재 Python 실행 경로와 프로그램 종료 코드 관리
import sys


# --------------------------------------------------
# Step 1. 프로젝트 루트 확인
# --------------------------------------------------

# 현재 명령어가 실행된 디렉터리를 프로젝트 루트로 사용
# 예: todo-ai-native/
root = Path.cwd()

# 실행할 검사 명령과 작업 디렉터리를 저장하는 리스트
# 형식: [(명령어 리스트, 실행 디렉터리), ...]
checks = []


# --------------------------------------------------
# Step 2. Frontend 검사 설정
# --------------------------------------------------

# frontend/package.json이 존재하면
# Node.js 기반 프론트엔드 프로젝트로 판단
if (root / 'frontend' / 'package.json').exists():

    # npm 실행 파일의 실제 경로를 검색
    # Windows: npm.cmd
    # macOS/Linux: npm
    npm = shutil.which('npm')

    if npm:
        # npm이 설치되어 있다면 빌드 명령을 검사 목록에 추가
        #
        # 실제 실행:
        # cd frontend
        # npm run build
        #
        # React + Vite 프로젝트에서는 일반적으로
        # TypeScript 검사 및 프로덕션 빌드를 수행할 수 있음
        # 단, 실제 검사 내용은 package.json의 build 스크립트에 따름
        checks.append((
            [npm, 'run', 'build'],
            root / 'frontend'
        ))

    else:
        # npm이 설치되지 않았다면 검사 생략
        print('SKIP: npm 미설치')


# --------------------------------------------------
# Step 3. Backend 검사 설정
# --------------------------------------------------

# backend 디렉터리가 존재하면 Python 백엔드로 판단
if (root / 'backend').is_dir():

    # Python 표준 라이브러리 compileall 실행
    #
    # -m compileall : Python 파일을 바이트코드로 컴파일
    # -q            : 불필요한 출력 최소화
    # backend       : 검사 대상 디렉터리
    #
    # Python 코드의 문법 오류 등을 검사
    # 실제 API 실행이나 기능 테스트를 수행하는 것은 아님
    checks.append((
        [sys.executable, '-m', 'compileall', '-q', 'backend'],
        root
    ))

    # Ruff 린터 설치 여부 확인
    ruff = shutil.which('ruff')

    if ruff:
        # Ruff가 설치되어 있다면 정적 분석 명령 추가
        #
        # 실제 실행:
        # ruff check backend
        #
        # 검사 내용:
        # - 사용하지 않는 import
        # - 정의되지 않은 변수
        # - 코드 스타일 및 설정된 품질 규칙 위반
        checks.append((
            [ruff, 'check', 'backend'],
            root
        ))

    else:
        # Ruff가 설치되지 않았다면 정적 분석 생략
        print('SKIP: Ruff 미설치')


# --------------------------------------------------
# Step 4. 검사 대상 존재 여부 확인
# --------------------------------------------------

# 실행할 검사 명령이 하나도 없다면
if not checks:

    print('SKIP: 검사 대상 프로젝트 없음')

    # 종료 코드 0: 정상 종료
    # 주의: 검사를 통과한 것이 아니라 검사하지 않은 상태
    sys.exit(0)


# --------------------------------------------------
# Step 5. 등록된 검사 명령 실행
# --------------------------------------------------

# 검사 실패 여부를 저장하는 변수
# False: 현재까지 실패 없음
# True : 하나 이상의 검사 실패
failed = False

# 검사 목록에 등록된 명령을 순서대로 실행
for command, cwd in checks:

    # 실행할 명령어를 화면에 출력
    #
    # 예:
    # RUN: npm run build
    # RUN: python -m compileall -q backend
    # RUN: ruff check backend
    print('RUN:', ' '.join(command), flush=True)

    # 외부 검사 프로그램 실행
    #
    # command     : 실행 명령어
    # cwd         : 명령어를 실행할 디렉터리
    # check=False : 실패하더라도 Python 예외를 발생시키지 않음
    #
    # returncode:
    # 0     : 검사 성공
    # 0 외  : 검사 실패
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False
    )

    # 검사 결과가 0이 아니면 실패로 기록
    if result.returncode:
        failed = True

    # 실패하더라도 다음 검사 명령은 계속 실행됨


# --------------------------------------------------
# Step 6. 최종 검사 결과 출력
# --------------------------------------------------

# 하나 이상의 검사가 실패하면 FAIL
# 실행된 검사가 모두 성공하면 PASS
print('FAIL' if failed else 'PASS')

# 최종 종료 코드 반환
#
# 0 : 실행된 모든 검사 성공
# 1 : 하나 이상의 검사 실패
#
# Claude Code의 Command, Hook 또는 Agent가
# 종료 코드를 이용해 다음 작업을 결정할 수 있음
sys.exit(1 if failed else 0)
