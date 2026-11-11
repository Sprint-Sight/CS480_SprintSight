"""Judge canary: does the grounding judge still catch claims that are known to be wrong?

Takes the hand-written gold citations for one benchmark team (every one of them true by
construction), then:

  * "unmutated": asks the judge about the gold claims as written. It should call them grounded.
  * "mutated": changes one number (or a commit SHA) in each claim, so each is now false, and asks
    again. It should NOT call them grounded.

A judge that rubber-stamps everything scores 100% on the first and 0% on the second; one that
rejects everything is the reverse. Run it after changing the judge prompt, the judge model, or
the context size; it exits non-zero when either accuracy drops below the threshold.

    python -m evaluation.offline.judge_canary [judge-model] [--repeats 3] [--min-accuracy 0.8]
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
import sys

from evaluation.benchmarks.cs203 import CS203G6_BUNDLE, CS203G6_GOLD
from evaluation.judges.citation_grounding import collect_citations, run_grounding_judge
from evaluation.judges.config import configured_judge_model

_SHA = re.compile(r"[0-9a-f]{40}")


def mutate(text: str, rng: random.Random | None = None) -> str:
    """Make a claim false: bump its first number, else replace a full commit SHA."""
    rng = rng or random.Random()
    if re.search(r"\d+", text):   # change a number, e.g. +105 -> +950
        return re.sub(r"\d+", lambda m: str(int(m.group()) + 845), text, count=1)
    return _SHA.sub("".join(rng.choices("0123456789abcdef", k=40)), text, count=1)  # fabricate a SHA


def build_canary_claims(rubric_scores, rng: random.Random | None = None) -> tuple[dict, dict]:
    """(true claims, false claims). A claim with no number and no SHA cannot be falsified, so it
    is left out of the false set instead of being passed through unchanged, where a correct
    'grounded' verdict would be scored as a miss."""
    true_claims = collect_citations(rubric_scores)
    if not true_claims:
        raise ValueError("The gold assessment has no citations to build a canary from.")
    false_claims = {}
    for cid, claim in true_claims.items():
        mutated = mutate(claim["text"], rng)
        if mutated != claim["text"]:
            false_claims[cid] = {**claim, "text": mutated}
    return true_claims, false_claims


async def run(judge_model: str, repeats: int = 3) -> dict[str, list[float]]:
    true_claims, false_claims = build_canary_claims(CS203G6_GOLD.rubric_scores)
    accuracies: dict[str, list[float]] = {}
    for name, claims, want_grounded in (("unmutated", true_claims, True), ("mutated", false_claims, False)):
        accuracies[name] = []
        for _ in range(repeats):
            verdict = await run_grounding_judge(CS203G6_BUNDLE, claims, judge_model)
            correct = [(v.label == "grounded") == want_grounded for v in verdict.citation_verdicts]
            accuracies[name].append(sum(correct) / len(correct))
        print(f"{name} ({len(claims)} claims): accuracy per repeat {accuracies[name]}")
    return accuracies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("judge_model", nargs="?", default=configured_judge_model())
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    args = parser.parse_args(argv)

    accuracies = asyncio.run(run(args.judge_model, args.repeats))
    failing = {name: sum(values) / len(values) for name, values in accuracies.items()
               if sum(values) / len(values) < args.min_accuracy}
    if failing:
        print(f"CANARY FAILED (min accuracy {args.min_accuracy}): {failing}")
        return 1
    print("canary ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
