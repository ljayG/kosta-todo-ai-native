"""PreToolUse Hook: Bash·PowerShell 명령을 실행 전에 검사해 위험하면 막고, 확실하지 않으면 사용자 확인을 요청한다.

판단 결과 (Claude Code PreToolUse JSON 출력, 종료 코드는 항상 0):
- 차단(deny): 위험이 분명한 명령. `permissionDecisionReason`이 Claude에게 전달되어 다른 방법을 찾게 한다.
- 확인(ask): 위험할 수 있지만 검사기가 확실히 판단할 수 없는 명령. 사용자에게 승인 창을 띄운다.
- 통과: 아무것도 출력하지 않는다. 자동 승인(allow)이 아니므로 settings.json의 `permissions` 규칙과
  평소 승인 정책이 그대로 적용된다.

검사 정책
1. Git: push --force/+refspec/--mirror, reset --hard, clean -f, filter-branch 등
2. 대량 삭제: rm -rf, Remove-Item -Recurse -Force, rd /s /q, find -delete, rimraf, 디스크 초기화
3. DB: DROP·TRUNCATE·WHERE 없는 DELETE, supabase db reset, dropdb, HTTP DELETE
4. 민감 정보: .env·키 파일 읽기·복사·커밋, 환경 변수 전체 출력, 비밀 환경 변수 출력

우회 대응: 명령 조합(; && || | &), 따옴표, 명령 치환($(...), `...`, <(...)), heredoc·here-string,
bash -c·eval·PowerShell -Command·-EncodedCommand 같은 중첩 실행, sudo·env·xargs 같은 래퍼,
변수로 정한 명령 이름, 셸·인터프리터로 넘기는 파이프, $IFS·16진수·base64로 숨긴 문자열.
패턴 검사로 모든 우회를 막을 수는 없으므로 settings.json의 permissions 규칙과 함께 쓴다.

표준 라이브러리만 쓰며 Python 3.9 이상, Windows와 macOS/Linux에서 같은 방식으로 동작한다.
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import json
import re
import shlex
import sys
from dataclasses import dataclass, field

HOOK_NAME = "check_dangerous_commands"
ALLOW, ASK, DENY = 0, 1, 2
MAX_DEPTH = 6
MAX_COMMAND_LENGTH = 50_000
# 명령 치환 자리 표시. 이 값이 명령 이름 자리에 오면 실행할 명령을 미리 알 수 없다.
SUBST = "__SUBST__"
TOOL_SHELLS = {"Bash": "bash", "PowerShell": "powershell"}


# ───────── 판단 결과 ─────────


@dataclass
class Verdict:
    """검사 결과. 가장 높은 단계(통과 < 확인 < 차단)가 최종 판단이다."""

    level: int = ALLOW
    findings: list = field(default_factory=list)

    def flag(self, level: int, reason: str) -> None:
        if (level, reason) not in self.findings:
            self.findings.append((level, reason))
        self.level = max(self.level, level)

    def reasons(self) -> list:
        """최종 단계에 해당하는 사유만 돌려준다."""
        return [reason for level, reason in self.findings if level == self.level]


@dataclass
class Segment:
    """파이프라인 안의 명령 하나."""

    text: str
    name: str
    args: list
    index: int
    wrappers: list
    redirects: list
    stdin_texts: list


@dataclass
class Context:
    v: Verdict
    shell: str
    depth: int
    heredocs: dict
    pipeline: list = field(default_factory=list)


def clip(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def listing(items: list) -> str:
    shown = ", ".join(clip(item, 40) for item in items[:3])
    return shown + (f" 외 {len(items) - 3}개" if len(items) > 3 else "")


# ───────── 1단계: heredoc, 명령 치환, 명령 구분 ─────────

# `<<<`(here-string)은 제외한다.
HEREDOC_RE = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z0-9_.@-]+)\2")


def extract_heredocs(text: str) -> tuple[str, dict]:
    """heredoc 본문을 떼어 내고 연산자 자리에 `<< __HEREDOC_n__` 표시를 남긴다.

    본문은 데이터일 수도, 셸·DB·인터프리터가 실행할 내용일 수도 있으므로 받는 명령을 보고 따로 검사한다.
    """
    lines = text.split("\n")
    out, bodies, i, counter = [], {}, 0, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        pending, parts, last = [], [], 0
        for match in HEREDOC_RE.finditer(line):
            key = f"__HEREDOC_{counter}__"
            counter += 1
            pending.append((key, match.group(1) == "-", bool(match.group(2)), match.group(3)))
            parts += [line[last : match.start()], f"<< {key}"]
            last = match.end()
        out.append("".join(parts) + line[last:])
        for key, strip_tabs, quoted, delimiter in pending:
            body = []
            while i < len(lines):
                current = lines[i]
                i += 1
                compare = current.lstrip("\t") if strip_tabs else current
                if compare.rstrip("\r") == delimiter:
                    break
                body.append(current)
            bodies[key] = ("\n".join(body), quoted)
    return "\n".join(out), bodies


def find_closing(text: str, start: int) -> int:
    """`text[start]`의 여는 괄호와 짝이 맞는 닫는 괄호 위치. 없으면 -1."""
    depth, quote, i = 0, None, start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "\\":
            i += 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def extract_substitutions(text: str, shell: str) -> tuple[str, list, bool]:
    """`$(...)`, `` `...` ``, `<(...)`, `>(...)` 안의 명령을 꺼내고 자리에 SUBST를 남긴다.

    작은따옴표 안은 실행되지 않으므로 건너뛴다. 큰따옴표 안의 치환은 실행되므로 꺼낸다.
    """
    if shell == "cmd":
        return text, [], True
    escape = "`" if shell == "powershell" else "\\"
    out, inner, quote, i, n = [], [], None, 0, len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            out.append(ch)
            if ch == "'":
                quote = None
            i += 1
            continue
        if ch == escape and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch == "'" and quote is None:
            quote = "'"
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            quote = None if quote == '"' else '"'
            out.append(ch)
            i += 1
            continue
        opens_subst = ch == "$" or (ch in "<>" and quote is None and shell == "bash")
        if opens_subst and text[i + 1 : i + 2] == "(":
            end = find_closing(text, i + 1)
            if end < 0:
                return "".join(out) + text[i:], inner, False
            inner.append(text[i + 2 : end])
            out.append(SUBST)
            i = end + 1
            continue
        if ch == "`" and shell == "bash":
            end = text.find("`", i + 1)
            if end < 0:
                return "".join(out) + text[i:], inner, False
            inner.append(text[i + 1 : end])
            out.append(SUBST)
            i = end + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), inner, True


def escape_char(shell: str) -> str:
    return {"powershell": "`", "cmd": "^"}.get(shell, "\\")


def split_pipelines(text: str, shell: str) -> list:
    """명령 문자열을 파이프라인 목록으로 나눈다. 파이프라인은 `|`로 이어진 명령 문자열의 목록이다.

    `;`, `&&`, `||`, `&`, 줄바꿈, 괄호·중괄호(서브셸, 스크립트 블록)를 구분자로 본다. 따옴표 안은 나누지 않는다.
    """
    escape = escape_char(shell)
    pipelines, current, buffer = [], [], []
    quote, i, n = None, 0, len(text)

    def end_segment() -> None:
        segment = "".join(buffer).strip()
        buffer.clear()
        if segment:
            current.append(segment)

    def end_pipeline() -> None:
        end_segment()
        if current:
            pipelines.append(list(current))
            current.clear()

    while i < n:
        ch = text[i]
        if quote:
            buffer.append(ch)
            if ch == escape and quote == '"' and i + 1 < n:
                buffer.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == escape and i + 1 < n:
            if text[i + 1] == "\n":
                i += 2
                continue
            buffer.append(text[i : i + 2])
            i += 2
            continue
        if ch in "'\"":
            quote = ch
            buffer.append(ch)
            i += 1
            continue
        if ch == "$" and text[i + 1 : i + 2] == "{":
            end = text.find("}", i)
            end = n - 1 if end < 0 else end
            buffer.append(text[i : end + 1])
            i = end + 1
            continue
        if ch == "#" and (i == 0 or text[i - 1] in " \t\n;&|(){}"):
            while i < n and text[i] != "\n":
                i += 1
            continue
        pair = text[i : i + 2]
        if pair in ("&&", "||"):
            end_pipeline()
            i += 2
            continue
        if ch == "|":
            end_segment()
            i += 2 if pair == "|&" else 1
            continue
        if ch == "&":
            # 2>&1, &> 같은 리다이렉션은 구분자가 아니다.
            if (i > 0 and text[i - 1] in "<>") or text[i + 1 : i + 2] == ">":
                buffer.append(ch)
                i += 1
                continue
            end_pipeline()
            i += 1
            continue
        if ch in ";\n\r(){}":
            end_pipeline()
            i += 1
            continue
        buffer.append(ch)
        i += 1
    end_pipeline()
    return pipelines


def tokenize(text: str, shell: str) -> tuple[list, list]:
    """따옴표를 해석해 토큰으로 나누고 리다이렉션(`<`, `>`, `2>&1`, `<<`)을 따로 모은다."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars="<>&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = escape_char(shell)
    raw = list(lexer)
    if shell == "bash":
        # bash는 큰따옴표 안의 \$, \`도 풀지만 shlex는 백슬래시를 남긴다.
        raw = [token.replace("\\$", "$").replace("\\`", "`") for token in raw]
    tokens, redirects, i = [], [], 0
    while i < len(raw):
        token = raw[i]
        if token and set(token) <= set("<>&|") and ("<" in token or ">" in token):
            if tokens and tokens[-1].isdigit():
                tokens.pop()  # 2>, 1> 같은 파일 설명자 번호
            target = raw[i + 1] if i + 1 < len(raw) else ""
            redirects.append((token, target))
            i += 2
            continue
        tokens.append(token)
        i += 1
    return tokens, redirects


