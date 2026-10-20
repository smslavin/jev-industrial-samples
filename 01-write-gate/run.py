"""Run the write gate over recorded agent tool calls and compare with expected outcomes.

    python run.py              # all cases
    python run.py lower-trip   # one case, with every judgment printed

Each verdict is appended to decisions.jsonl: a trace of what the gate saw and why
it decided, the record an MOC reviewer would want.
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient

from gate import judge

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    """Minimal .env reader so the samples need nothing beyond the SDK."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


async def main(only: str | None) -> None:
    cases = json.loads((HERE / "cases.json").read_text())
    if only:
        cases = [c for c in cases if c["id"] == only]

    async with AsyncTypeSafeClient() as client:
        start = time.perf_counter()
        verdicts = await asyncio.gather(*(judge(client, c) for c in cases))
        elapsed = time.perf_counter() - start

    hits = 0
    with (HERE / "decisions.jsonl").open("a") as log:
        for case, v in zip(cases, verdicts):
            ok = v.decision == case["expected"]
            hits += ok
            mark = "ok  " if ok else "MISS"
            print(f"{mark} {case['id']:<26} {v.decision:<9} (expected {case['expected']})")
            for reason in v.reasons:
                print(f"       - {reason}")
            if only:
                for name, value in v.judgments.items():
                    print(f"       {name:<24} {value:.3f}")
            log.write(json.dumps({"ts": time.time(), "case": case["id"], **asdict(v)}) + "\n")

    tokens = sum((v.usage.get("input_tokens") or 0) for v in verdicts)
    print(f"\n{hits}/{len(cases)} match expected | {elapsed:.2f}s wall | {tokens} input tokens")


if __name__ == "__main__":
    load_env(HERE.parent / ".env")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
