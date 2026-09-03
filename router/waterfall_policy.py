"""Data-driven coding route policy and inspectable run traces.

The existing ``SmartRouter`` decides how much prompt work can leave Claude.
This module answers the newer question: which coding tier should author and
review that work, and what concrete event is allowed to promote it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "routing.yaml"
DEFAULT_TRACE_PATH = Path.home() / ".waterfall" / "last_route.json"
AUTHOR_TIERS = ("draft", "implement", "harden", "escalate", "ceiling")


@dataclass(frozen=True)
class RepoSignals:
    """Optional facts that make a prompt classification less speculative."""

    file_count: int = 0
    languages: tuple[str, ...] = ()
    test_runner_present: bool = False
    previous_harden_failed: bool = False


@dataclass(frozen=True)
class RouteDecision:
    """Stable public JSON contract returned by ``waterfall classify``."""

    tier: str
    effort: str
    reason: str
    failure_cost: str
    frontend: bool
    long_horizon: bool
    suggested_models: tuple[str, ...]
    hardness: str = field(default="local", repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "effort": self.effort,
            "reason": self.reason,
            "failure_cost": self.failure_cost,
            "frontend": self.frontend,
            "long_horizon": self.long_horizon,
            "suggested_models": list(self.suggested_models),
        }


@dataclass(frozen=True)
class PromotionSignal:
    kind: str
    detail: str = ""
    blocking_defects: tuple[str, ...] = ()


@dataclass
class RunAttempt:
    role: str
    tier: str
    model: str
    effort: str
    status: str
    cost_usd: float = 0.0
    reason: str = ""
    blocking_defects: list[str] = field(default_factory=list)


@dataclass
class RunTrace:
    task_preview: str
    classified: dict[str, Any]
    task_hash: str = ""
    attempts: list[RunAttempt] = field(default_factory=list)
    promotions: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_cost_usd"] = round(self.total_cost_usd, 6)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunTrace":
        return cls(
            task_preview=str(data.get("task_preview", "")),
            classified=dict(data.get("classified", {})),
            task_hash=str(data.get("task_hash", "")),
            attempts=[RunAttempt(**attempt) for attempt in data.get("attempts", [])],
            promotions=list(data.get("promotions", [])),
            skipped=list(data.get("skipped", [])),
            total_cost_usd=float(data.get("total_cost_usd", 0.0)),
            created_at=str(data.get("created_at", "")),
        )


class RoutingPolicy:
    """Load tier/model choices from YAML and apply the promotion contract."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        self._tiers = {tier["id"]: tier for tier in self.config["tiers"]}
        self._validate()

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise RuntimeError(f"Could not load routing policy {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"Routing policy {path} must contain a mapping")
        return loaded

    def _validate(self) -> None:
        tier_ids = [tier.get("id") for tier in self.config.get("tiers", [])]
        if tier_ids != ["classify", *AUTHOR_TIERS]:
            raise ValueError("routing tiers must be classify, draft, implement, harden, escalate, ceiling")
        priorities = [tier.get("priority") for tier in self.config["tiers"]]
        if priorities != list(range(6)):
            raise ValueError("routing tier priorities must be contiguous from 0 through 5")
        models = self.config.get("models", {})
        for tier in self.config["tiers"]:
            missing = set(tier.get("models", [])) - set(models)
            if missing:
                raise ValueError(f"tier {tier['id']} references unknown models: {sorted(missing)}")

    @property
    def promotion_cap(self) -> int:
        return int(self.config.get("promotion_cap", 2))

    @property
    def tier_ids(self) -> tuple[str, ...]:
        return tuple(self._tiers)

    @property
    def efforts(self) -> tuple[str, ...]:
        return tuple(self.config.get("efforts", ("low", "medium", "high", "xhigh", "max")))

    def resolve_alias(self, name: str) -> str:
        aliases = self.config.get("aliases", {})
        seen: set[str] = set()
        resolved = name
        while resolved in aliases:
            if resolved in seen:
                raise ValueError(f"model alias cycle at {resolved}")
            seen.add(resolved)
            resolved = aliases[resolved]
        if resolved not in self.config["models"]:
            raise ValueError(f"unknown model alias {name!r}")
        return resolved

    def provider_id(self, model: str) -> str:
        return str(self.config["models"][self.resolve_alias(model)]["provider_id"])

    def model_metadata(self, model: str) -> dict[str, Any]:
        return dict(self.config["models"][self.resolve_alias(model)])

    def models_for(self, tier: str, *, frontend: bool = False) -> tuple[str, ...]:
        if tier not in self._tiers:
            raise ValueError(f"unknown tier {tier!r}")
        models = list(self._tiers[tier].get("models", []))
        if tier == "implement" and frontend and "kimi-k3" in models:
            models.remove("kimi-k3")
            models.insert(0, "kimi-k3")
        return tuple(models)

    def tier_for_model(self, model: str, effort: Optional[str] = None) -> str:
        resolved = self.resolve_alias(model)
        if resolved == "claude-fable-5.1":
            return "ceiling" if effort == "max" else "escalate"
        for tier in AUTHOR_TIERS:
            if resolved in self._tiers[tier].get("models", []):
                return tier
        configured = self.config["models"][resolved].get("default_tier")
        if configured in AUTHOR_TIERS:
            return str(configured)
        raise ValueError(f"model {model!r} is not assigned to an author tier")

    def effort_for(self, tier: str, requested: Optional[str] = None) -> str:
        if tier not in self._tiers:
            raise ValueError(f"unknown tier {tier!r}")
        effort = requested or str(self._tiers[tier]["effort"])
        allowed = self._tiers[tier].get("allowed_efforts", [self._tiers[tier]["effort"]])
        if effort not in allowed:
            raise ValueError(
                f"effort {effort!r} is not allowed for {tier}; choose from {', '.join(allowed)}"
            )
        return effort

    def classify(
        self,
        task: str,
        signals: Optional[RepoSignals] = None,
        *,
        tier: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> RouteDecision:
        signals = signals or RepoSignals()
        lower = task.lower()
        patterns = self.config.get("classification", {})

        def matches(group: str) -> bool:
            return any(
                re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", lower)
                for term in patterns.get(group, [])
            )

        frontend = matches("frontend") or any(
            language.lower() in {"css", "html", "tsx", "jsx"}
            for language in signals.languages
        )
        rare_bug = matches("rare_bug")
        cant_be_wrong = matches("cant_be_wrong")
        long_horizon = matches("long_horizon")
        repo_span = matches("repo_span") or signals.file_count >= 4
        trivial = matches("trivial") or (0 < signals.file_count <= 1 and len(task.split()) <= 24)
        high_failure = matches("high_failure_cost") or rare_bug or cant_be_wrong

        if high_failure:
            failure_cost = "high"
        elif repo_span or long_horizon or signals.test_runner_present:
            failure_cost = "medium"
        else:
            failure_cost = "low"

        if tier is not None:
            chosen_tier = tier
            hardness = "pinned"
            reason = f"user pinned {tier}"
        elif signals.previous_harden_failed:
            chosen_tier = "escalate"
            hardness = "previous-harden-failure"
            reason = "the same task previously failed harden"
        elif cant_be_wrong:
            chosen_tier = "escalate"
            hardness = "cant-be-wrong"
            reason = "explicit can't-be-wrong request"
        elif rare_bug:
            chosen_tier = "escalate"
            hardness = "rare-bug"
            reason = "rare failure mode with high estimated failure cost"
        elif long_horizon and failure_cost == "high":
            chosen_tier = "escalate"
            hardness = "long-horizon"
            reason = "long-horizon task with high estimated failure cost"
        elif long_horizon:
            chosen_tier = "harden"
            hardness = "long-horizon"
            reason = "long-horizon task starts at harden"
        elif repo_span:
            chosen_tier = "harden"
            hardness = "repo-span"
            reason = "repo-spanning work"
        elif trivial:
            chosen_tier = "draft"
            hardness = "trivial"
            reason = "small local change"
        else:
            chosen_tier = "implement"
            hardness = "local"
            reason = "local feature"

        if chosen_tier not in AUTHOR_TIERS:
            raise ValueError(f"tier must be one of {', '.join(AUTHOR_TIERS)}")
        chosen_effort = self.effort_for(chosen_tier, effort)
        models = self.models_for(chosen_tier, frontend=frontend)

        return RouteDecision(
            tier=chosen_tier,
            effort=chosen_effort,
            reason=(
                f"{reason}, tests exist" if signals.test_runner_present and "tests" not in reason
                else reason
            ),
            failure_cost=failure_cost,
            frontend=frontend,
            long_horizon=long_horizon,
            suggested_models=models,
            hardness=hardness,
        )

    def promotion_decision(
        self,
        signal: PromotionSignal,
        *,
        promotions_so_far: int,
        no_cap: bool = False,
    ) -> tuple[bool, str]:
        if not no_cap and promotions_so_far >= self.promotion_cap:
            return False, f"promotion cap reached ({self.promotion_cap})"
        allowed = set(self.config["promotion"]["allowed"])
        denied = set(self.config["promotion"]["denied"])
        if signal.kind in denied:
            return False, f"{signal.kind} is not a promotion reason"
        if signal.kind not in allowed:
            return False, f"unknown promotion signal {signal.kind}"
        if signal.kind == "reviewer_reject" and not signal.blocking_defects:
            return False, "reviewer rejection needs at least one concrete blocking defect"
        return True, signal.detail or signal.kind.replace("_", " ")

    @staticmethod
    def next_tier(tier: str) -> Optional[str]:
        if tier not in AUTHOR_TIERS:
            raise ValueError(f"unknown author tier {tier!r}")
        index = AUTHOR_TIERS.index(tier)
        return AUTHOR_TIERS[index + 1] if index + 1 < len(AUTHOR_TIERS) else None

    def reviewer_for(
        self,
        author_tier: str,
        author_model: str,
        *,
        high_risk: bool = False,
    ) -> tuple[str, str, str]:
        tier = self._tiers[author_tier]
        reviewer_tier = str(tier.get("reviewer_tier", author_tier))
        if high_risk and tier.get("high_risk_reviewer_models"):
            candidates = list(tier["high_risk_reviewer_models"])
        elif tier.get("reviewer_models"):
            candidates = list(tier["reviewer_models"])
        else:
            candidates = list(self._tiers[reviewer_tier]["models"])
        author_resolved = self.resolve_alias(author_model)
        reviewer = next(
            (candidate for candidate in candidates if self.resolve_alias(candidate) != author_resolved),
            None,
        )
        if reviewer is None:
            raise ValueError(f"no independent reviewer configured for {author_model} at {author_tier}")
        reviewer_effort = self.effort_for(reviewer_tier)
        return reviewer_tier, reviewer, reviewer_effort

    def fable_models(self) -> set[str]:
        return {
            name for name, metadata in self.config["models"].items()
            if "fable" in name or "fable" in str(metadata.get("provider_id", ""))
        }

    def default_path_starts_on_fable(self, task: str = "implement a local feature") -> bool:
        decision = self.classify(task)
        return bool(set(decision.suggested_models) & self.fable_models())


def save_trace(trace: RunTrace, path: Path = DEFAULT_TRACE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")


def task_hash(task: str) -> str:
    normalized = " ".join(task.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_trace(path: Path = DEFAULT_TRACE_PATH) -> RunTrace:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("No route trace yet. Run `waterfall run ...` first.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Route trace is invalid JSON: {path}") from exc
    return RunTrace.from_dict(data)


def same_task_failed_harden(task: str, path: Path = DEFAULT_TRACE_PATH) -> bool:
    try:
        trace = load_trace(path)
    except (FileNotFoundError, ValueError):
        return False
    if trace.task_hash != task_hash(task):
        return False
    return any(
        attempt.tier == "harden" and attempt.status in {
            "stuck", "provider-failed", "reject",
        }
        for attempt in trace.attempts
    ) or any(
        promotion.get("from") == "harden" for promotion in trace.promotions
    )


def parse_reviewer_verdict(text: str) -> tuple[str, list[str]]:
    """Parse the deliberately small PASS/REJECT reviewer protocol."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "INVALID", []
    first = lines[0].upper()
    if first.startswith("PASS"):
        verdict = "PASS"
    elif first.startswith("REJECT"):
        verdict = "REJECT"
    else:
        return "INVALID", []
    defects = [
        line.lstrip("-* 0123456789.").strip()
        for line in lines[1:]
        if line.lstrip("-* 0123456789.").strip()
        and not line.upper().startswith("ESCALATE:")
    ]
    non_blocking = (
        "style", "verbosity", "verbose", "more elegant", "missing comment",
        "add comments", "smarter model", "naming preference",
    )
    defects = [
        defect for defect in defects
        if not any(phrase in defect.lower() for phrase in non_blocking)
    ]
    return verdict, defects


def reviewer_prompt(task: str, author_output: str) -> str:
    return (
        "Review this proposed coding answer. Reply PASS, or REJECT followed only by "
        "concrete blocking defects. Ignore style, verbosity, comments, and elegance. "
        "End with ESCALATE: yes or ESCALATE: no.\n\n"
        f"TASK\n{task}\n\nPROPOSED ANSWER\n{author_output}"
    )


def format_why(trace: RunTrace) -> str:
    decision = trace.classified
    lines = [
        f"classified: {decision.get('reason', 'unknown')} -> {decision.get('tier', 'unknown')}",
    ]
    for attempt in trace.attempts:
        label = "tried" if attempt.role == "author" else "reviewed"
        detail = f"{attempt.model} {attempt.effort} (${attempt.cost_usd:.2f}, {attempt.status}"
        if attempt.reason:
            detail += f": {attempt.reason}"
        elif attempt.blocking_defects:
            detail += ": " + "; ".join(attempt.blocking_defects)
        lines.append(f"{label}: {detail})")
    for promotion in trace.promotions:
        lines.append(
            f"promoted: {promotion.get('from')} -> {promotion.get('to')} "
            f"({promotion.get('reason')})"
        )
    if trace.skipped:
        lines.append("skipped: " + ", ".join(trace.skipped))
    lines.append(f"total: ${trace.total_cost_usd:.2f}")
    return "\n".join(lines)