# ───────── 2단계: 명령 이름 정규화와 래퍼 제거 ─────────

SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "esac", "coproc"}
HEADER_KEYWORDS = {"for", "case", "select", "function"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
# 래퍼 명령과 값을 받는 옵션. 래퍼를 벗겨 실제로 실행되는 명령을 검사한다.
WRAPPERS = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--user", "--group", "--host", "--prompt", "--chdir"},
    "doas": {"-u", "-C"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p", "--class", "--classdata"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--max-procs", "--delimiter", "--arg-file", "--replace"},
    "nohup": set(),
    "time": {"-f", "-o"},
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
    "npx": {"-p", "--package"},
    "pnpx": set(),
    "bunx": set(),
    "setsid": set(),
    "unbuffer": set(),
    "caffeinate": set(),
    "busybox": set(),
    "winpty": set(),
    "chroot": set(),
    "flock": {"-w", "-E"},
    "taskset": set(),
}
# 옵션 다음에 오는 위치 인수 개수 (timeout 5 cmd, chroot /root cmd)
WRAPPER_POSITIONAL = {"timeout": 1, "chroot": 1, "flock": 1, "taskset": 1}
PS_DANGER_EXPR = re.compile(r"(\.|::)(delete|remove|removeall|clear|kill|drop|truncate|executenonquery|getenvironmentvariable)\b", re.IGNORECASE)


def normalize_name(token: str) -> str:
    """경로·확장자·대소문자를 정리한 명령 이름. `/bin/rm`, `RM.EXE` → `rm`"""
    base = re.split(r"[\\/]", token)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
    return base


def is_dynamic(token: str) -> bool:
    """변수·명령 치환·와일드카드로 정해져 실제 값을 미리 알 수 없는 토큰인지."""
    if token in ("[", "[["):
        return False
    return "$" in token or SUBST in token or "`" in token or any(ch in token for ch in "*?[")


def resolve_powershell(tokens: list, ctx: Context) -> list | None:
    """PowerShell 호출 연산자(&, .)와 변수 대입을 벗긴다. 식(메서드 호출)이면 검사 후 None."""
    while tokens and tokens[0] in ("&", "."):
        tokens = tokens[1:]
    if not tokens or not tokens[0].startswith(("$", "[")):
        return tokens
    if len(tokens) > 1 and tokens[1] in ("=", "+=", "-=", "*=", "/=", "??="):
        return tokens[2:]
    assignment = re.match(r"^\$[\w:]+=(.*)$", tokens[0])
    if assignment:
        return ([assignment.group(1)] if assignment.group(1) else []) + tokens[1:]
    expression = " ".join(tokens)
    if re.search(r"::getenvironmentvariables\b", expression, re.IGNORECASE):
        ctx.v.flag(DENY, "[Environment]::GetEnvironmentVariables(): 모든 환경 변수(비밀 값 포함)를 출력합니다.")
    elif PS_DANGER_EXPR.search(expression):
        ctx.v.flag(ASK, f"PowerShell 메서드 호출로 삭제·초기화를 실행할 수 있습니다: {clip(expression)}")
    return None


def resolve(tokens: list, ctx: Context) -> tuple | None:
    """(명령 이름, 인수, 벗긴 래퍼 목록)을 돌려준다. 실행할 명령이 없거나 알 수 없으면 None."""
    if ctx.shell == "powershell":
        tokens = resolve_powershell(tokens, ctx)
        if tokens is None:
            return None
    wrappers, i, n = [], 0, len(tokens)
    while i < n:
        token = tokens[i]
        if token in SHELL_KEYWORDS:
            i += 1
            continue
        if token in HEADER_KEYWORDS and not wrappers:
            return None
        if ctx.shell != "powershell" and ASSIGNMENT_RE.match(token):
            i += 1
            continue
        if is_dynamic(token):
            ctx.v.flag(ASK, f"실행할 명령 이름을 미리 알 수 없습니다(변수·명령 치환·와일드카드): {clip(token)}")
            return None
        name = normalize_name(token)
        if name == "command" and i + 1 < n and tokens[i + 1] in ("-v", "-V"):
            return name, tokens[i + 1 :], wrappers
        if name in WRAPPERS and ctx.shell != "powershell":
            wrappers.append(name)
            i += 1
            value_options = WRAPPERS[name]
            while i < n and tokens[i].startswith("-") and tokens[i] != "-":
                option = tokens[i]
                i += 1
                if option == "--":
                    break
                if option in value_options:
                    i += 1
            i += WRAPPER_POSITIONAL.get(name, 0)
            if i >= n:
                if name == "env":
                    return "env", [], wrappers[:-1]
                if name == "xargs":
                    return "echo", [], wrappers  # xargs의 기본 명령은 echo
                return None
            continue
        return name, tokens[i + 1 :], wrappers
    return None


def parse_segment(text: str, index: int, ctx: Context) -> Segment | None:
    try:
        tokens, redirects = tokenize(text, ctx.shell)
    except ValueError:
        ctx.v.flag(ASK, f"따옴표 짝이 맞지 않아 명령을 해석하지 못했습니다: {clip(text)}")
        return None
    check_redirections(redirects, ctx)
    stdin_texts = []
    for operator, target in redirects:
        if operator == "<<" and target in ctx.heredocs:
            stdin_texts.append(ctx.heredocs[target][0])
        elif operator == "<<<":
            stdin_texts.append(target)
    resolved = resolve(tokens, ctx)
    if resolved is None:
        return None
    name, args, wrappers = resolved
    return Segment(text, name, args, index, wrappers, redirects, stdin_texts)


def analyze(text: str, v: Verdict, shell: str, depth: int = 0) -> None:
    """명령 문자열 하나를 검사한다. 중첩 실행(bash -c, eval, 명령 치환)은 depth를 올려 다시 부른다."""
    if depth > MAX_DEPTH:
        v.flag(ASK, "명령이 너무 깊게 중첩되어 끝까지 검사하지 못했습니다.")
        return
    if not text or not text.strip():
        return
    heredocs = {}
    if shell == "bash":
        text, heredocs = extract_heredocs(text)
        for body, quoted in heredocs.values():
            if not quoted:  # 따옴표 없는 heredoc 본문의 $(...)는 실행된다.
                _, inner, _ = extract_substitutions(body, shell)
                for command in inner:
                    analyze(command, v, shell, depth + 1)
    text, inner, balanced = extract_substitutions(text, shell)
    if not balanced:
        v.flag(ASK, "괄호나 백틱 짝이 맞지 않아 명령 치환을 정확히 해석하지 못했습니다.")
    for command in inner:
        analyze(command, v, shell, depth + 1)
    for pipeline in split_pipelines(text, shell):
        ctx = Context(v, shell, depth, heredocs)
        segments = [parse_segment(part, index, ctx) for index, part in enumerate(pipeline)]
        ctx.pipeline = [segment for segment in segments if segment]
        for segment in ctx.pipeline:
            check_segment(segment, ctx)


