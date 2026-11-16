"""Judge canary: does the grounding judge still catch claims that are known to be wrong?

Takes the hand-written gold citations for two benchmark teams (CS203G6 and CS203JY; every one
of them true by construction), then:

  * "unmutated": asks the judge about the gold claims as written. It should call them grounded.
  * "mutated": falsifies the REASON half of each "identifier | reason" claim and asks again. It
    should NOT call them grounded. Two kinds of falsehood, both about a real commit or file:
    a number in the reason is changed (+105 lines -> +950, 1,184 -> 2,029), or an author handle
    is swapped for another author of the same bundle ("by student3" -> "by student1").

The identifier is never touched. The engine drops citations whose identifier is not in the
evidence before the judge sees them (see GROUNDING_SYSTEM_PROMPT), so a fabricated SHA tests a
case the judge never faces in production; a real SHA with a wrong story is the case it does.

A judge that rubber-stamps everything scores 100% on the first and 0% on the second; one that
rejects everything is the reverse. Run it after changing the judge prompt, the judge model, or
the context size; it exits non-zero when either accuracy drops below the threshold. Output only
appears when a phase finishes, so run it with `python -u`, in the background, with a log file.

    python -u -m evaluation.offline.judge_canary [judge-model] [--repeats 3] [--min-accuracy 0.8]
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
import sys
from collections.abc import Sequence

from evaluation.benchmarks.cs203 import (
    CS203G6_BUNDLE,
    CS203G6_GOLD,
    CS203JY_BUNDLE,
    CS203JY_GOLD,
)
from evaluation.judges.citation_grounding import collect_citations, run_grounding_judge
from evaluation.judges.config import configured_judge_model
from schemas.artifact_bundle import ArtifactBundle

# (name, bundle, gold) for every benchmark team the canary asks about.
CANARY_TEAMS = (
    ("cs203g6", CS203G6_BUNDLE, CS203G6_GOLD),
    ("cs203jy", CS203JY_BUNDLE, CS203JY_GOLD),
)

_SEPARATOR = " | "
_BUMP = 845
# A number that stands alone: not part of a word or handle (student2, Junhao186), a PR/issue
# reference (#16), a ticket key or SHA fragment (CG-46, CS203-10, 37f65c3). 1,184 matches whole.
_NUMBER = re.compile(r"(?<![\w#.])(?<!\w-)\d{1,3}(?:,\d{3})+(?![\w,]|\.\d)|(?<![\w#.])(?<!\w-)\d+(?![\w]|\.\d)")
_QUOTED = re.compile(r"'[^']*'")


def _bump(match: re.Match[str]) -> str:
    raw = match.group()
    value = int(raw.replace(",", "")) + _BUMP
    return f"{value:,}" if "," in raw else str(value)


def _mutate_number(reason: str) -> str | None:
    """Bump one standalone number, preferring those outside quoted commit messages."""
    quoted = [m.span() for m in _QUOTED.finditer(reason)]
    numbers = list(_NUMBER.finditer(reason))
    outside = [m for m in numbers if not any(a <= m.start() < b for a, b in quoted)]
    pool = outside or numbers
    if not pool:
        return None
    chosen = pool[0]
    return reason[:chosen.start()] + _bump(chosen) + reason[chosen.end():]


def _mutate_author(reason: str, authors: Sequence[str]) -> str | None:
    """Swap the first author named in the reason for a different author of the same bundle."""
    for author in sorted(authors, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w-]){re.escape(author)}(?![\w-])", re.IGNORECASE)
        found = pattern.search(reason)
        if not found:
            continue
        others = [a for a in authors if a.lower() != author.lower()]
        if others:
            return reason[:found.start()] + others[0] + reason[found.end():]
    return None


def bundle_authors(bundle: ArtifactBundle) -> list[str]:
    """Distinct commit authors of the bundle, in order of first appearance."""
    return list(dict.fromkeys(c.author for c in bundle.commits if c.author))


def mutate(text: str, rng: random.Random | None = None, authors: Sequence[str] = ()) -> str:
    """Make "<identifier> | <reason>" false by changing only the reason; the identifier stays.

    Picks at random (via `rng`) between the kinds of change that apply: a standalone number
    bumped, or an author swapped for another of `authors`. Text with no separator, or a reason
    with neither, is returned unchanged: it cannot be falsified without touching the identifier.
    """
    identifier, sep, reason = text.partition(_SEPARATOR)
    if not sep:
        return text
    rng = rng or random.Random()
    options = [m for m in (_mutate_number(reason), _mutate_author(reason, authors)) if m is not None]
    if not options:
        return text
    return f"{identifier}{sep}{rng.choice(options)}"


def build_canary_claims(
    rubric_scores, rng: random.Random | None = None, *, authors: Sequence[str] = ()
) -> tuple[dict, dict]:
    """(true claims, false claims). A claim whose reason has nothing to falsify is left out of the
    false set instead of being passed through unchanged, where a correct 'grounded' verdict would
    be scored as a miss."""
    true_claims = collect_citations(rubric_scores)
    if not true_claims:
        raise ValueError("The gold assessment has no citations to build a canary from.")
    false_claims = {}
    for cid, claim in true_claims.items():
        mutated = mutate(claim["text"], rng, authors)
        if mutated != claim["text"]:
            false_claims[cid] = {**claim, "text": mutated}
    return true_claims, false_claims


async def run(judge_model: str, repeats: int = 3) -> dict[str, list[float]]:
    """Accuracy per (team, repeat), pooled under "unmutated" and "mutated"."""
    accuracies: dict[str, list[float]] = {"unmutated": [], "mutated": []}
    for team, bundle, gold in CANARY_TEAMS:
        true_claims, false_claims = build_canary_claims(gold.rubric_scores, authors=bundle_authors(bundle))
        for name, claims, want_grounded in (("unmutated", true_claims, True), ("mutated", false_claims, False)):
            per_repeat = []
            for _ in range(repeats):
                verdict = await run_grounding_judge(bundle, claims, judge_model)
                correct = [(v.label == "grounded") == want_grounded for v in verdict.citation_verdicts]
                per_repeat.append(sum(correct) / len(correct) if correct else 0.0)
            accuracies[name].extend(per_repeat)
            print(f"{team} {name} ({len(claims)} claims): accuracy per repeat {per_repeat}", flush=True)
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
