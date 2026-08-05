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
  - A bare `cat <file>` (Bash) or `Get-Content`/`type <file>` (PowerShell)
    with no pipe/redirect -- i.e. dumping a whole file straight to stdout.
Reads that already specify offset/limit are trusted and never capped --
the caller has already narrowed the request. Piped or redirected shell
commands are never capped -- only a bare whole-file dump to stdout matches.

Contract: must NEVER raise, and must fail OPEN (allow) whenever the size
can't be determined -- missing file, unreadable path, unparseable
command. A bug here must never be able to brick every tool call in a
session; the worst acceptable failure mode is "the cap doesn't fire".
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CAP_TOKENS = int(os.environ.get("WATERFALL_RINGER_CAP_TOKENS", "8000"))

# Anchored to "the whole command is just a dump of one file to stdout" --
# a pipe, redirect, extra flag, or second command drops out of the match,
# which is intentional: those aren't the blind-dump footgun this targets.
_BASH_CAT_RE = re.compile(r'^cat\s+"?([^"|>\s][^|>]*?)"?\s*$')
_PWSH_CAT_RE = re.compile(r'^(?:Get-Content|type)\s+"?([^"|>\s][^|>]*?)"?\s*$', re.IGNORECASE)


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


def check_read(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    """Return a deny reason if a whole-file Read would blow the cap, else None."""
    if tool_input.get("offset") or tool_input.get("limit"):
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

    return (
        f"waterfall Ringer: {file_path} is ~{tokens:,} tokens ({size:,} bytes), "
        f"over the {cap_tokens:,}-token per-call cap. Read a narrower slice with "
        f"offset/limit, or use Grep to search it instead of reading it whole."
    )


def _check_whole_file_dump(
    command: str, pattern: re.Pattern, cwd: str, cap_tokens: int
) -> str | None:
    match = pattern.match(command.strip())
    if not match:
        return None
    file_path = match.group(1).strip()

    sized = _size_tokens(file_path, cwd)
    if sized is None:
        return None
    size, tokens = sized
    if tokens <= cap_tokens:
        return None

    return (
        f"waterfall Ringer: {file_path} is ~{tokens:,} tokens ({size:,} bytes), "
        f"over the {cap_tokens:,}-token per-call cap. Use Read with offset/limit, "
        f"or Grep, instead of dumping the whole file to stdout."
    )


def check_bash(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    return _check_whole_file_dump(tool_input.get("command", ""), _BASH_CAT_RE, cwd, cap_tokens)


def check_powershell(tool_input: dict, cwd: str, cap_tokens: int = CAP_TOKENS) -> str | None:
    return _check_whole_file_dump(tool_input.get("command", ""), _PWSH_CAT_RE, cwd, cap_tokens)


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