def analyze_tokens(tokens: list, ctx: Context) -> None:
    """이미 나뉜 토큰(find -exec, docker exec 뒤의 명령)을 다시 명령 문자열로 만들어 검사한다."""
    if tokens:
        analyze(" ".join(shlex.quote(token) for token in tokens), ctx.v, "bash", ctx.depth + 1)


# ───────── 3단계: 명령별 검사 ─────────


def short_flags(args: list) -> set:
    """`-fu` 같은 한 글자 옵션 묶음의 글자 집합 (대소문자 구분)"""
    letters = set()
    for arg in args:
        if re.fullmatch(r"-[A-Za-z]+", arg):
            letters.update(arg[1:])
    return letters


def long_flags(args: list) -> set:
    return {arg.split("=", 1)[0] for arg in args if arg.startswith("--")}


GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--super-prefix"}


def git_subcommand(args: list) -> tuple[str, list]:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_VALUE_OPTIONS else 1
    if i >= len(args):
        return "", []
    return args[i].lower(), args[i + 1 :]


def check_git(seg: Segment, ctx: Context) -> None:
    v = ctx.v
    for i, arg in enumerate(seg.args[:-1]):
        if arg == "-c" and seg.args[i + 1].lower().startswith("alias."):
            v.flag(ASK, "git -c alias.*: 별칭으로 다른 명령을 숨길 수 있습니다.")
    sub, rest = git_subcommand(seg.args)
    short, longs = short_flags(rest), long_flags(rest)
    positional = [arg for arg in rest if not arg.startswith("-")]
    if sub == "push":
        if "--force" in longs or "f" in short:
            v.flag(DENY, "git push --force: 원격 저장소의 기록을 덮어써 다른 사람의 커밋이 사라질 수 있습니다.")
        if "--mirror" in longs:
            v.flag(DENY, "git push --mirror: 원격 저장소의 모든 참조를 로컬 상태로 덮어씁니다.")
        if any(arg.startswith("+") for arg in positional):
            v.flag(DENY, "git push +<refspec>: 강제 푸시와 같습니다.")
        if longs & {"--force-with-lease", "--force-if-includes"}:
            v.flag(ASK, "git push --force-with-lease: 조건부지만 원격 기록을 덮어씁니다.")
        if "--delete" in longs or "d" in short or any(arg.startswith(":") and len(arg) > 1 for arg in positional):
            v.flag(ASK, "git push --delete: 원격 브랜치·태그를 삭제합니다.")
        if "--prune" in longs:
            v.flag(ASK, "git push --prune: 로컬에 없는 원격 브랜치를 삭제합니다.")
        if "--no-verify" in longs:
            v.flag(ASK, "git push --no-verify: Git Hook 검사를 건너뜁니다.")
    elif sub == "reset" and "--hard" in longs:
        v.flag(DENY, "git reset --hard: 커밋하지 않은 변경 사항이 모두 사라집니다.")
    elif sub == "clean" and ("f" in short or "--force" in longs) and not ("n" in short or "--dry-run" in longs):
        v.flag(DENY, "git clean -f: 추적하지 않는 파일을 복구할 수 없게 삭제합니다. 먼저 git clean -n으로 확인하세요.")
    elif sub in ("filter-branch", "filter-repo"):
        v.flag(DENY, f"git {sub}: 저장소 기록 전체를 다시 씁니다.")
    elif sub == "checkout" and ("f" in short or "--force" in longs or "--" in rest or "." in rest):
        v.flag(ASK, "git checkout -- <경로>: 작업 트리의 변경 사항을 덮어씁니다.")
    elif sub == "restore":
        staged_only = ("--staged" in longs or "S" in short) and not ("--worktree" in longs or "W" in short)
        if not staged_only:
            v.flag(ASK, "git restore: 작업 트리의 변경 사항을 되돌립니다.")
    elif sub == "switch" and ("--discard-changes" in longs or "--force" in longs or "f" in short):
        v.flag(ASK, "git switch --discard-changes: 작업 트리의 변경 사항을 버립니다.")
    elif sub == "branch" and ("D" in short or "M" in short or ("--delete" in longs and ("--force" in longs or "f" in short))):
        v.flag(ASK, "git branch -D: 병합하지 않은 브랜치를 강제로 삭제합니다.")
    elif sub == "stash" and positional[:1] and positional[0] in ("drop", "clear"):
        v.flag(ASK, f"git stash {positional[0]}: 보관한 변경 사항을 삭제합니다.")
    elif sub == "reflog" and positional[:1] and positional[0] in ("expire", "delete"):
        v.flag(ASK, "git reflog expire/delete: 복구에 필요한 기록을 지웁니다.")
    elif sub == "gc" and any(arg.startswith("--prune") for arg in rest):
        v.flag(ASK, "git gc --prune: 도달할 수 없는 커밋을 즉시 삭제합니다.")
    elif sub == "update-ref" and "d" in short:
        v.flag(ASK, "git update-ref -d: 참조를 직접 삭제합니다.")
    elif sub == "rm" and ("r" in short) and ("f" in short or "--force" in longs):
        v.flag(ASK, "git rm -rf: 파일과 폴더를 강제로 삭제합니다.")
    elif sub == "commit" and ("--no-verify" in longs or "n" in short):
        v.flag(ASK, "git commit --no-verify: Git Hook 검사를 건너뜁니다.")
    elif sub == "add" and ("f" in short or "--force" in longs):
        v.flag(ASK, "git add -f: .gitignore로 제외한 파일(민감 정보 포함 가능)을 강제로 추가합니다.")
    elif sub == "config" and any(arg.lower().startswith("alias.") for arg in rest):
        v.flag(ASK, "git config alias.*: 별칭으로 위험 명령을 숨길 수 있습니다.")
    elif sub == "credential":
        v.flag(ASK, "git credential: 저장된 자격 증명을 다룹니다.")


def is_broad_target(target: str) -> bool:
    """삭제 대상이 넓거나(루트, 홈, 현재 폴더, 와일드카드) 실행 전에는 알 수 없는(변수) 경로인지."""
    text = target.strip()
    if not text or "$" in text or SUBST in text or text.startswith("~"):
        return True
    if any(ch in text for ch in "*?["):
        return True
    norm = text.replace("\\", "/").rstrip("/")
    if norm in ("", ".", "..", "./", "/home", "/users", "/etc", "/usr", "/var", "/bin", "/opt"):
        return True
    if re.fullmatch(r"[A-Za-z]:|/[A-Za-z]|/[A-Za-z]/users", norm, re.IGNORECASE):
        return True
    return norm.startswith("../")


def check_rm(seg: Segment, ctx: Context) -> None:
    recursive = force = options_done = False
    targets = []
    for arg in seg.args:
        if not options_done and arg == "--":
            options_done = True
        elif not options_done and arg.startswith("--"):
            recursive |= arg == "--recursive"
            force |= arg == "--force"
            if arg == "--no-preserve-root":
                ctx.v.flag(DENY, "rm --no-preserve-root: 루트(/) 보호를 끄고 삭제합니다.")
        elif not options_done and arg.startswith("-") and len(arg) > 1:
            recursive |= "r" in arg or "R" in arg
            force |= "f" in arg
        else:
            targets.append(arg)
    broad = [target for target in targets if is_broad_target(target)]
    described = listing(targets) if targets else "표준 입력·목록"
    if recursive and force:
        ctx.v.flag(DENY, f"rm -rf: 하위 폴더까지 확인 없이 삭제합니다(대상: {described}).")
    elif recursive:
        ctx.v.flag(DENY if broad else ASK, f"rm -r: 폴더를 통째로 삭제합니다(대상: {described}).")
    elif "xargs" in seg.wrappers or (not targets and seg.index > 0):
        ctx.v.flag(ASK, "xargs·파이프로 받은 목록을 삭제합니다. 대상이 무엇인지 확인하세요.")
    elif broad:
        ctx.v.flag(ASK, f"와일드카드·변수로 정한 대상을 삭제합니다(대상: {listing(broad)}).")


def ps_param(token: str, full: str, min_length: int) -> bool:
    """PowerShell 매개변수 축약형 일치 여부. `-rec`, `-Recurse:$true` → -Recurse"""
    key = token.lower().split(":", 1)[0]
    return key.startswith("-") and len(key) >= min_length and full.startswith(key)


