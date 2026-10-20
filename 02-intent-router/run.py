"""Route recorded operator requests and compare with expected handlers.

    python run.py              # all cases
    python run.py two-items    # one case, with every judgment printed
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient

from router import route

HERE = Path(__file__).parent


def load_env(path: Path) -> None:
    """Minimal .env reader so the samples need nothing beyond the SDK."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def matches(case: dict, r) -> bool:
    if r.handled_by != case["expected"]:
        return False
    return case["expected"] != "code" or (r.target, r.attribute) == (case["target"], case["attribute"])


async def main(only: str | None) -> None:
    cases = json.loads((HERE / "cases.json").read_text())
    if only:
        cases = [c for c in cases if c["id"] == only]

    async with AsyncTypeSafeClient() as client:
        start = time.perf_counter()
        results = await asyncio.gather(*(route(client, c["request"]) for c in cases))
        elapsed = time.perf_counter() - start

    hits = 0
    for case, r in zip(cases, results):
        ok = matches(case, r)
        hits += ok
        print(f"{'ok  ' if ok else 'MISS'} {case['id']:<18} {r.handled_by:<10} {r.reply}")
        if not ok or only:
            want = case["expected"] + (f" {case['target']}.{case['attribute']}" if case["expected"] == "code" else "")
            print(f"       expected {want}; judgments {r.judgments}")

    in_code = sum(r.handled_by == "code" for r in results)
    tokens = sum((r.usage.get("input_tokens") or 0) for r in results)
    print(f"\n{hits}/{len(cases)} match expected | {in_code} answered in code, no agent call "
          f"| {elapsed:.2f}s wall | {tokens} input tokens")


if __name__ == "__main__":
    load_env(HERE.parent / ".env")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
