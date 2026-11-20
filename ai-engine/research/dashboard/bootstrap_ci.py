"""Paired cluster bootstrap over results_tidy.csv (read-only; prints Markdown).
Unit of resampling = (bundle, dimension) cell; the 3 repeats of a cell are averaged first so that
repeats (not independent) never inflate n. A failed (null) dimension-run is dropped; a cell is kept
for a model only if it has >=1 valid repeat. Pairwise comparisons use cells valid for BOTH models.
Run: python research/dashboard/bootstrap_ci.py [--ablate-requirements]"""
import csv
import itertools
import random
import statistics as st
import sys
from pathlib import Path

B, SEED = 10000, 480
ablate = "--ablate-requirements" in sys.argv
with open(Path(__file__).with_name("results_tidy.csv"), newline="") as f:
    rows = list(csv.DictReader(f))
MODELS = ["qwen25-32b", "qwen", "gemma", "r1-32b", "coder-32b"]

def cells(script, model):
    d = {}
    for r in rows:
        if r["script"] != script or r["model"] != model or r["failed"] == "True" or r["score"] == "": continue
        if ablate and script == "cs203" and r["dimension"] == "requirements": continue
        d.setdefault((r["bundle"], r["dimension"]), []).append((abs(float(r["score"]) - float(r["reference"])), float(r["signed_error"])))
    return {k: (st.mean(a for a, _ in v), st.mean(s for _, s in v)) for k, v in d.items()}

def const_err(script, model):   # |5.5 - gold| on the same cells
    d = {}
    for r in rows:
        if r["script"] == script and r["model"] == model and r["failed"] != "True" and r["score"] != "":
            if ablate and script == "cs203" and r["dimension"] == "requirements": continue
            d[(r["bundle"], r["dimension"])] = abs(5.5 - float(r["reference"]))
    return d

def ci(xs, rng):
    n = len(xs); bs = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return bs[int(.025 * B)], bs[int(.975 * B) - 1]

rng = random.Random(SEED)
for script, label in (("cs203", "CS203 real bundles"), ("fixture", "Synthetic fixtures")):
    C = {m: cells(script, m) for m in MODELS}; K = {m: const_err(script, m) for m in MODELS}
    print(f"\n### {label}{' (requirements excluded)' if ablate and script=='cs203' else ''}\n")
    print("| Model | cells | MAE | 95% CI | const-baseline MAE | MAE - baseline [95% CI] |\n|---|---|---|---|---|---|")
    for m in MODELS:
        ks = sorted(C[m]); e = [C[m][k][0] for k in ks]; b = [K[m][k] for k in ks]; dlt = [x - y for x, y in zip(e, b)]
        lo, hi = ci(e, rng); dl, dh = ci(dlt, rng)
        print(f"| {m} | {len(ks)} | {st.mean(e):.2f} | [{lo:.2f}, {hi:.2f}] | {st.mean(b):.2f} | {st.mean(dlt):+.2f} [{dl:+.2f}, {dh:+.2f}] |")
    print("\n| A vs B | shared cells | MAE_A - MAE_B | 95% CI | excludes 0? |\n|---|---|---|---|---|")
    for a, b2 in itertools.combinations(MODELS, 2):
        ks = sorted(set(C[a]) & set(C[b2])); d = [C[a][k][0] - C[b2][k][0] for k in ks]
        lo, hi = ci(d, rng)
        print(f"| {a} vs {b2} | {len(ks)} | {st.mean(d):+.2f} | [{lo:+.2f}, {hi:+.2f}] | {'yes' if lo > 0 or hi < 0 else 'no'} |")