def check_remove_item(seg: Segment, ctx: Context) -> None:
    recurse = any(ps_param(arg, "-recurse", 2) for arg in seg.args)
    force = any(ps_param(arg, "-force", 3) for arg in seg.args)
    targets = [arg for arg in seg.args if not arg.startswith("-")]
    broad = [target for target in targets if is_broad_target(target)]
    described = listing(targets) if targets else "파이프 입력"
    if recurse and force:
        ctx.v.flag(DENY, f"Remove-Item -Recurse -Force: 하위 폴더까지 확인 없이 삭제합니다(대상: {described}).")
    elif recurse:
        ctx.v.flag(DENY if broad else ASK, f"Remove-Item -Recurse: 폴더를 통째로 삭제합니다(대상: {described}).")
    elif broad or (not targets and seg.index > 0):
        ctx.v.flag(ASK, f"Remove-Item: 와일드카드·변수·파이프로 정한 대상을 삭제합니다(대상: {described}).")


def check_cmd_delete(seg: Segment, ctx: Context) -> None:
    switches = {arg.lower() for arg in seg.args if arg.startswith("/")}
    targets = [arg for arg in seg.args if not arg.startswith("/")]
    if "/s" in switches:
        level = DENY if "/q" in switches else ASK
        ctx.v.flag(level, f"{seg.name} /s: 하위 폴더까지 삭제합니다(대상: {listing(targets)}).")
    elif any(is_broad_target(target) for target in targets):
        ctx.v.flag(ASK, f"{seg.name}: 와일드카드로 정한 파일을 삭제합니다(대상: {listing(targets)}).")


def check_find(seg: Segment, ctx: Context) -> None:
    args = seg.args
    roots = []
    for arg in args:
        if arg.startswith(("-", "(", "!")):
            break
        roots.append(arg)
    if "-delete" in args:
        level = DENY if any(re.fullmatch(r"/|~/?|\$HOME|[A-Za-z]:[\\/]?|/[A-Za-z]/?", root) for root in roots) else ASK
        ctx.v.flag(level, f"find -delete: 조건에 맞는 파일을 한꺼번에 삭제합니다(시작 위치: {listing(roots) or '.'}).")
    looks_for_secret = any(classify_path(arg, ctx.shell) for arg in args)
    i = 0
    while i < len(args):
        if args[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            command = []
            while j < len(args) and args[j] not in (";", "+"):
                command.append(args[j])
                j += 1
            analyze_tokens(command, ctx)
            if looks_for_secret and command and normalize_name(command[0]) in READERS:
                ctx.v.flag(DENY, "find -exec: 민감 파일을 찾아 내용을 출력합니다.")
            i = j
        i += 1


def check_disk(seg: Segment, ctx: Context) -> None:
    if seg.name == "dd":
        if any(arg.lower().startswith("of=/dev/") for arg in seg.args):
            ctx.v.flag(DENY, "dd of=/dev/...: 디스크 장치를 직접 덮어씁니다.")
        return
    ctx.v.flag(DENY, f"{seg.name}: 디스크나 파일을 복구할 수 없게 지웁니다.")


def check_rimraf(seg: Segment, ctx: Context) -> None:
    ctx.v.flag(DENY, f"{seg.name}: rm -rf와 같이 폴더를 통째로 삭제합니다.")


def check_truncate(seg: Segment, ctx: Context) -> None:
    ctx.v.flag(ASK, f"{seg.name}: 파일 내용을 비웁니다.")


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "mksh", "tcsh", "csh"}
SHELL_VALUE_OPTIONS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}


def check_shell(seg: Segment, ctx: Context) -> None:
    args, i = seg.args, 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            break
        if arg in SHELL_VALUE_OPTIONS:
            i += 2
            continue
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
            if i + 1 < len(args):
                analyze(args[i + 1], ctx.v, "bash", ctx.depth + 1)
            return
        if not arg.startswith(("-", "+")):
            return  # 스크립트 파일 실행. 파일 내용은 검사하지 않는다.
        i += 1
    for body in seg.stdin_texts:
        analyze(body, ctx.v, "bash", ctx.depth + 1)
    if seg.index > 0:
        ctx.v.flag(ASK, f"파이프로 받은 내용을 {seg.name}이(가) 명령으로 실행합니다. 내용을 확인할 수 없습니다.")


def check_cmd(seg: Segment, ctx: Context) -> None:
    for i, arg in enumerate(seg.args):
        if arg.lower() in ("/c", "/k", "//c", "//k", "/r"):
            analyze(" ".join(seg.args[i + 1 :]), ctx.v, "cmd", ctx.depth + 1)
            return
    if seg.index > 0:
        ctx.v.flag(ASK, "파이프로 받은 내용을 cmd가 명령으로 실행합니다.")


PS_VALUE_OPTIONS = ("-executionpolicy", "-ep", "-windowstyle", "-workingdirectory", "-wd", "-configurationname", "-version", "-outputformat", "-inputformat")


def decode_powershell(encoded: str) -> str | None:
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-16-le")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def check_powershell(seg: Segment, ctx: Context) -> None:
    args, i = seg.args, 0
    while i < len(args):
        arg = args[i]
        if not arg.startswith(("-", "/")):
            # 첫 위치 인수는 -Command(Windows PowerShell)로 해석된다.
            analyze(" ".join(args[i:]), ctx.v, "powershell", ctx.depth + 1)
            return
        key = "-" + arg.lower().lstrip("-/").split(":", 1)[0]
        if key in ("-e", "-ec") or (len(key) >= 3 and "-encodedcommand".startswith(key)):
            decoded = decode_powershell(args[i + 1]) if i + 1 < len(args) else None
            if decoded is None:
                ctx.v.flag(ASK, "인코딩된 PowerShell 명령(-EncodedCommand)의 내용을 확인할 수 없습니다.")
            else:
                analyze(decoded, ctx.v, "powershell", ctx.depth + 1)
            return
        if key == "-c" or (len(key) >= 4 and "-command".startswith(key)):
            analyze(" ".join(args[i + 1 :]), ctx.v, "powershell", ctx.depth + 1)
            return
        if key == "-f" or (len(key) >= 3 and "-file".startswith(key)):
            return
        i += 2 if any(full.startswith(key) for full in PS_VALUE_OPTIONS if len(key) >= 3) else 1
    if seg.index > 0:
        ctx.v.flag(ASK, "파이프로 받은 내용을 PowerShell이 명령으로 실행합니다.")


def check_eval(seg: Segment, ctx: Context) -> None:
    analyze(" ".join(seg.args), ctx.v, ctx.shell, ctx.depth + 1)


def check_invoke_expression(seg: Segment, ctx: Context) -> None:
    if seg.args:
        analyze(" ".join(seg.args), ctx.v, "powershell", ctx.depth + 1)
    elif seg.index > 0:
        ctx.v.flag(ASK, "파이프로 받은 문자열을 Invoke-Expression이 실행합니다.")


def check_wsl(seg: Segment, ctx: Context) -> None:
    args, i = seg.args, 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-e", "--exec", "--"):
            i += 1
            break
        i += 2 if args[i] in ("-d", "--distribution", "-u", "--user", "--cd") else 1
    analyze_tokens(args[i:], ctx)


SSH_VALUE_OPTIONS = {"-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m", "-O", "-o", "-p", "-Q", "-R", "-S", "-W", "-w", "-B"}


def check_ssh(seg: Segment, ctx: Context) -> None:
    args, i = seg.args, 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in SSH_VALUE_OPTIONS else 1
    if i + 1 < len(args):
        analyze(" ".join(args[i + 1 :]), ctx.v, "bash", ctx.depth + 1)


DOCKER_GLOBAL_VALUE = {"--context", "-c", "-H", "--host", "--config", "--log-level", "-l"}
DOCKER_EXEC_VALUE = {"-u", "--user", "-w", "--workdir", "-e", "--env", "--env-file", "--detach-keys", "--index"}
COMPOSE_VALUE = {"-f", "--file", "-p", "--project-name", "--env-file", "--profile", "--project-directory"}


def skip_options(args: list, value_options: set) -> int:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in value_options else 1
    return i


