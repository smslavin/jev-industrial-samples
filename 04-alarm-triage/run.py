"""Triage each recorded alarm flood, print the agent briefing, and score against the labels.

    python run.py                          # both scenarios
    python run.py intake-power-dip         # one scenario

The safety number is "urgent suppressed": an alarm labeled urgency 2 or 3 that the triage hid.
It must be zero.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient

from triage import briefing, is_act_now, triage

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    """Minimal .env reader so the samples need nothing beyond the SDK."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def raw_flood(alarms: list[dict]) -> str:
    """The flood as the agent would otherwise see it: one event per occurrence, chattering included."""
    events = [{k: v for k, v in a.items() if k not in ("label", "repeat")} for a in alarms for _ in range(a.get("repeat", 1))]
    return json.dumps(events)


async def main(only: str | None) -> None:
    data = json.loads((HERE / "scenarios.json").read_text())
    scenarios = {k: v for k, v in data["scenarios"].items() if not only or k == only}

    async with AsyncTypeSafeClient() as client:
        start = time.perf_counter()
        results = await asyncio.gather(*(triage(client, data["process"], s["alarms"]) for s in scenarios.values()))
        elapsed = time.perf_counter() - start

    for (name, s), (triaged, usage) in zip(scenarios.items(), results):
        print(f"=== {name}: {s['summary']}\n")
        role_ok = urgent_suppressed = urgent_missed = 0
        for t in triaged:
            label = s["alarms"][t.index]["label"]
            ok = t.role == label["role"]
            role_ok += ok
            if t.suppressed and label["urgency"] >= 2:
                urgent_suppressed += 1
            if label["urgency"] == 3 and not is_act_now(t):
                urgent_missed += 1
            flag = "SUPP" if t.suppressed else "    "
            print(f"{'ok  ' if ok else 'MISS'} {flag} {t.alarm['tag'] + ' ' + t.alarm['condition']:<40} "
                  f"{t.role:<12} conf={t.role_confidence:.2f} urg={t.urgency:.1f} "
                  f"(label {label['role']}, {label['urgency']})")

        brief = briefing(triaged)
        top = max(triaged, key=lambda t: t.initiating_p)
        print(f"\n--- briefing for the agent ---\n{brief}\n")
        print(f"roles {role_ok}/{len(triaged)} | initiating top-1 "
              f"{'ok' if s['alarms'][top.index]['label']['role'] == 'initiating' else 'MISS'} "
              f"| urgent suppressed {urgent_suppressed} | urgency-3 not in act-now {urgent_missed} "
              f"| {len(raw_flood(s['alarms']))} chars raw -> {len(brief)} chars briefing "
              f"| {usage['input_tokens']} Jev input tokens\n")
    print(f"{elapsed:.2f}s wall")


if __name__ == "__main__":
    load_env(HERE.parent / ".env")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
