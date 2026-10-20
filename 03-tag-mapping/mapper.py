"""Brownfield tag mapping: match an existing galaxy's UDAs to nodes on a PLC's OPC-UA server.

Two Jev stages, because the second stage's options depend on the first's answers:

1. Device: one request, one Choice per galaxy instance over the server's device folders.
2. Signal: one request per matched instance, one Choice per UDA over that folder's nodes.

Code does everything exact: filters candidates by data type before Jev sees them, checks
engineering units, catches two UDAs claiming one node, and writes the binding strings.
Jev only selects from what code offers, so it cannot invent a node.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice

PROVIDER, GROUP = "OPCUA", "PlantPLC"
AUTO, REVIEW, UNMAPPED = "auto", "review", "unmapped"
AUTO_CONFIDENCE = 0.8  # starting point for this sample, not a validated value

COMPATIBLE = {
    "Boolean": {"Boolean"},
    "Float": {"Float", "Double"},
    "Integer": {"Int16", "Int32", "UInt16", "UInt32"},
}


@dataclass
class Mapping:
    instance: str
    uda: str
    node: str | None          # full browse path, e.g. PLC1.RW_PMP_1.SPD_FB
    status: str
    reasons: list[str]
    device_confidence: float | None = None
    point_confidence: float | None = None

    @property
    def binding(self) -> str | None:
        return f"{PROVIDER}:{GROUP}.{self.node}" if self.node else None

    @property
    def device_item(self) -> str | None:
        return f"/{GROUP}/s={self.node}" if self.node else None


def describe_node(name: str, n: dict[str, Any]) -> str:
    parts = [n["description"] or "no description", n["data_type"]]
    if n.get("eu"):
        parts.append(f"units {n['eu']}")
    parts.append(f"current value {n['value']}")
    return f"{name}: " + ", ".join(parts)


async def match_devices(client: AsyncTypeSafeClient, galaxy: dict, browse: dict) -> dict[str, Any]:
    folders = {
        folder: "Signals: " + "; ".join(f"{name} ({n['description']})" if n["description"] else name for name, n in nodes.items())
        for folder, nodes in browse.items()
    }
    folders["none"] = "None of these folders holds this equipment's signals."
    state = {"instances": {name: {k: inst[k] for k in ("template", "area", "description")} | {"attributes": list(inst["udas"])}
                           for name, inst in galaxy.items()}}
    questions = {
        name: Choice(
            instructions=f"Which PLC device folder on the OPC-UA server holds the signals for the galaxy object `instances.{name}`?",
            criteria=folders,
        )
        for name in galaxy
    }
    response = await client.system_one(state=state, questions=questions)
    return response.choices


async def match_signals(client: AsyncTypeSafeClient, name: str, inst: dict, folder: str, nodes: dict) -> dict[str, Any]:
    questions, skipped = {}, {}
    for uda, spec in inst["udas"].items():
        candidates = {n: describe_node(n, node) for n, node in nodes.items() if node["data_type"] in COMPATIBLE[spec["type"]]}
        if not candidates:
            skipped[uda] = f"no {spec['type']} node in {folder}"
            continue
        candidates["none"] = "None of these signals is this attribute."
        questions[uda] = Choice(
            instructions=(
                f"Which signal in PLC folder `folder` measures or reports the same thing as the galaxy attribute "
                f"`instance.udas.{uda}`? Judge by meaning; the engineering units may differ, and scaling is handled separately. "
                "The attribute will be bound as an input, so the signal must be a measurement or status feedback from the "
                "field. A setpoint, alarm limit, command, or mode selector is never the right signal, even if it is the closest name."
            ),
            criteria=candidates,
        )
    answers = {}
    if questions:
        state = {"instance": {"name": name, **inst}, "folder": folder}
        answers = dict((await client.system_one(state=state, questions=questions)).choices)
    return {"answers": answers, "skipped": skipped}


async def map_galaxy(client: AsyncTypeSafeClient, galaxy: dict, browse: dict) -> list[Mapping]:
    devices = await match_devices(client, galaxy, browse)

    # As with signals: a confident "none" means no device; an unsure one carries on with the best
    # candidate folder, and everything found under it goes to review.
    folder_of, device_notes = {}, {}
    for name, a in devices.items():
        if a.choice != "none":
            folder_of[name] = a.choice
        elif a.confidence < AUTO_CONFIDENCE:
            best, p = max(((k, v) for k, v in a.probabilities.items() if k != "none"), key=lambda kv: kv[1])
            folder_of[name] = best
            device_notes[name] = f"Jev leaned 'no device' (confidence {a.confidence:.2f}); best candidate {best} p={p:.2f}"

    signals = await asyncio.gather(*(
        match_signals(client, name, galaxy[name], folder, browse[folder]) for name, folder in folder_of.items()
    ))
    signals = dict(zip(folder_of, signals))
    folder_claims = Counter(folder_of.values())

    mappings = []
    for name, inst in galaxy.items():
        dev = devices[name]
        if name not in folder_of:
            mappings += [Mapping(name, uda, None, UNMAPPED, ["no device folder on this server"], dev.confidence) for uda in inst["udas"]]
            continue
        folder = folder_of[name]
        sig = signals[name]
        for uda, spec in inst["udas"].items():
            if uda in sig["skipped"]:
                mappings.append(Mapping(name, uda, None, UNMAPPED, [sig["skipped"][uda]], dev.confidence))
                continue
            pt = sig["answers"][uda]
            signal, reasons = pt.choice, []
            if signal == "none":
                # A confident "none" means unmapped; an unsure one goes to a person with the best candidate.
                signal, p = max(((k, v) for k, v in pt.probabilities.items() if k != "none"), key=lambda kv: kv[1])
                if pt.confidence >= AUTO_CONFIDENCE:
                    mappings.append(Mapping(name, uda, None, UNMAPPED, ["no matching signal in folder"], dev.confidence, pt.confidence))
                    continue
                reasons.append(f"Jev leaned 'none' (confidence {pt.confidence:.2f}); best candidate {signal} p={p:.2f}")

            node = browse[folder][signal]
            if name in device_notes:
                reasons.append(device_notes[name])
            elif dev.confidence < AUTO_CONFIDENCE:
                reasons.append(f"device match confidence {dev.confidence:.2f}")
            if folder_claims[folder] > 1:
                reasons.append(f"{folder} also matched to another object")
            if pt.choice != "none" and pt.confidence < AUTO_CONFIDENCE:
                reasons.append(f"signal match confidence {pt.confidence:.2f}")
            if spec.get("units") and node.get("eu") != spec["units"]:
                reasons.append(f"units differ: galaxy {spec['units']}, PLC {node.get('eu') or 'none'}; needs scaling")
            mappings.append(Mapping(name, uda, f"{folder}.{signal}", REVIEW if reasons else AUTO, reasons,
                                    dev.confidence, pt.confidence))

    # One node feeding two attributes is almost always a mapping error.
    node_claims = Counter(m.node for m in mappings if m.node)
    for m in mappings:
        if m.node and node_claims[m.node] > 1:
            m.status = REVIEW
            m.reasons.append("node also mapped to another attribute")
    return mappings