def check_docker(seg: Segment, ctx: Context) -> None:
    args = seg.args
    if seg.name == "docker-compose":
        sub, rest = "compose", args
    else:
        i = skip_options(args, DOCKER_GLOBAL_VALUE)
        if i >= len(args):
            return
        sub, rest = args[i], args[i + 1 :]
    if sub == "compose":
        j = skip_options(rest, COMPOSE_VALUE)
        action, after = (rest[j], rest[j + 1 :]) if j < len(rest) else ("", [])
        if action == "down" and any(arg in ("-v", "--volumes") for arg in after):
            ctx.v.flag(ASK, "docker compose down -v: 컨테이너 볼륨(DB 데이터 포함)을 삭제합니다.")
        if action in ("exec", "run"):
            k = skip_options(after, DOCKER_EXEC_VALUE)
            analyze_tokens(after[k + 1 :], ctx)
        return
    if sub == "exec":
        j = skip_options(rest, DOCKER_EXEC_VALUE)
        analyze_tokens(rest[j + 1 :], ctx)
    elif sub == "volume" and rest[:1] and rest[0] in ("rm", "remove", "prune"):
        ctx.v.flag(ASK, f"docker volume {rest[0]}: 볼륨(DB 데이터 포함)을 삭제합니다.")
    elif sub == "system" and rest[:1] == ["prune"]:
        ctx.v.flag(ASK, "docker system prune: 사용하지 않는 컨테이너·이미지·볼륨을 삭제합니다.")


def check_kubectl(seg: Segment, ctx: Context) -> None:
    if seg.args[:1] == ["exec"] and "--" in seg.args:
        analyze_tokens(seg.args[seg.args.index("--") + 1 :], ctx)
    elif seg.args[:1] == ["delete"]:
        ctx.v.flag(ASK, "kubectl delete: 클러스터 리소스를 삭제합니다.")


def check_gh(seg: Segment, ctx: Context) -> None:
    if seg.args[:2] == ["auth", "token"]:
        ctx.v.flag(DENY, "gh auth token: GitHub 인증 토큰을 그대로 출력합니다.")
    elif seg.args[:2] == ["auth", "status"] and ("-t" in seg.args or "--show-token" in seg.args):
        ctx.v.flag(DENY, "gh auth status --show-token: GitHub 인증 토큰을 출력합니다.")


# ───────── 민감 정보 ─────────

SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist", ".defaults", ".schema")
SENSITIVE_GLOBS = (
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.ppk",
    "id_rsa", "id_rsa_*", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.json", ".netrc", "_netrc", ".pgpass", ".git-credentials", ".pypirc",
    "secrets.json", "secrets.yaml", "secrets.yml", "service-account*.json",
    "db정보.txt", "environ",
)  # fmt: skip
# 와일드카드가 민감 파일을 가리킬 수 있는지 시험할 견본 이름
SENSITIVE_SAMPLES = (
    ".env", ".env.local", ".env.production", "prod.env", "id_rsa", "id_ed25519", "server.pem", "server.key",
    "credentials", "credentials.json", ".netrc", ".pgpass", ".git-credentials", "secrets.json", "db정보.txt",
)  # fmt: skip
SENSITIVE_IN_TEXT = re.compile(
    r"(?<![\w.-])(\.env(?!\.(?:example|sample|template)\b)(?:\.[\w-]+)?|id_rsa|id_ed25519|\.pgpass|\.netrc"
    r"|\.git-credentials|db정보\.txt|credentials\.json)(?![\w-])",
    re.IGNORECASE,
)
SECRET_NAME_RE = re.compile(
    r"SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|API_?KEY|ACCESS_?KEY|SERVICE_ROLE|DATABASE_URL|DB_URL"
    r"|(^|_)(PASS|KEY|AUTH|DSN)($|_)",
    re.IGNORECASE,
)
VAR_REF_RE = re.compile(r"\$\{?(?:env:)?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)

# 민감 파일 이름이 나와도 내용을 읽지 않는 명령 (존재 확인, 삭제, 이름 출력)
SENSITIVE_OK = {
    "ls", "dir", "ll", "test", "[", "[[", "stat", "file", "touch", "rm", "rmdir", "unlink", "del", "erase", "rd",
    "remove-item", "ri", "test-path", "get-item", "gi", "get-childitem", "gci", "mkdir", "md", "new-item", "ni",
    "realpath", "readlink", "basename", "dirname", "wc", "chmod", "chown", "attrib", "icacls", "echo", "printf",
    "write-output", "write-host", "cd", "pushd", "popd", "set-location", "sl", "find", "locate", "which", "where", "du",
}  # fmt: skip
# 민감 파일 내용을 출력·복사·전송하는 명령
READERS = {
    "cat", "tac", "less", "more", "head", "tail", "nl", "bat", "batcat", "type", "get-content", "gc", "sed", "awk",
    "gawk", "mawk", "grep", "egrep", "fgrep", "rg", "ag", "ack", "findstr", "select-string", "sls", "strings", "xxd",
    "od", "hexdump", "format-hex", "fhx", "base64", "base32", "cut", "sort", "uniq", "diff", "cmp", "jq", "yq", "vim",
    "vi", "nvim", "nano", "emacs", "code", "notepad", "cp", "copy", "copy-item", "cpi", "mv", "move", "move-item", "mi",
    "scp", "rsync", "curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod", "irm", "nc", "ncat", "netcat",
    "socat", "tar", "zip", "7z", "7za", "gzip", "bzip2", "xz", "compress-archive", "openssl", "gpg", "clip", "pbcopy",
    "xclip", "xsel", "set-clipboard", "scb", "tee",
}  # fmt: skip
COPY_COMMANDS = {"cp", "copy", "copy-item", "cpi", "mv", "move", "move-item", "mi", "scp", "rsync"}
# 첫 위치 인수가 파일이 아니라 패턴·스크립트인 명령
PATTERN_FIRST = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "sed", "awk", "gawk", "mawk", "jq", "yq", "findstr"}
GIT_SENSITIVE_OK = {"check-ignore", "status", "ls-files", "rm"}
GIT_SENSITIVE_DENY = {"add", "commit", "show", "diff", "log", "cat-file", "blame", "grep", "stash", "archive", "bundle", "format-patch"}
PRINTERS = {"echo", "printf", "print", "write-output", "write-host", "write", "out-host"}


def is_sensitive_basename(base: str) -> bool:
    name = base.lower()
    if not name or name.endswith(".pub"):
        return False
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return not name.endswith(SAFE_ENV_SUFFIXES)
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in SENSITIVE_GLOBS)


def path_candidates(token: str) -> list:
    """`--env-file=.env`, `@.env`, `host:.env` 같은 토큰에서 경로 후보를 꺼낸다."""
    candidates = [token]
    for separator in ("=", "@", ":"):
        if separator in token:
            candidates += [token.split(separator, 1)[1], token.rsplit(separator, 1)[1]]
    return candidates


def classify_path(token: str, shell: str) -> str | None:
    """민감 파일을 가리키면 'explicit', 와일드카드가 민감 파일과 맞을 수 있으면 'glob', 아니면 None."""
    separators = r"[\\/]" if shell in ("powershell", "cmd") else r"/"
    for candidate in path_candidates(token):
        path = candidate.strip().rstrip("/\\")
        if not path:
            continue
        if re.search(r"/proc/[^/\s]+/environ", path):
            return "explicit"
        base = re.split(separators, path)[-1]
        if is_sensitive_basename(base):
            return "explicit"
        if any(ch in base for ch in "*?["):
            pattern = base.lower()
            for sample in SENSITIVE_SAMPLES:
                # bash 기본 동작: 점으로 시작하는 파일은 점으로 시작하는 패턴만 맞는다.
                if sample.startswith(".") and not pattern.startswith("."):
                    continue
                if fnmatch.fnmatchcase(sample, pattern):
                    return "glob"
    return None


def file_arguments(seg: Segment) -> list:
    """민감 파일 검사 대상 인수. grep·sed 같은 명령의 패턴 인수는 뺀다."""
    if seg.name not in PATTERN_FIRST and seg.name not in ("select-string", "sls"):
        return seg.args
    files, pattern_seen, skip, take = [], False, False, False
    for arg in seg.args:
        if skip:
            skip = False
            continue
        if take:
            files.append(arg)
            take = False
            continue
        low = arg.lower()
        if arg in ("-e", "-f", "--regexp", "--file", "--expression") or low == "-pattern":
            pattern_seen, skip = True, True
            continue
        if low in ("-path", "-literalpath"):
            take = True
            continue
        if arg.startswith("-"):
            files.append(arg)
            continue
        if not pattern_seen:
            pattern_seen = True
            continue
        files.append(arg)
    return files


