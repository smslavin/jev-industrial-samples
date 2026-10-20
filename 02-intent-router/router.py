"""Intent router: one Jev request decides who handles an operator's request, and fills in
the arguments the simple handlers need.

Routing and argument questions go out together (speculative fan-out). Code consumes the
argument answers only on the branches that use them. Anything uncertain falls back to the
agent, so a routing mistake costs an agent call, never a bad write: writes always go
through the agent and then the write gate from sample 01.
"""

from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul

from plant import CATALOG

READ, LOOKUP, WRITE, AGENT, REFUSE = "read_value", "galaxy_lookup", "write_request", "needs_agent", "out_of_scope"

ROUTE = Choice(
    instructions="Which handler should take `operator_request`, from an operator panel in an industrial plant?",
    criteria={
        READ: "Asks for the current value or status of one plant item: a measurement, setpoint, mode, running state, or alarm state.",
        LOOKUP: "Asks how one item is configured in the automation system: its template, area, description, or engineering units.",
        WRITE: "Asks to change something: set, raise, lower, start, stop, switch mode, acknowledge, reset, inhibit, or deploy.",
        AGENT: "Asks why something happened, to compare or diagnose, about history, trends, batches, or production records, "
               "or anything else that needs a multi-step investigation.",
        REFUSE: "Not about this plant or its automation system.",
    },
)

TARGET = Choice(
    instructions="Which plant item is `operator_request` about?",
    criteria={
        **{tag: f"{tag}: {t['description']} ({t['template']}, area {t['area']})" for tag, t in CATALOG.items()},
        "none": "None of these items is the one the operator is asking about.",
    },
)

ATTRIBUTE = Choice(
    instructions="Which value of the item does `operator_request` ask for?",
    criteria={
        "PV": "The measured process value: level, temperature, flow, pressure, speed, concentration.",
        "SP": "The setpoint or target value.",
        "Mode": "Auto, manual, or cascade mode.",
        "Status": "Whether equipment is running, stopped, or out of service.",
        "Alarm": "The item's alarm state.",
    },
)

LOOKUP_FIELD = Choice(
    instructions="Which configuration detail of the item does `operator_request` ask about?",
    criteria={
        "template": "The template the object is derived from.",
        "area": "The area or plant section the object belongs to.",
        "description": "What the object is or does.",
        "units": "The engineering units.",
    },
)

SINGLE_ITEM = Noul(
    instructions="Does `operator_request` ask about exactly one plant item, rather than several items or none?",
)

QUESTIONS = {"route": ROUTE, "target": TARGET, "attribute": ATTRIBUTE, "lookup_field": LOOKUP_FIELD, "single_item": SINGLE_ITEM}

# Starting points for this sample, not validated values.
MIN_ROUTE_CONFIDENCE = 0.6
MIN_ARG_CONFIDENCE = 0.6


@dataclass
class Routed:
    route: str                 # what Jev chose
    handled_by: str            # who actually answers: code, agent, agent+gate, refused
    reply: str
    target: str | None = None
    attribute: str | None = None
    judgments: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int | None] = field(default_factory=dict)


def to_agent(route: str, why: str, **kw: Any) -> Routed:
    return Routed(route, "agent", f"-> Claude agent ({why})", **kw)


async def route(client: AsyncTypeSafeClient, request: str) -> Routed:
    response = await client.system_one(state={"operator_request": request}, questions=QUESTIONS)
    c = response.choices
    j = {name: (a.choice, round(a.confidence, 2)) for name, a in c.items()}
    j["single_item"] = round(response.nouls["single_item"].noul, 2)
    meta = {"judgments": j, "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}}

    chosen = c["route"].choice
    if c["route"].confidence < MIN_ROUTE_CONFIDENCE:
        return to_agent(chosen, f"route unsure, confidence {c['route'].confidence:.2f}", **meta)
    if chosen == REFUSE:
        return Routed(chosen, "refused", "That's outside what this panel can help with.", **meta)
    if chosen == WRITE:
        return Routed(chosen, "agent+gate", "-> Claude agent proposes the write; write gate (sample 01) decides", **meta)
    if chosen == AGENT:
        return to_agent(chosen, "needs reasoning", **meta)

    # read_value and galaxy_lookup: answer in code if the arguments are solid.
    tag = c["target"].choice
    if response.nouls["single_item"].noul < 0.5:
        return to_agent(chosen, "more than one item", **meta)
    if tag == "none" or c["target"].confidence < MIN_ARG_CONFIDENCE:
        return to_agent(chosen, f"item unclear ({tag}, confidence {c['target'].confidence:.2f})", **meta)
    item = CATALOG[tag]

    if chosen == READ:
        attr = c["attribute"].choice
        if c["attribute"].confidence < MIN_ARG_CONFIDENCE or attr not in item["values"]:
            return to_agent(chosen, f"attribute unclear ({attr})", target=tag, **meta)
        units = f" {item['units']}" if attr in ("PV", "SP") and item["units"] else ""
        return Routed(chosen, "code", f"{tag}.{attr} = {item['values'][attr]}{units}", target=tag, attribute=attr, **meta)

    fld = c["lookup_field"].choice
    if c["lookup_field"].confidence < MIN_ARG_CONFIDENCE:
        return to_agent(chosen, f"lookup field unclear ({fld})", target=tag, **meta)
    return Routed(chosen, "code", f"{tag} {fld}: {item[fld] or '(none)'}", target=tag, attribute=fld, **meta)
