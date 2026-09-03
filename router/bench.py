"""Small executable coding harness that emits leaderboard-ready JSONL."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Optional

try:
    from .waterfall_policy import RoutingPolicy, parse_reviewer_verdict, reviewer_prompt
    from .waterfall_run import Generator, OpenRouterGenerator, REVIEWER_SYSTEM
except ImportError:
    from waterfall_policy import RoutingPolicy, parse_reviewer_verdict, reviewer_prompt
    from waterfall_run import Generator, OpenRouterGenerator, REVIEWER_SYSTEM


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITES_DIR = ROOT / "data" / "suites"
DEFAULT_RUNS_DIR = ROOT / "data" / "runs"
EXPECTED_CATEGORY_COUNTS = {
    "one-file-bugfix": 5,
    "multi-file-feature": 5,
    "review-only": 3,
    "long-horizon": 2,
}
PATCH_SYSTEM = (
    "Solve the self-contained coding task. Return only a git-compatible unified diff "
    "inside one ```diff fence. Do not edit tests or files outside the allowed list."
)


@dataclass
class BenchAttempt:
    record_type: str
    timestamp: str
    suite: str
    task_id: str
    category: str
    model: str
    effort: str
    input_tokens: int
    output_tokens: int
    cache_reads: int
    cost_usd: float
    cost_at_list_cache_usd: float
    wall_time: float
    passed: bool
    escalate_count: int
    reviewer_model: str
    reviewer_verdict: str
    verification: str
    failure_reason: str


def load_suite(name: str, suites_dir: Path = DEFAULT_SUITES_DIR) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("suite name may contain lowercase letters, digits, and hyphens")
    path = Path(suites_dir) / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_suite(data)
    return data


def validate_suite(suite: dict[str, Any]) -> None:
    if suite.get("schema_version") != 1 or not suite.get("id"):
        raise ValueError("benchmark suite needs schema_version 1 and an id")
    counts = {category: 0 for category in EXPECTED_CATEGORY_COUNTS}
    ids: set[str] = set()
    for task in suite.get("tasks", []):
        task_id = task.get("id")
        category = task.get("category")
        if not task_id or task_id in ids:
            raise ValueError("benchmark task ids must be present and unique")
        if category not in counts:
            raise ValueError(f"unknown benchmark category {category!r}")
        if task.get("mode") not in {"patch", "review"}:
            raise ValueError(f"task {task_id} needs patch or review mode")
        if task["mode"] == "patch" and (not task.get("files") or not task.get("allowed_files")):
            raise ValueError(f"patch task {task_id} needs files and allowed_files")
        ids.add(task_id)
        counts[category] += 1
    if counts != EXPECTED_CATEGORY_COUNTS:
        raise ValueError(f"coding-smoketest category counts must be {EXPECTED_CATEGORY_COUNTS}, got {counts}")


def _safe_relative(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
        raise ValueError(f"unsafe benchmark path {raw!r}")
    return path


def _task_prompt(task: dict[str, Any]) -> str:
    files = []
    for name, content in task["files"].items():
        files.append(f"--- {name} ---\n{content}")
    allowed = ", ".join(task["allowed_files"])
    return (
        f"{task['prompt']}\n\nAllowed files: {allowed}\n\n"
        "CURRENT FILES\n" + "\n".join(files)
    )


def extract_diff(text: str) -> str:
    fenced = re.search(r"```(?:diff|patch)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip() + "\n"
    starts = [position for marker in ("diff --git ", "--- a/") if (position := text.find(marker)) >= 0]
    if starts:
        return text[min(starts):].strip() + "\n"
    raise ValueError("author did not return a unified diff")


def changed_paths(patch: str) -> set[str]:
    paths = set(re.findall(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE))
    if not paths:
        paths = {match[1] for match in re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE)}
    return {str(_safe_relative(path)) for path in paths if path != "/dev/null"}


def _write_fixture(directory: Path, files: dict[str, str]) -> None:
    for raw, content in files.items():
        relative = _safe_relative(raw)
        target = directory.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def verify_patch(task: dict[str, Any], patch: str) -> tuple[bool, str]:
    changed = changed_paths(patch)
    allowed = {str(_safe_relative(path)) for path in task["allowed_files"]}
    if not changed:
        return False, "diff is empty"
    if changed - allowed:
        return False, "diff edits files outside the allowed list: " + ", ".join(sorted(changed - allowed))
    if len(changed) < int(task.get("min_changed_files", 1)):
        return False, f"diff changes {len(changed)} files; task requires {task.get('min_changed_files', 1)}"

    with tempfile.TemporaryDirectory(prefix="waterfall-bench-") as tmp:
        workspace = Path(tmp)
        _write_fixture(workspace, task["files"])
        check = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            cwd=workspace,
            input=patch,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if check.returncode:
            return False, "patch does not apply: " + (check.stderr.strip() or check.stdout.strip())[:300]
        applied = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=workspace,
            input=patch,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if applied.returncode:
            return False, "patch application failed: " + (applied.stderr.strip() or applied.stdout.strip())[:300]
        tested = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if tested.returncode:
            detail = (tested.stdout + "\n" + tested.stderr).strip()
            return False, "tests failed: " + detail[-500:]
    return True, "tests passed"


def _usage(response: Any) -> tuple[int, int, int, float]:
    return (
        int(getattr(response, "input_tokens", 0) or 0),
        int(getattr(response, "output_tokens", 0) or 0),
        int(getattr(response, "cache_read_tokens", 0) or 0),
        float(getattr(response, "cost_usd", 0.0) or 0.0),
    )


def _review_task(task: dict[str, Any], response_text: str) -> tuple[bool, str, str]:
    verdict, _defects = parse_reviewer_verdict(response_text)
    expected = task["expected_verdict"]
    lower = response_text.lower()
    terms_ok = all(term.lower() in lower for term in task.get("required_terms", []))
    passed = verdict == expected and terms_ok
    reason = "review matched expected blocking verdict" if passed else (
        f"expected {expected} with terms {task.get('required_terms', [])}, got {verdict}"
    )
    return passed, verdict, reason


def run_attempt(
    suite_id: str,
    task: dict[str, Any],
    model: str,
    *,
    effort: Optional[str] = None,
    policy: Optional[RoutingPolicy] = None,
    generator: Optional[Generator] = None,
) -> BenchAttempt:
    policy = policy or RoutingPolicy()
    generator = generator or OpenRouterGenerator()
    resolved_model = policy.resolve_alias(model)
    author_tier = policy.tier_for_model(resolved_model, effort)
    selected_effort = policy.effort_for(author_tier, effort)
    started = time.monotonic()
    total_in = total_out = total_cache = 0
    total_cost = 0.0
    reviewer_model = ""
    reviewer_verdict = "not-run"

    if task["mode"] == "review":
        response = generator.generate(
            task["prompt"], policy.provider_id(resolved_model), selected_effort, REVIEWER_SYSTEM
        )
        total_in, total_out, total_cache, total_cost = _usage(response)
        passed, reviewer_verdict, reason = _review_task(task, response.text)
        verification = "expected-review-verdict"
        reviewer_model = resolved_model
    else:
        response = generator.generate(
            _task_prompt(task), policy.provider_id(resolved_model), selected_effort, PATCH_SYSTEM
        )
        total_in, total_out, total_cache, total_cost = _usage(response)
        try:
            patch = extract_diff(response.text)
            tests_passed, reason = verify_patch(task, patch)
        except (ValueError, subprocess.SubprocessError) as exc:
            patch = ""
            tests_passed, reason = False, str(exc)
        passed = False
        verification = "tests"
        if tests_passed:
            _reviewer_tier, reviewer_model, reviewer_effort = policy.reviewer_for(
                author_tier, resolved_model, high_risk=task["category"] == "long-horizon"
            )
            try:
                review = generator.generate(
                    reviewer_prompt(task["prompt"], patch),
                    policy.provider_id(reviewer_model),
                    reviewer_effort,
                    REVIEWER_SYSTEM,
                )
            except Exception as exc:
                reviewer_verdict = "provider-failed"
                reason = f"reviewer provider failed: {exc}"
            else:
                review_in, review_out, review_cache, review_cost = _usage(review)
                total_in += review_in
                total_out += review_out
                total_cache += review_cache
                total_cost += review_cost
                reviewer_verdict, defects = parse_reviewer_verdict(review.text)
                passed = reviewer_verdict == "PASS"
                if not passed:
                    reason = "reviewer rejected: " + "; ".join(defects)

    return BenchAttempt(
        record_type="bench_attempt",
        timestamp=datetime.now(timezone.utc).isoformat(),
        suite=suite_id,
        task_id=task["id"],
        category=task["category"],
        model=resolved_model,
        effort=selected_effort,
        input_tokens=total_in,
        output_tokens=total_out,
        cache_reads=total_cache,
        cost_usd=round(total_cost, 8),
        cost_at_list_cache_usd=round(total_cost, 8),
        wall_time=round(time.monotonic() - started, 3),
        passed=passed,
        escalate_count=0,
        reviewer_model=reviewer_model,
        reviewer_verdict=reviewer_verdict,
        verification=verification,
        failure_reason="" if passed else reason,
    )


def append_attempt(attempt: BenchAttempt, output_path: Optional[Path] = None) -> Path:
    path = Path(output_path) if output_path else DEFAULT_RUNS_DIR / f"{attempt.timestamp[:10]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(asdict(attempt), separators=(",", ":")) + "\n")
    return path


def run_suite(
    suite: dict[str, Any],
    models: Iterable[str],
    *,
    effort: Optional[str] = None,
    output_path: Optional[Path] = None,
    limit: Optional[int] = None,
    policy: Optional[RoutingPolicy] = None,
    generator: Optional[Generator] = None,
    progress: Optional[Callable[[BenchAttempt], None]] = None,
) -> list[BenchAttempt]:
    policy = policy or RoutingPolicy()
    generator = generator or OpenRouterGenerator()
    tasks = suite["tasks"][:limit] if limit else suite["tasks"]
    attempts = []
    for model in models:
        for task in tasks:
            try:
                attempt = run_attempt(
                    suite["id"], task, model, effort=effort, policy=policy, generator=generator
                )
            except Exception as exc:
                resolved = policy.resolve_alias(model)
                tier = policy.tier_for_model(resolved, effort)
                attempt = BenchAttempt(
                    record_type="bench_attempt",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    suite=suite["id"],
                    task_id=task["id"],
                    category=task["category"],
                    model=resolved,
                    effort=policy.effort_for(tier, effort),
                    input_tokens=0,
                    output_tokens=0,
                    cache_reads=0,
                    cost_usd=0.0,
                    cost_at_list_cache_usd=0.0,
                    wall_time=0.0,
                    passed=False,
                    escalate_count=0,
                    reviewer_model="",
                    reviewer_verdict="not-run",
                    verification="provider",
                    failure_reason=f"provider failed: {exc}",
                )
            append_attempt(attempt, output_path)
            attempts.append(attempt)
            if progress:
                progress(attempt)
    return attempts