def check_sensitive_files(seg: Segment, ctx: Context) -> None:
    explicit, globbed = [], []
    for arg in file_arguments(seg):
        kind = classify_path(arg, ctx.shell)
        if kind == "explicit":
            explicit.append(arg)
        elif kind == "glob":
            globbed.append(arg)
    if not (explicit or globbed) or seg.name in SENSITIVE_OK:
        return
    targets = listing(explicit or globbed)
    if seg.name == "git":
        sub, _ = git_subcommand(seg.args)
        if sub in GIT_SENSITIVE_OK:
            return
        level = DENY if sub in GIT_SENSITIVE_DENY and explicit else ASK
        ctx.v.flag(level, f"git {sub}: 민감 파일({targets})이 커밋되거나 출력될 수 있습니다.")
        return
    if seg.name in COPY_COMMANDS:
        positional = [arg for arg in seg.args if not arg.startswith("-")]
        sources = [arg for arg in positional[:-1] if classify_path(arg, ctx.shell)]
        if sources:
            explicit_source = any(classify_path(arg, ctx.shell) == "explicit" for arg in sources)
            ctx.v.flag(DENY if explicit_source else ASK, f"{seg.name}: 민감 파일({listing(sources)})을 다른 곳으로 복사·이동합니다.")
        else:
            ctx.v.flag(ASK, f"{seg.name}: 민감 파일({targets})을 덮어쓸 수 있습니다.")
        return
    if seg.name in READERS:
        level = DENY if explicit else ASK
        ctx.v.flag(level, f"{seg.name}: 민감 파일({targets})의 내용을 출력·전송할 수 있습니다.")
    else:
        ctx.v.flag(ASK, f"{seg.name}: 민감 파일({targets})을 다루는 명령입니다.")


def check_redirections(redirects: list, ctx: Context) -> None:
    for operator, target in redirects:
        if operator.startswith("<<") or target.startswith("&"):
            continue
        kind = classify_path(target, ctx.shell)
        if not kind:
            continue
        if "<" in operator:
            level = DENY if kind == "explicit" else ASK
            ctx.v.flag(level, f"민감 파일({clip(target, 40)})의 내용을 명령 입력으로 읽습니다.")
        else:
            ctx.v.flag(ASK, f"민감 파일({clip(target, 40)})을 덮어쓰거나 내용을 덧붙입니다.")


def check_secret_variables(seg: Segment, ctx: Context) -> None:
    names = sorted({match.group(1) for match in VAR_REF_RE.finditer(seg.text) if SECRET_NAME_RE.search(match.group(1))})
    if not names:
        return
    if seg.name in PRINTERS:
        ctx.v.flag(DENY, f"{seg.name}: 민감한 환경 변수({listing(names)})의 값을 출력합니다.")
    else:
        ctx.v.flag(ASK, f"{seg.name}: 민감한 환경 변수({listing(names)})를 명령에 넘깁니다. 값이 출력되거나 외부로 나갈 수 있습니다.")


def check_env_dump(seg: Segment, ctx: Context) -> None:
    name, args = seg.name, seg.args
    positional = [arg for arg in args if not arg.startswith("-")]
    if name == "env" and not args:
        ctx.v.flag(DENY, "env: 모든 환경 변수(비밀 값 포함)를 출력합니다.")
    elif name == "printenv" and (not positional or any(SECRET_NAME_RE.search(arg) for arg in positional)):
        ctx.v.flag(DENY, "printenv: 환경 변수(비밀 값 포함)를 출력합니다.")
    elif name == "set" and ctx.shell == "bash" and not args:
        ctx.v.flag(DENY, "set: 모든 셸 변수와 환경 변수를 출력합니다.")
    elif name == "export" and (not args or args == ["-p"]):
        ctx.v.flag(DENY, "export -p: 모든 환경 변수를 출력합니다.")
    elif name in ("declare", "typeset") and not positional and (not args or any("p" in arg or "x" in arg for arg in args)):
        ctx.v.flag(DENY, f"{name} -p: 모든 변수를 출력합니다.")


PS_ITEM_COMMANDS = {"get-childitem", "gci", "ls", "dir", "get-item", "gi", "get-content", "gc", "cat", "type", "get-itemproperty", "gp"}


def check_ps_env_drive(seg: Segment, ctx: Context) -> None:
    for arg in seg.args:
        match = re.match(r"^env:[\\/]?(.*)$", arg, re.IGNORECASE)
        if match and (match.group(1) in ("", "*") or "*" in match.group(1) or SECRET_NAME_RE.search(match.group(1))):
            ctx.v.flag(DENY, f"{seg.name} env:: PowerShell 환경 변수 드라이브의 값(비밀 값 포함)을 출력합니다.")


# ───────── DB ─────────

SQL_RULES = (
    (DENY, re.compile(r"\bdrop\s+(table|database|schema|view|materialized\s+view|index|sequence|function|procedure"
                      r"|trigger|policy|role|user|owned|extension|type|domain)\b", re.IGNORECASE), "DROP"),
    (DENY, re.compile(r"\btruncate\s+(table\s+)?(only\s+)?[\"`\[]?[a-z_]", re.IGNORECASE), "TRUNCATE"),
    (DENY, re.compile(r"\bdelete\s+from\s+[\w.\"`\[\]]+\s*(;|$|\)|returning\b|--|')", re.IGNORECASE | re.MULTILINE), "WHERE 없는 DELETE"),
    (ASK, re.compile(r"\bdelete\s+from\b", re.IGNORECASE), "DELETE"),
    (ASK, re.compile(r"\bupdate\s+[\w.\"`\[\]]+\s+set\b(?![^;]*\bwhere\b)", re.IGNORECASE), "WHERE 없는 UPDATE"),
    (ASK, re.compile(r"\balter\s+table\b[^;]*\bdrop\b", re.IGNORECASE), "ALTER TABLE ... DROP"),
    (ASK, re.compile(r"\bdisable\s+row\s+level\s+security\b|\bgrant\s+all\b", re.IGNORECASE), "RLS 해제·전체 권한 부여"),
    (DENY, re.compile(r"\bdropDatabase\s*\(|\.drop\s*\(\s*\)|\bdeleteMany\s*\(\s*\{\s*\}\s*\)", re.IGNORECASE), "MongoDB 삭제"),
    (DENY, re.compile(r"\bflush(all|db)\b", re.IGNORECASE), "Redis 전체 삭제"),
)  # fmt: skip
DB_TOOL_RULES = (
    (DENY, re.compile(r"^dropdb\b"), "dropdb: 데이터베이스를 삭제합니다."),
    (DENY, re.compile(r"^dropuser\b"), "dropuser: DB 사용자를 삭제합니다."),
    (DENY, re.compile(r"^supabase\b.*\bdb\s+reset\b"), "supabase db reset: 데이터베이스를 초기화해 데이터가 모두 사라집니다."),
    (ASK, re.compile(r"^supabase\b.*\bdb\s+push\b"), "supabase db push: 원격 DB 스키마를 바꿉니다."),
    (ASK, re.compile(r"^supabase\b.*\b(migration\s+(repair|squash)|projects\s+delete)\b"), "supabase 마이그레이션 기록·프로젝트를 바꿉니다."),
    (DENY, re.compile(r"^prisma\b.*\bmigrate\s+reset\b"), "prisma migrate reset: 데이터베이스를 초기화합니다."),
    (DENY, re.compile(r"^prisma\b.*\bdb\s+push\b.*--(force-reset|accept-data-loss)"), "prisma db push --force-reset: 데이터를 지웁니다."),
    (DENY, re.compile(r"^(rails|rake)\b.*\bdb:(drop|reset|purge|schema:load)\b"), "rails db:drop/reset: 데이터베이스를 지웁니다."),
    (DENY, re.compile(r"\bmanage\.py\s+(flush|reset_db|sqlflush)\b"), "manage.py flush: 데이터베이스의 모든 데이터를 지웁니다."),
    (ASK, re.compile(r"^alembic\b.*\bdowngrade\b"), "alembic downgrade: 스키마를 되돌리며 데이터가 사라질 수 있습니다."),
    (DENY, re.compile(r"^(sequelize|knex)\b.*\b(db:drop|migrate:rollback\s+--all)\b"), "DB 삭제·전체 롤백입니다."),
)  # fmt: skip
DB_CLIENTS = {
    "psql", "mysql", "mariadb", "sqlite3", "sqlite", "sqlcmd", "mongosh", "mongo", "redis-cli", "clickhouse-client",
    "clickhouse", "duckdb", "cockroach", "pgcli", "mycli", "litecli", "usql", "bq", "snowsql", "osql", "isql", "supabase",
}  # fmt: skip
DB_FILE_OPTIONS = {"-f", "--file", "-i", "--input-file", "--source"}
HTTP_CLIENTS = {"curl", "wget", "http", "https", "xh", "invoke-webrequest", "iwr", "invoke-restmethod", "irm"}
# SQL 단어가 나와도 DB에 실행하지 않는 명령 (검색, 출력, 파일 쓰기, 커밋 메시지)
SQL_TEXT_OK = {
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "findstr", "select-string", "sls", "echo", "printf", "write-output",
    "write-host", "git", "cat", "tee", "less", "more", "head", "tail", "wc", "sed", "awk", "code", "vim", "nano",
    "notepad", "set-content", "add-content", "out-file", "new-item", "touch", "eval", "cmd", "powershell", "pwsh",
    "wsl", "ssh", "docker", "podman", "docker-compose", "kubectl", "iex", "invoke-expression", "find", "gh",
}  # fmt: skip


