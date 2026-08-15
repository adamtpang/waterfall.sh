"""PreToolUse hook -- the "Ringer": a hard per-call size cap on tool calls
that would dump an entire large file into context in one shot. This is the
one open item from TOKEN_COMPOUNDING.md's countermeasure list that
UserPromptSubmit doesn't cover: that hook only nudges on the *human's*
prompt before generation, so it can't stop Claude from, mid-task, Read-ing
a 500KB log file whole or `cat`-ing a huge file to stdout. Once that
content lands in the transcript it gets resent and re-billed as
reused-input on every later turn in the session -- this hook stops it
from landing in the first place.

Scope, deliberately narrow to avoid false positives:
  - Read with no offset/limit (a "read the whole thing" call) against a
    file over the cap.
  - A single output-heavy command (see _BASH_DUMP_COMMANDS /
    _PWSH_DUMP_COMMANDS below -- cat/less/more/xxd/hexdump/od/base64 on
    Bash, Get-Content/type/Format-Hex on PowerShell) invoked with exactly
    one non-flag file argument and no pipe/redirect/chaining -- i.e.
    dumping a whole file straight to stdout, however it's spelled.
Reads that already specify offset/limit are trusted and never capped --
the caller has already narrowed the request. Any pipe, redirect, `;`, or
`&&` drops a shell command out of scope entirely -- only a bare
whole-file-to-stdout dump matches, by design.

Known gap, not covered: commands whose output size isn't tied to a
single file's on-disk size and so can't be sized without running them
first -- `find`, `git log`, `grep`/`rg` without a match cap, `curl`,
recursive directory listings. A pre-execution hard cap is not possible
for those without executing them; that's a real limitation, not an
oversight, and the honest boundary of what a PreToolUse hook can enforce
before the command runs.

Contract: must NEVER raise, and must fail OPEN (allow) whenever the size
can't be determined -- missing file, unreadable path, unparseable
command, ambiguous multi-file invocation. A bug here must never be able
to brick every tool call in a session; the worst acceptable failure mode
is "the cap doesn't fire".
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CAP_TOKENS = int(os.environ.get("WATERFALL_RINGER_CAP_TOKENS", "8000"))

# Command names that, invoked bare against one file, dump that file's
# entire contents to stdout. Matched case-insensitively on the last path
# component of argv[0] (so "/usr/bin/cat" and "cat" are the same check).
_BASH_DUMP_COMMANDS = {"cat", "less", "more", "xxd", "hexdump", "od", "base64"}
_PWSH_DUMP_COMMANDS = {"get-content", "type", "format-hex"}

# Any of these in the raw command string takes it out of scope entirely --
# a pipe, redirect, or chained command means this isn't a blind dump.
_SHELL_OPERATORS = ("|", ">", "<", ";", "&&", "||", "\n")


def estimate_tokens(num_bytes: int) -> int:
    """Rough token estimate: ~4 bytes per token for English/code text."""
    return max(0, num_bytes // 4)


def _resolve(path_str: str, cwd: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(cwd) / path
    return path


def _size_tokens(path_str: str, cwd: str) -> tuple[int, int] | None:
    try:
        path = _resolve(path_str, cwd)
        size = path.stat().st_size
    except OSError:
        return None
    return size, estimate_tokens(size)


def _deny_reason(file_path: str, size: int, tokens: int, cap_tokens: int, suggestion: str) -> str:
    return (
        f"waterfall Ringer: {file_path} is ~{tokens:,} tokens ({size:,} bytes), "
        f"over the {cap_tokens:,}-token per-call cap. {suggestion}"
    )


def check_read(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    """Return a deny reason if a whole-file Read would blow the cap, else None."""
    # `pages` is the PDF equivalent of offset/limit (e.g. "1-10"); Read
    # itself caps PDF requests at 20 pages, so a narrowed `pages` value is
    # bounded content regardless of which 20 pages of a huge PDF.
    if tool_input.get("offset") or tool_input.get("limit") or tool_input.get("pages"):
        return None  # caller already narrowed the read -- trust it

    file_path = tool_input.get("file_path")
    if not file_path:
        return None

    sized = _size_tokens(file_path, cwd)
    if sized is None:
        return None
    size, tokens = sized
    if tokens <= cap_tokens:
        return None

    return _deny_reason(
        file_path, size, tokens, cap_tokens,
        "Read a narrower slice with offset/limit, or use Grep to search it instead of reading it whole.",
    )


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        return token[1:-1]
    return token


def _extract_whole_file_target(command: str, dump_commands: set[str]) -> str | None:
    """If `command` is exactly one dump command with exactly one file
    argument and nothing else (no pipe/redirect/chain), return that file
    argument. Otherwise None -- fail open on anything ambiguous."""
    stripped = command.strip()
    if not stripped or any(op in stripped for op in _SHELL_OPERATORS):
        return None

    try:
        # posix=False: posix mode treats backslash as an escape character,
        # which silently mangles Windows-style paths (C:\Users\... loses
        # its backslashes). False preserves them; quotes are stripped
        # manually below instead.
        tokens = shlex.split(stripped, posix=False)
    except ValueError:
        return None  # unbalanced quotes etc -- don't guess
    if not tokens:
        return None

    cmd_name = _strip_quotes(tokens[0]).lower().replace("\\", "/").rsplit("/", 1)[-1]
    if cmd_name not in dump_commands:
        return None

    positional = [_strip_quotes(t) for t in tokens[1:] if not t.startswith("-")]
    if len(positional) != 1:
        return None  # zero or multiple file args -- ambiguous, don't guess

    return positional[0]


def _check_whole_file_dump(
    command: str, dump_commands: set[str], cwd: str, cap_tokens: int
) -> str | None:
    file_path = _extract_whole_file_target(command, dump_commands)
    if file_path is None:
        return None

    sized = _size_tokens(file_path, cwd)
    if sized is None:
        return None
    size, tokens = sized
    if tokens <= cap_tokens:
        return None

    return _deny_reason(
        file_path, size, tokens, cap_tokens,
        "Use Read with offset/limit, or Grep, instead of dumping the whole file to stdout.",
    )


def check_bash(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    return _check_whole_file_dump(tool_input.get("command", ""), _BASH_DUMP_COMMANDS, cwd, cap_tokens)


def check_powershell(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    return _check_whole_file_dump(tool_input.get("command", ""), _PWSH_DUMP_COMMANDS, cwd, cap_tokens)


def evaluate(tool_name: str, tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    if tool_name == "Read":
        return check_read(tool_input, cwd, cap_tokens)
    if tool_name == "Bash":
        return check_bash(tool_input, cwd, cap_tokens)
    if tool_name == "PowerShell":
        return check_powershell(tool_input, cwd, cap_tokens)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    try:
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input") or {}
        cwd = payload.get("cwd") or os.getcwd()
        reason = evaluate(tool_name, tool_input, cwd)
    except Exception:
        return 0

    if reason is None:
        return 0

    try:
        from hook_log import log_deny
        log_deny(cwd, f"{tool_name}: {reason}")
    except Exception:
        pass  # logging is a side effect -- never let it block the deny itself

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
