"""Run the mapper over generated namespaces at each difficulty and report what breaks.

    python sweep.py              # easy/medium/hard x seeds 1-3
    python sweep.py hard 1 2 3 4 5

The number that matters is wrong-auto: a binding made without review that is wrong.
Everything in review or unmapped costs an engineer's time, not a bad binding.
"""

import asyncio
import sys
from collections import Counter

from typesafe_sdk import AsyncTypeSafeClient

from dirtier import LEVELS, generate
from mapper import AUTO, REVIEW, UNMAPPED, map_galaxy
from run import HERE, load_env


async def one(client: AsyncTypeSafeClient, level: str, seed: int) -> tuple[Counter, list[str]]:
    galaxy, browse, expected = generate(level, seed)
    mappings = await map_galaxy(client, galaxy, browse)
    c, wrong_auto = Counter(), []
    for m in mappings:
        key = f"{m.instance}.{m.uda}"
        ok = m.node == expected[key]
        c[m.status] += 1
        c["correct"] += ok
        if m.status == AUTO and not ok:
            wrong_auto.append(f"{key} -> {m.node} (expected {expected[key]})")
        if m.status == REVIEW:
            c["review_right_proposal"] += ok
        if m.status == UNMAPPED and expected[key] is not None:
            c["missed"] += 1
    c["total"] = len(mappings)
    return c, wrong_auto


async def main(levels: list[str], seeds: list[int]) -> None:
    async with AsyncTypeSafeClient() as client:
        runs = [(lv, s) for lv in levels for s in seeds]
        results = await asyncio.gather(*(one(client, lv, s) for lv, s in runs))

    print(f"{'run':<10} {'correct':>8} {'auto':>5} {'wrong-auto':>10} {'review':>7} {'unmapped':>9} {'missed':>7}")
    for (lv, s), (c, wrong) in zip(runs, results):
        print(f"{lv + '-' + str(s):<10} {c['correct']:>3}/{c['total']:<4} {c[AUTO]:>5} {len(wrong):>10} "
              f"{c[REVIEW]:>7} {c[UNMAPPED]:>9} {c['missed']:>7}")
        for w in wrong:
            print(f"           wrong auto: {w}")


if __name__ == "__main__":
    load_env(HERE.parent / ".env")
    args = sys.argv[1:]
    levels = [args.pop(0)] if args and args[0] in LEVELS else list(LEVELS)
    asyncio.run(main(levels, [int(a) for a in args] or [1, 2, 3]))