def sql_findings(texts: list) -> list:
    found = []
    for text in texts:
        for level, pattern, label in SQL_RULES:
            if pattern.search(text) and (level, label) not in found:
                found.append((level, label))
    # 같은 문장이 WHERE 없는 DELETE와 DELETE 둘 다에 걸리면 더 강한 쪽만 남긴다.
    if (DENY, "WHERE 없는 DELETE") in found and (ASK, "DELETE") in found:
        found.remove((ASK, "DELETE"))
    return found


def check_db_tools(seg: Segment, ctx: Context) -> None:
    joined = " ".join([seg.name, *seg.args]).lower()
    for level, pattern, message in DB_TOOL_RULES:
        if pattern.search(joined):
            ctx.v.flag(level, message)


def check_db_client(seg: Segment, ctx: Context) -> None:
    upstream = [other for other in ctx.pipeline if other.index < seg.index]
    texts = [seg.text, *seg.stdin_texts, *(other.text for other in upstream)]
    for level, label in sql_findings(texts):
        ctx.v.flag(level, f"{seg.name}: {label} 문으로 데이터가 삭제·변경될 수 있습니다.")
    if seg.name == "supabase":
        return
    reads_file = any(arg in DB_FILE_OPTIONS or arg.startswith("--file=") for arg in seg.args)
    reads_file |= any(op.startswith("<") and not op.startswith("<<") for op, _ in seg.redirects)
    reads_file |= any(other.name not in PRINTERS for other in upstream)
    if reads_file:
        ctx.v.flag(ASK, f"{seg.name}: SQL을 파일·파이프로 받아 실행할 내용을 확인할 수 없습니다.")


def check_http(seg: Segment, ctx: Context) -> None:
    joined = " ".join(seg.args)
    method_delete = re.search(r"(^|\s)(-x|--request|-method|--method)(\s+|=|:)?delete\b|-XDELETE\b", joined, re.IGNORECASE)
    if method_delete or (seg.name in ("http", "https", "xh") and seg.args[:1] and seg.args[0].upper() == "DELETE"):
        ctx.v.flag(ASK, f"{seg.name} DELETE 요청: 서버의 데이터가 삭제될 수 있습니다.")
    for level, label in sql_findings([seg.text]):
        ctx.v.flag(level, f"{seg.name}: 요청 본문에 {label} 문이 있어 원격 DB 데이터가 삭제·변경될 수 있습니다.")


def check_sql_text(seg: Segment, ctx: Context) -> None:
    """DB 클라이언트가 아닌 명령에 데이터 삭제 SQL이 보이면 실제 실행 여부를 알 수 없으므로 확인을 요청한다."""
    labels = [label for level, label in sql_findings([seg.text, *seg.stdin_texts]) if level == DENY]
    if labels:
        ctx.v.flag(ASK, f"{seg.name}: 명령에 데이터 삭제 SQL({listing(labels)})이 있습니다. DB에 실행되는지 확인하세요.")


# ───────── 인터프리터 인라인 코드 ─────────

CODE_DESTRUCTIVE = re.compile(
    r"\brmtree\b|\bos\.(remove|unlink|rmdir|removedirs)\b|\.unlink\s*\(|\.rmdir\s*\(|\brmSync\b|\brmdirSync\b"
    r"|\bunlinkSync\b|\bfs(\.promises)?\.rm\s*\(|\brimraf\b|\bFileUtils\.rm_r?f?\b|\bunlink\s*\(",
    re.IGNORECASE,
)
CODE_SHELL_EXEC = re.compile(r"\bsubprocess\b|\bos\.(system|popen|exec\w*)\b|\bchild_process\b|\bexecSync\b|\bspawnSync\b|\bsystem\s*\(|`", re.IGNORECASE)
CODE_ENV_DUMP = re.compile(
    r"print\s*\(\s*(dict\s*\(\s*)?os\.environ\s*\)?\s*\)|console\.log\s*\(\s*process\.env\s*\)"
    r"|JSON\.stringify\s*\(\s*process\.env\b|json\.dumps\s*\(\s*dict\s*\(\s*os\.environ",
    re.IGNORECASE,
)
CODE_FLAGS = {"python": {"-c"}, "node": {"-e", "--eval", "-p", "--print"}, "rubyperl": {"-e", "-E"}, "php": {"-r"}}


def interpreter_family(name: str) -> str | None:
    if name.startswith("python") or name in ("py", "pythonw"):
        return "python"
    if name in ("node", "nodejs", "bun"):
        return "node"
    if name == "deno":
        return "deno"
    if name in ("ruby", "perl"):
        return "rubyperl"
    if name == "php":
        return "php"
    return None


def scan_code(code: str, label: str, ctx: Context) -> None:
    if CODE_ENV_DUMP.search(code):
        ctx.v.flag(DENY, f"{label}: 모든 환경 변수(비밀 값 포함)를 출력합니다.")
    if CODE_DESTRUCTIVE.search(code):
        ctx.v.flag(ASK, f"{label}: 파일·폴더를 삭제하는 코드가 있습니다.")
    sql = [name for _, name in sql_findings([code])]
    if sql:
        ctx.v.flag(ASK, f"{label}: 데이터 삭제·변경 SQL({listing(sql)})이 있습니다.")
    secret = SENSITIVE_IN_TEXT.search(code)
    if secret:
        ctx.v.flag(ASK, f"{label}: 민감 파일({secret.group(0)})을 다룹니다.")
    if CODE_SHELL_EXEC.search(code) and fallback_hits(code, force=True):
        ctx.v.flag(ASK, f"{label}: 위험한 셸 명령을 실행하는 코드가 있습니다.")


def check_interpreter(seg: Segment, ctx: Context) -> None:
    family = interpreter_family(seg.name)
    flags = CODE_FLAGS.get(family, set())
    code, reads_stdin = None, True
    for i, arg in enumerate(seg.args):
        is_code_flag = arg in flags or (family == "python" and re.fullmatch(r"-[A-Za-z]*c", arg))
        if is_code_flag or (family == "deno" and arg == "eval"):
            code = seg.args[i + 1] if i + 1 < len(seg.args) else ""
            break
        if arg == "-":
            break
        if arg == "-m" or (family == "python" and arg.startswith("-m")) or not arg.startswith("-"):
            reads_stdin = False
            break
    label = f"{seg.name} 인라인 코드"
    if code is not None:
        scan_code(code, label, ctx)
        return
    if not reads_stdin:
        # 스크립트 파일 실행. 파일 내용은 검사하지 않고, 인수로 넘기는 SQL만 확인한다.
        check_sql_text(seg, ctx)
        return
    for body in seg.stdin_texts:
        scan_code(body, label, ctx)
    if seg.index > 0:
        ctx.v.flag(ASK, f"파이프로 받은 코드를 {seg.name}이(가) 실행합니다. 내용을 확인할 수 없습니다.")


# ───────── 명령 분배 ─────────

