"""Execute the coding waterfall through the repository's OpenRouter client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

try:
    from .openrouter_api_client import GenerateResult, OpenRouterClient
    from .waterfall_policy import (
        PromotionSignal,
        RepoSignals,
        RoutingPolicy,
        RunAttempt,
        RunTrace,
        parse_reviewer_verdict,
        reviewer_prompt,
        task_hash,
    )
except ImportError:
    from openrouter_api_client import GenerateResult, OpenRouterClient
    from waterfall_policy import (
        PromotionSignal,
        RepoSignals,
        RoutingPolicy,
        RunAttempt,
        RunTrace,
        parse_reviewer_verdict,
        reviewer_prompt,
        task_hash,
    )


AUTHOR_SYSTEM = (
    "You are the author for a coding task. Return a concrete implementation or patch. "
    "Do not ask for a smarter model. If required context is missing, say STUCK and name it."
)
REVIEWER_SYSTEM = "You are an independent blocking-defect reviewer. Keep the verdict short."


class Generator(Protocol):
    def generate(self, prompt: str, model: str, effort: str, system: str) -> GenerateResult:
        ...


class OpenRouterGenerator:
    def __init__(self, client: Optional[OpenRouterClient] = None) -> None:
        self.client = client or OpenRouterClient()

    def generate(self, prompt: str, model: str, effort: str, system: str) -> GenerateResult:
        return self.client.generate_with_usage(
            prompt,
            model=model,
            system=system,
            output_effort=effort,
            temperature=0.2,
        )


@dataclass
class WaterfallRunResult:
    output: str
    passed: bool
    trace: RunTrace


def _looks_stuck(text: str) -> bool:
    lowered = text.strip().lower()
    return not lowered or lowered.startswith("stuck") or lowered.startswith("i cannot") or lowered.startswith("i can't")


def _next_route(policy: RoutingPolicy, tier: str, effort: str) -> tuple[Optional[str], Optional[str]]:
    if tier == "escalate" and effort == "high":
        return "escalate", "xhigh"
    return policy.next_tier(tier), None


def execute_waterfall(
    task: str,
    *,
    policy: Optional[RoutingPolicy] = None,
    generator: Optional[Generator] = None,
    signals: Optional[RepoSignals] = None,
    tier: Optional[str] = None,
    effort: Optional[str] = None,
    no_cap: bool = False,
) -> WaterfallRunResult:
    """Author, independently review, and promote only on blocking failure."""

    policy = policy or RoutingPolicy()
    generator = generator or OpenRouterGenerator()
    decision = policy.classify(task, signals, tier=tier, effort=effort)
    trace = RunTrace(
        task_preview=task[:200], classified=decision.to_dict(), task_hash=task_hash(task)
    )
    current_tier = decision.tier
    current_effort = decision.effort
    promotions = 0
    last_output = ""

    while True:
        author_output = ""
        author_model = ""
        for candidate in policy.models_for(current_tier, frontend=decision.frontend):
            provider_id = policy.provider_id(candidate)
            try:
                response = generator.generate(task, provider_id, current_effort, AUTHOR_SYSTEM)
            except Exception as exc:
                trace.attempts.append(RunAttempt(
                    role="author", tier=current_tier, model=candidate,
                    effort=current_effort, status="provider-failed", reason=str(exc),
                ))
                continue
            author_model = candidate
            author_output = response.text
            last_output = response.text
            stuck = _looks_stuck(response.text)
            trace.attempts.append(RunAttempt(
                role="author", tier=current_tier, model=candidate,
                effort=current_effort, status="stuck" if stuck else "answered",
                cost_usd=float(response.cost_usd),
                reason="empty or self-reported stuck" if stuck else "",
            ))
            trace.total_cost_usd += float(response.cost_usd)
            if not stuck:
                break

        if not author_output or _looks_stuck(author_output):
            signal = PromotionSignal("author_stuck", "author models failed or returned stuck")
            promote, reason = policy.promotion_decision(
                signal, promotions_so_far=promotions, no_cap=no_cap
            )
            next_tier, next_effort = _next_route(policy, current_tier, current_effort)
            if not promote or next_tier is None:
                break
            trace.promotions.append({"from": current_tier, "to": next_tier, "reason": reason})
            promotions += 1
            current_tier = next_tier
            current_effort = next_effort or policy.effort_for(next_tier)
            continue

        reviewer_tier, reviewer_model, reviewer_effort = policy.reviewer_for(
            current_tier,
            author_model,
            high_risk=decision.failure_cost == "high",
        )
        try:
            review = generator.generate(
                reviewer_prompt(task, author_output),
                policy.provider_id(reviewer_model),
                reviewer_effort,
                REVIEWER_SYSTEM,
            )
        except Exception as exc:
            trace.attempts.append(RunAttempt(
                role="reviewer", tier=reviewer_tier, model=reviewer_model,
                effort=reviewer_effort, status="provider-failed", reason=str(exc),
            ))
            break

        verdict, defects = parse_reviewer_verdict(review.text)
        trace.attempts.append(RunAttempt(
            role="reviewer", tier=reviewer_tier, model=reviewer_model,
            effort=reviewer_effort, status=verdict.lower(),
            cost_usd=float(review.cost_usd),
            blocking_defects=defects if verdict == "REJECT" else [],
        ))
        trace.total_cost_usd += float(review.cost_usd)
        if verdict == "PASS":
            _add_skipped_fable(trace, policy)
            return WaterfallRunResult(output=author_output, passed=True, trace=trace)

        signal = PromotionSignal(
            "reviewer_reject",
            "reviewer found a blocking defect",
            tuple(defects),
        )
        promote, reason = policy.promotion_decision(
            signal, promotions_so_far=promotions, no_cap=no_cap
        )
        next_tier, next_effort = _next_route(policy, current_tier, current_effort)
        if not promote or next_tier is None:
            break
        trace.promotions.append({"from": current_tier, "to": next_tier, "reason": reason})
        promotions += 1
        task = (
            f"{task}\n\nA previous answer was rejected for these blocking defects:\n"
            + "\n".join(f"- {defect}" for defect in defects)
        )
        current_tier = next_tier
        current_effort = next_effort or policy.effort_for(next_tier)

    _add_skipped_fable(trace, policy)
    return WaterfallRunResult(output=last_output, passed=False, trace=trace)


def _add_skipped_fable(trace: RunTrace, policy: RoutingPolicy) -> None:
    tried = {attempt.model for attempt in trace.attempts}
    if not (tried & policy.fable_models()):
        trace.skipped.append("claude-fable-5.1")
