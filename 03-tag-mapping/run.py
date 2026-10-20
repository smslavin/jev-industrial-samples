"""Map the sample galaxy onto the sample OPC-UA browse and score against expected.json.

    python run.py                    # the hand-written sample in this folder
    python run.py dirty/medium-7     # a generated namespace from dirtier.py

Writes binding_plan.json next to the input files: GRAccess input-source strings for the auto rows, the review
queue, and the OI Gateway Device Items the bound nodes need.
"""

import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient

from mapper import AUTO, REVIEW, UNMAPPED, map_galaxy

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    """Minimal .env reader so the samples need nothing beyond the SDK."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


async def main(data: Path) -> None:
    galaxy = json.loads((data / "galaxy.json").read_text())
    browse = json.loads((data / "opcua_browse.json").read_text())
    expected = json.loads((data / "expected.json").read_text())

    async with AsyncTypeSafeClient() as client:
        start = time.perf_counter()
        mappings = await map_galaxy(client, galaxy, browse)
        elapsed = time.perf_counter() - start

    correct = Counter()
    for m in mappings:
        key = f"{m.instance}.{m.uda}"
        ok = m.node == expected[key]
        correct[(m.status, ok)] += 1
        conf = " ".join(f"{label}={v:.2f}" for label, v in (("dev", m.device_confidence), ("sig", m.point_confidence)) if v is not None)
        print(f"{'ok  ' if ok else 'MISS'} {m.status:<9} {key:<32} -> {m.node or '-':<26} {conf}")
        for r in m.reasons:
            print(f"       - {r}")
        if not ok:
            print(f"       expected {expected[key]}")

    plan = {
        "bindings": {f"{m.instance}.{m.uda}": m.binding for m in mappings if m.status == AUTO},
        "review": [{"attribute": f"{m.instance}.{m.uda}", "proposed": m.binding, "reasons": m.reasons}
                   for m in mappings if m.status == REVIEW],
        "unmapped": [f"{m.instance}.{m.uda}" for m in mappings if m.status == UNMAPPED],
        "device_items": sorted({m.device_item for m in mappings if m.status in (AUTO, REVIEW)}),
    }
    (data / "binding_plan.json").write_text(json.dumps(plan, indent=2))

    n = len(mappings)
    total_ok = sum(v for (_, ok), v in correct.items() if ok)
    auto_n = correct[(AUTO, True)] + correct[(AUTO, False)]
    print(f"\n{total_ok}/{n} match expected | auto {auto_n} ({correct[(AUTO, True)]} correct) "
          f"| review {correct[(REVIEW, True)] + correct[(REVIEW, False)]} "
          f"| unmapped {correct[(UNMAPPED, True)] + correct[(UNMAPPED, False)]} | {elapsed:.2f}s wall")


if __name__ == "__main__":
    load_env(HERE.parent / ".env")
    asyncio.run(main(HERE / sys.argv[1] if len(sys.argv) > 1 else HERE))