DISK_DESTROYERS = {"shred", "wipe", "srm", "dd", "diskpart", "fdisk", "sfdisk", "parted", "wipefs",
                   "format-volume", "clear-disk", "initialize-disk", "remove-partition"}  # fmt: skip
PS_REMOVE = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}
CHECKERS = {
    "git": check_git,
    "rm": check_rm,
    "find": check_find,
    "env": check_env_dump,
    "printenv": check_env_dump,
    "set": check_env_dump,
    "export": check_env_dump,
    "declare": check_env_dump,
    "typeset": check_env_dump,
    "cmd": check_cmd,
    "powershell": check_powershell,
    "pwsh": check_powershell,
    "eval": check_eval,
    "iex": check_invoke_expression,
    "invoke-expression": check_invoke_expression,
    "wsl": check_wsl,
    "ssh": check_ssh,
    "docker": check_docker,
    "podman": check_docker,
    "nerdctl": check_docker,
    "docker-compose": check_docker,
    "kubectl": check_kubectl,
    "gh": check_gh,
    "rimraf": check_rimraf,
    "truncate": check_truncate,
    "clear-content": check_truncate,
    "clc": check_truncate,
    **dict.fromkeys(SHELLS, check_shell),
    **dict.fromkeys(DISK_DESTROYERS, check_disk),
}


def check_segment(seg: Segment, ctx: Context) -> None:
    name = seg.name
    if {"sudo", "doas"} & set(seg.wrappers):
        ctx.v.flag(ASK, f"관리자 권한(sudo)으로 {name}을(를) 실행합니다.")
    check_sensitive_files(seg, ctx)
    check_secret_variables(seg, ctx)
    if ctx.shell == "powershell" and name in PS_REMOVE:
        check_remove_item(seg, ctx)
    elif ctx.shell == "cmd" and name in ("rd", "rmdir", "del", "erase"):
        check_cmd_delete(seg, ctx)
    elif interpreter_family(name):
        check_interpreter(seg, ctx)
    elif name.startswith("mkfs"):
        check_disk(seg, ctx)
    elif name in CHECKERS:
        CHECKERS[name](seg, ctx)
    if ctx.shell == "powershell" and name in PS_ITEM_COMMANDS:
        check_ps_env_drive(seg, ctx)
    check_db_tools(seg, ctx)
    if name in DB_CLIENTS:
        check_db_client(seg, ctx)
    elif name in HTTP_CLIENTS:
        check_http(seg, ctx)
    elif name not in SQL_TEXT_OK and name not in SHELLS and not interpreter_family(name):
        check_sql_text(seg, ctx)


# ───────── 4단계: 난독화 대비 보조 검사 ─────────

OBFUSCATION_HINTS = re.compile(
    r"\$\{?IFS|\\x[0-9a-f]{2}|\\[0-7]{3}|\$'|''|\"\"|[a-z]\\[a-z]|\bbase64\b|frombase64string|\brev\b|\bxxd\b|\btr\s",
    re.IGNORECASE,
)
FALLBACK_RULES = (
    (re.compile(r"\brm\s+(?:-\S+\s+)*-[a-z]*(?:r[a-z]*f|f[a-z]*r)"), "rm -rf"),
    (re.compile(r"\brm\s+(?:\S+\s+)*--recursive"), "rm --recursive"),
    (re.compile(r"\bgit\b[^;&|]*\bpush\b[^;&|]*(?:--force|--mirror|\s-[a-z]*f\b|\s\+[\w/:-])"), "git push --force"),
    (re.compile(r"\bgit\b[^;&|]*\breset\b[^;&|]*--hard"), "git reset --hard"),
    (re.compile(r"\bgit\b[^;&|]*\bclean\b[^;&|]*\s-[a-z]*f"), "git clean -f"),
    (re.compile(r"\bdrop\s+(?:table|database|schema)\b"), "DROP TABLE"),
    (re.compile(r"\btruncate\s+table\b"), "TRUNCATE"),
    (re.compile(r"\bremove-item\b[^;|]*\s-r"), "Remove-Item -Recurse"),
    (re.compile(r"\b(?:rd|rmdir|del)\s+(?:/\w\s+)*/s\b"), "rd /s"),
    (re.compile(r"\b(?:rmtree|rmsync|rimraf)\b"), "재귀 삭제"),
    (re.compile(r"\bmkfs\b|\bdd\b[^;|]*\bof=/dev/|\bshred\b"), "디스크 삭제"),
    (re.compile(r"(?<![\w.])\.env\b(?!\.example)"), ".env 접근"),
    (re.compile(r"\bprintenv\b|\bget-childitem\s+env:"), "환경 변수 출력"),
)  # fmt: skip
BASE64_TOKEN = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")


def normalize_obfuscated(text: str) -> str:
    """흔한 난독화($IFS, 16진수·8진수 이스케이프, 빈 따옴표, 백슬래시)를 풀어 소문자로 만든다."""
    text = re.sub(r"\$\{?IFS\}?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), text)
    text = re.sub(r"[\"'`\\]", "", text)
    return re.sub(r"\s+", " ", text).lower()


def decoded_variants(text: str) -> list:
    variants = [normalize_obfuscated(text)]
    for token in BASE64_TOKEN.findall(text):
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=True)
        except (binascii.Error, ValueError):
            continue
        for encoding in ("utf-8", "utf-16-le"):
            try:
                decoded = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if decoded and sum(ch.isprintable() or ch.isspace() for ch in decoded) / len(decoded) > 0.9:
                variants.append(normalize_obfuscated(decoded))
    return variants


def fallback_hits(text: str, force: bool = False) -> list:
    """난독화 흔적이 있을 때만(force면 항상) 정규화한 명령에서 위험 형태를 찾는다."""
    if not force and not OBFUSCATION_HINTS.search(text):
        return []
    hits = []
    for variant in decoded_variants(text):
        for pattern, label in FALLBACK_RULES:
            if pattern.search(variant) and label not in hits:
                hits.append(label)
    return hits


# ───────── 진입점 ─────────


def decide(tool_name: str, command: str) -> Verdict:
    """도구 이름과 명령으로 판단한다. 테스트에서도 이 함수를 직접 부른다."""
    v = Verdict()
    shell = TOOL_SHELLS.get(tool_name)
    if shell is None or not command.strip():
        return v
    if len(command) > MAX_COMMAND_LENGTH:
        v.flag(ASK, f"명령이 너무 길어({len(command)}자) 끝까지 검사하지 않았습니다.")
        return v
    analyze(command, v, shell)
    if v.level == ALLOW:
        hits = fallback_hits(command)
        if hits:
            v.flag(ASK, f"난독화된 명령에서 위험한 형태({listing(hits)})가 보입니다. 우회 시도일 수 있어 확인이 필요합니다.")
    return v


def build_output(v: Verdict) -> dict | None:
    if v.level == ALLOW:
        return None
    reasons = "\n".join(f"- {reason}" for reason in v.reasons())
    if v.level == DENY:
        decision = "deny"
        message = (
            f"[{HOOK_NAME}] 위험한 명령으로 판단해 실행을 차단했습니다.\n{reasons}\n"
            "꼭 필요한 작업이면 사용자에게 위험과 이유를 설명하고 직접 실행하도록 요청하세요."
        )
    else:
        decision = "ask"
        message = f"[{HOOK_NAME}] 안전하다고 확실히 판단할 수 없어 사용자 확인이 필요합니다.\n{reasons}"
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": message,
        }
    }


def emit(output: dict | None) -> None:
    if output is not None:
        # ensure_ascii: 콘솔 코드페이지와 관계없이 JSON이 깨지지 않게 한다.
        sys.stdout.write(json.dumps(output, ensure_ascii=True) + "\n")


def ask_output(reason: str) -> dict:
    verdict = Verdict()
    verdict.flag(ASK, reason)
    return build_output(verdict)


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except ValueError:
        emit(ask_output("Hook 입력(JSON)을 해석하지 못해 명령을 검사하지 못했습니다."))
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") not in TOOL_SHELLS:
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0
    try:
        verdict = decide(payload["tool_name"], command)
    except Exception as error:  # noqa: BLE001 - 검사기 오류로 위험 명령이 자동 통과하지 않게 한다.
        emit(ask_output(f"검사기 내부 오류({type(error).__name__})로 판단하지 못했습니다."))
        return 0
    emit(build_output(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
