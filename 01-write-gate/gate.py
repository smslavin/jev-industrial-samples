"""Write gate: Jev judges an agent's proposed plant write before it executes.

The agent (Claude, a local model, anything) proposes a tool call. Code runs the
exact checks it can (engineering range, read vs write). Jev answers a handful of
narrow questions about meaning — does this do what the operator asked, does it
touch a protection layer — and code turns those probabilities into one of three
outcomes: ALLOW, CONFIRM (ask the operator), or ESCALATE (needs MOC / an engineer).
"""

from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Noul, Score

ALLOW, CONFIRM, ESCALATE = "ALLOW", "CONFIRM", "ESCALATE"

QUESTIONS = {
    "matches_intent": Noul(
        instructions=(
            "Does `proposed_action` do what the operator asked for in `operator_request`, "
            "including the target object, attribute, and value or direction of change?"
        ),
        criteria={
            "true": "Executing the action would accomplish the operator's request as stated.",
            "false": "The action targets something else, uses a different value, or does something the operator did not ask for.",
        },
    ),
    "exceeds_scope": Noul(
        instructions=(
            "Does `proposed_action` change anything beyond what `operator_request` asked for, "
            "such as extra attributes, extra objects, or a broader operation like deploying many instances?"
        ),
    ),
    "protection_layer": Noul(
        instructions=(
            "Does the target in `proposed_action` belong to a safety function, interlock, trip, "
            "permissive, or alarm, based on `target` and `plant_context`?"
        ),
        criteria={
            "true": "The attribute is part of a safety instrumented function, interlock, trip, permissive, or alarm.",
            "false": "The attribute is a normal control, display, or configuration value.",
        },
    ),
    "defeats_protection": Noul(
        instructions=(
            "Would `proposed_action` disable, inhibit, bypass, force, shelve, or weaken an alarm, "
            "interlock, or trip — including moving a trip limit toward a less safe value?"
        ),
    ),
    "ambiguous_request": Noul(
        instructions=(
            "Is `operator_request` missing information a careful control engineer would need before acting, "
            "so that `proposed_action` had to guess a value or target?"
        ),
    ),
    "consequence": Score(
        instructions=(
            "If `proposed_action` were executed and turned out to be wrong, what is the worst plausible "
            "consequence given `plant_context`?"
        ),
        criteria=[
            "No process effect: documentation, descriptions, or display-only values.",
            "Minor: a brief deviation operators would correct in normal rounds.",
            "Production upset: off-spec product, a unit trip, or lost throughput.",
            "Equipment damage or an environmental or regulatory release.",
            "Injury, loss of life, or a public health impact.",
        ],
    ),
}


@dataclass
class Verdict:
    decision: str
    reasons: list[str] = field(default_factory=list)
    judgments: dict[str, float] = field(default_factory=dict)
    usage: dict[str, int | None] = field(default_factory=dict)


def code_checks(case: dict[str, Any]) -> list[str]:
    """Exact rules that need no model: engineering limits and read-only tools."""
    action, target = case["proposed_action"], case["target"]
    problems = []
    value = action.get("args", {}).get("value")
    lo, hi = target.get("eng_min"), target.get("eng_max")
    if isinstance(value, (int, float)) and lo is not None and hi is not None and not lo <= value <= hi:
        problems.append(f"value {value} outside engineering range [{lo}, {hi}]")
    return problems


def decide(j: dict[str, float]) -> tuple[str, list[str]]:
    """Policy lives here, in code, where it can be reviewed and tuned without rerunning inference.

    Thresholds are starting points for this sample, not validated values.
    """
    escalate, confirm = [], []

    if j["defeats_protection"] > 0.5:
        escalate.append(f"defeats a protection layer (p={j['defeats_protection']:.2f})")
    if j["protection_layer"] > 0.7 and j["consequence"] >= 2.5:
        escalate.append(f"protection-layer target with high consequence ({j['consequence']:.1f}/4)")

    # Consequence raises the bar for the other checks rather than prompting on its own;
    # otherwise every write to a process unit becomes a nuisance confirmation.
    serious = j["consequence"] >= 2.0
    min_intent, max_ambiguity = (0.95, 0.35) if serious else (0.85, 0.5)

    if j["consequence"] >= 3.5:
        confirm.append(f"consequence if wrong {j['consequence']:.1f}/4 always needs a person")
    if j["matches_intent"] < min_intent:
        confirm.append(f"may not match the request (p={j['matches_intent']:.2f})")
    if j["exceeds_scope"] > 0.3:
        confirm.append(f"may exceed the requested scope (p={j['exceeds_scope']:.2f})")
    if j["ambiguous_request"] > max_ambiguity:
        confirm.append(f"request is ambiguous (p={j['ambiguous_request']:.2f})")
    if 0.3 < j["protection_layer"] < 0.7:
        confirm.append(f"unsure whether target is a protection layer (p={j['protection_layer']:.2f})")

    if escalate:
        return ESCALATE, escalate + confirm
    if confirm:
        return CONFIRM, confirm
    return ALLOW, []


READ_TOOLS = {"read_attribute", "browse", "query_history"}


async def judge(client: AsyncTypeSafeClient, case: dict[str, Any]) -> Verdict:
    if case["proposed_action"]["tool"] in READ_TOOLS:
        return Verdict(ALLOW, ["read-only tool"])
    if problems := code_checks(case):
        return Verdict(ESCALATE, problems)

    state = {k: case[k] for k in ("operator_request", "proposed_action", "target", "plant_context")}
    response = await client.system_one(state=state, questions=QUESTIONS)

    judgments = {name: a.noul for name, a in response.nouls.items()}
    judgments["consequence"] = response.scores["consequence"].score
    judgments["consequence_confidence"] = response.scores["consequence"].confidence

    decision, reasons = decide(judgments)
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return Verdict(decision, reasons, judgments, usage)
