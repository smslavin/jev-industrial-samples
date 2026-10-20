"""Alarm flood triage: Jev judges every alarm in a flood so the agent gets a briefing, not a dump.

Code handles the exact parts: chattering is already collapsed to one entry with a repeat count,
time order is kept, and a priority 1 alarm is never suppressed. Jev answers two questions per
alarm in a single request: what role it plays in the flood, and how urgently it needs action on
its own merits. Code turns those into a briefing for the agent.

Urgency is asked separately from role on purpose: an alarm unrelated to the upset can still be
the most urgent thing on the screen.
"""

from dataclasses import dataclass
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Score

INITIATING, CONSEQUENCE, INDEPENDENT, NUISANCE = "initiating", "consequence", "independent", "nuisance"

ROLE_CRITERIA = {
    INITIATING: "The first abnormal event that set off this upset; other alarms in the flood follow from it.",
    CONSEQUENCE: "Caused by the upset: a process or equipment response downstream of, or because of, the initiating event.",
    INDEPENDENT: "Not caused by this upset: a standing alarm from before it, or a separate problem that happens to arrive during it.",
    NUISANCE: "Carries no useful information: chattering, an instrument flickering around its limit, or an alarm that duplicates another without adding anything.",
}

URGENCY_CRITERIA = [
    "No action needed: log it or deal with it in routine maintenance.",
    "Monitor: worth watching; act this shift if it persists.",
    "Respond within minutes: needs an operator check or action soon to stop the situation getting worse.",
    "Respond now: risk to people, the public water supply, or major equipment unless an operator acts immediately.",
]

# Starting points for this sample, not validated values.
SUPPRESS_CONFIDENCE = 0.8
SUPPRESS_MAX_URGENCY = 1.5
ACT_NOW_URGENCY = 2.5
CHATTER_REPEATS = 3


@dataclass
class Triaged:
    index: int
    alarm: dict[str, Any]
    role: str
    role_confidence: float
    initiating_p: float
    urgency: float
    suppressed: bool


def questions_for(alarms: list[dict]) -> dict:
    q = {}
    for i in range(len(alarms)):
        q[f"role_{i}"] = Choice(
            instructions=f"In the alarm flood `alarms`, what role does `alarms[{i}]` play? Use `process` for how the plant is connected.",
            criteria=ROLE_CRITERIA,
        )
        q[f"urgency_{i}"] = Score(
            instructions=f"On its own merits, regardless of the other alarms, how urgently does `alarms[{i}]` need operator action?",
            criteria=URGENCY_CRITERIA,
        )
    return q


async def triage(client: AsyncTypeSafeClient, process: str, alarms: list[dict]) -> tuple[list[Triaged], dict]:
    visible = [{k: v for k, v in a.items() if k != "label"} for a in alarms]  # answer key stays in code
    response = await client.system_one(state={"process": process, "alarms": visible}, questions=questions_for(alarms))

    out = []
    for i, alarm in enumerate(visible):
        role = response.choices[f"role_{i}"]
        urgency = response.scores[f"urgency_{i}"].score
        suppressed = (
            alarm["priority"] > 1
            and role.choice in (NUISANCE, INDEPENDENT)
            and role.confidence >= SUPPRESS_CONFIDENCE
            and urgency < SUPPRESS_MAX_URGENCY
        )
        out.append(Triaged(i, alarm, role.choice, role.confidence, role.probabilities[INITIATING], urgency, suppressed))
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return out, usage


def is_act_now(t: Triaged) -> bool:
    # The plant's own priority 1 is engineered knowledge; it outranks any judgment.
    return not t.suppressed and (t.alarm["priority"] == 1 or t.urgency >= ACT_NOW_URGENCY)


def is_chattering(t: Triaged) -> bool:
    return t.alarm.get("repeat", 1) >= CHATTER_REPEATS


def line(t: Triaged) -> str:
    a = t.alarm
    rep = f" (x{a['repeat']})" if a.get("repeat") else ""
    return f"{a['time']} {a['tag']} {a['condition']}{rep}: {a['description']} [P{a['priority']}, {a['state']}]"


def briefing(triaged: list[Triaged]) -> str:
    """What the agent receives instead of the raw flood."""
    kept = [t for t in triaged if not t.suppressed]
    initiating = sorted(kept, key=lambda t: -t.initiating_p)[:2]
    act_now = sorted((t for t in kept if is_act_now(t)), key=lambda t: (t.alarm["priority"] != 1, -t.urgency))
    shown = {t.index for t in initiating} | {t.index for t in act_now}
    chattering = [t for t in kept if t.index not in shown and is_chattering(t)]
    shown |= {t.index for t in chattering}
    rest = sorted((t for t in kept if t.index not in shown), key=lambda t: -t.urgency)
    suppressed = [t for t in triaged if t.suppressed]

    parts = ["Likely initiating event:"]
    parts += [f"  {line(t)}  (p={t.initiating_p:.2f})" for t in initiating]
    parts.append("Act now:")
    parts += [f"  {line(t)}  (urgency {t.urgency:.1f}/3, {t.role})" for t in act_now] or ["  none"]
    parts.append("Other active alarms, most urgent first:")
    parts += [f"  {line(t)}  ({t.role}, urgency {t.urgency:.1f})" for t in rest] or ["  none"]
    if chattering:
        parts.append("Chattering (for alarm rationalization; check the instrument):")
        parts += [f"  {line(t)}" for t in chattering]
    if suppressed:
        parts.append(f"Suppressed ({len(suppressed)}): " + ", ".join(f"{t.alarm['tag']} {t.alarm['condition']}" for t in suppressed))
    return "\n".join(parts)
