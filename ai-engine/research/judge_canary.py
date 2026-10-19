import asyncio
import random
import re
import sys

from schemas.cs203_groundtruth import CS203G6_BUNDLE, CS203G6_GOLD

from judges.citation_ground_custom_judge import collect_citations, run_grounding_judge


def mutate(text: str) -> str:
    if re.search(r"\d+", text):   # change a number, e.g. +105 -> +950
        return re.sub(r"\d+", lambda m: str(int(m.group()) + 845), text, count=1)
    return re.sub(r"[0-9a-f]{40}", "".join(random.choices("0123456789abcdef", k=40)), text, count=1)  # fabricate a SHA

async def run(judge_model: str, repeats: int = 3):
    real = collect_citations(CS203G6_GOLD)
    fake = {k: {**v, "text": mutate(v["text"])} for k, v in real.items()}
    for name, cits, want_ok in (("unmutated", real, True), ("mutated", fake, False)):
        accs = []
        for _ in range(repeats):
            v = await run_grounding_judge(CS203G6_BUNDLE, cits, judge_model)
            ok = [(x.label == "grounded") == want_ok for x in v.citation_verdicts]
            accs.append(sum(ok) / len(ok))
        print(f"{name}: accuracy per repeat {accs}")

if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "sprintsight-judge-phi"))
