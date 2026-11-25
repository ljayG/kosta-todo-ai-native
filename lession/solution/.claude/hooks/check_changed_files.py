"""PostToolUse Hook: Edit/Write로 바뀐 파일 하나만 린트하고, 문제가 있으면 Claude Code에 보고한다.

- JavaScript/TypeScript: 그 파일이 속한 패키지(package.json)에 설정된 린터(oxlint 또는 ESLint)
- Python: Ruff (backend/.venv → PATH → `python -m ruff` 순서로 찾음)

종료 코드 규칙 (Claude Code Hook):
- 0: 문제 없음, 검사 대상 아님, 또는 린터가 없어 건너뜀(작업을 막지 않음)
- 2: 린트 오류·경고 발견. stderr 내용이 Claude에게 전달되어 바로 고칠 수 있다

표준 라이브러리만 쓰며 Windows와 macOS/Linux에서 같은 방식으로 동작한다.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

JS_TS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
PY_SUFFIXES = {".py", ".pyi"}
# 생성물·의존성 폴더는 검사하지 않는다.
SKIP_DIRS = {"node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".git"}
LINT_TIMEOUT_SECONDS = 60
IS_WINDOWS = os.name == "nt"


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env).resolve() if env else Path.cwd().resolve()


def read_changed_file(root: Path) -> Path | None:
    """stdin의 Hook 입력(JSON)에서 바뀐 파일 경로를 꺼낸다. 검사할 수 없으면 None."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or root) / path
    path = path.resolve()
    # 프로젝트 밖 파일(스크래치 등)과 삭제된 파일은 검사하지 않는다.
    if not path.is_file() or not path.is_relative_to(root):
        return None
    if SKIP_DIRS.intersection(path.relative_to(root).parts):
        return None
    return path


def find_upwards(start: Path, root: Path, name: str) -> Path | None:
    """start부터 프로젝트 루트까지 올라가며 name 파일이 있는 폴더를 찾는다."""
    for folder in (start, *start.parents):
        if (folder / name).is_file():
            return folder
        if folder == root:
            break
    return None


def local_bin(folder: Path, name: str) -> Path | None:
    """node_modules/.bin 실행 파일. Windows는 .cmd 래퍼를 쓴다."""
    candidates = [f"{name}.cmd", f"{name}.exe", name] if IS_WINDOWS else [name]
    for candidate in candidates:
        path = folder / "node_modules" / ".bin" / candidate
        if path.is_file():
            return path
    return None


def js_ts_command(file: Path, root: Path) -> tuple[list[str], Path] | str:
    """패키지에 설정된 린터 명령. 실행할 수 없으면 건너뛴 이유(str)를 돌려준다."""
    package_dir = find_upwards(file.parent, root, "package.json")
    if package_dir is None:
        return "package.json을 찾지 못해 JS/TS 검사를 건너뜁니다."
    try:
        package = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "package.json을 읽지 못해 JS/TS 검사를 건너뜁니다."
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    lint_script = package.get("scripts", {}).get("lint", "")
    target = str(file.relative_to(package_dir))

    # `npm run lint`가 쓰는 린터를 우선한다. 이 프로젝트는 oxlint (.oxlintrc.json).
    if "oxlint" in deps or "oxlint" in lint_script:
        binary = local_bin(package_dir, "oxlint")
        if binary is None:
            return f"oxlint가 설치되지 않았습니다. `{package_dir.name}`에서 `npm install`을 실행하세요."
        # 경고도 실패로 본다 (CLAUDE.md 9-2: lint 경고 0건 유지).
        return [str(binary), "--deny-warnings", target], package_dir
    if "eslint" in deps or "eslint" in lint_script:
        binary = local_bin(package_dir, "eslint")
        if binary is None:
            return f"ESLint가 설치되지 않았습니다. `{package_dir.name}`에서 `npm install`을 실행하세요."
        return [str(binary), "--max-warnings", "0", target], package_dir
    return "package.json에 설정된 JS/TS 린터(oxlint, ESLint)가 없어 건너뜁니다."


def ruff_command(file: Path, root: Path) -> tuple[list[str], Path] | str:
    """Ruff 명령. 가상환경 → PATH → 현재 Python 모듈 순서로 찾는다.

    가상환경은 파일에서 가까운 `.venv`를 먼저 보고, 없으면 루트 바로 아래 폴더의 `.venv`(예: backend/.venv)를 쓴다.
    그래서 `.claude/hooks/*.py`처럼 backend 밖의 Python 파일도 같은 Ruff로 검사한다.
    """
    scripts = ("Scripts", "ruff.exe") if IS_WINDOWS else ("bin", "ruff")
    nearby = [folder for folder in (file.parent, *file.parents) if folder.is_relative_to(root)]
    top_level = sorted(child for child in root.iterdir() if child.is_dir() and child.name not in SKIP_DIRS)
    candidates = [folder / ".venv" / scripts[0] / scripts[1] for folder in (*nearby, *top_level)]
    venv_ruff = next((c for c in candidates if c.is_file() and c.is_relative_to(root)), None)
    if venv_ruff:
        base = [str(venv_ruff)]
    elif shutil.which("ruff"):
        base = [shutil.which("ruff") or "ruff"]
    elif importlib.util.find_spec("ruff") is not None:
        base = [sys.executable, "-m", "ruff"]
    else:
        return "Ruff가 설치되지 않았습니다. `backend`에서 `pip install -r requirements-dev.txt`를 실행하세요."
    # --force-exclude: 설정의 exclude를 명시한 파일에도 적용한다. 설정은 파일 위치 기준으로 찾는다.
    return [*base, "check", "--force-exclude", "--no-cache", str(file)], root


def run(command: list[str], cwd: Path) -> tuple[int, str]:
    env = {**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0"}
    try:
        done = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LINT_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 0, f"린터가 {LINT_TIMEOUT_SECONDS}초 안에 끝나지 않아 건너뜁니다."
    except OSError as error:
        return 0, f"린터를 실행하지 못해 건너뜁니다: {error}"
    return done.returncode, (done.stdout + done.stderr).strip()


def main() -> int:
    # Windows 콘솔 코드페이지와 관계없이 한국어 메시지를 UTF-8로 보낸다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    root = project_root()
    file = read_changed_file(root)
    if file is None:
        return 0

    suffix = file.suffix.lower()
    if suffix in JS_TS_SUFFIXES:
        tool, plan = "JS/TS 린터", js_ts_command(file, root)
    elif suffix in PY_SUFFIXES:
        tool, plan = "Ruff", ruff_command(file, root)
    else:
        return 0

    rel = file.relative_to(root).as_posix()
    if isinstance(plan, str):
        # 린터가 없으면 작업을 막지 않고 안내만 남긴다.
        print(f"[check_changed_files] {rel}: {plan}", file=sys.stderr)
        return 0

    command, cwd = plan
    code, output = run(command, cwd)
    if code == 0:
        return 0

    # 원본 린터 출력은 바꾸지 않고 그대로 전달한다 (CLAUDE.md 1절).
    print(
        f"[check_changed_files] {rel} 검사에서 {tool} 문제가 발견되었습니다. 아래 내용을 확인해 수정하세요.\n"
        f"실행: {Path(command[0]).name} {' '.join(command[1:])}\n\n{output}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
