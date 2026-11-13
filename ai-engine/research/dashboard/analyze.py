"""Read-only analysis of the local-LLM grading trials in ai-engine/results.

Reads every raw_results / summary / raw_judge_results file in ai-engine/results (or a subset, see the
flags below), ai-engine/audit_logs and the reference scores. Writes only into this folder:
analysis.json, results_tidy.csv, run_health.md.
Run from anywhere:  python3 research/dashboard/analyze.py
Optional filters:   --since 2026-11-11        only sessions on or after this date
                    --experiment fixtures_test_4   only files whose name contains this text
Note: the scorecard pools sessions of the same model and script, so use a filter when the folder mixes
experiments with different prompts or judges.
"""
import argparse
import collections
import csv
import datetime as dt
import importlib.util
import json
import math
import re
import statistics as st
from pathlib import Path
from typing import Any

ap = argparse.ArgumentParser()
ap.add_argument("--since", help="only sessions on or after this date, YYYY-MM-DD")
ap.add_argument("--experiment", help="only files whose name contains this text, e.g. fixtures_test_4")
args = ap.parse_args()

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                       # ai-engine/
RES, AUD = ROOT / "results", ROOT / "audit_logs"
DIMS = ["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]
COMMIT_DIMS = ["code_quality", "testing", "documentation", "cicd"]
DATA_DIMS = ["requirements", "collaboration"]
BASELINE = 5.5

# expected orders: load the module straight from its file (it only imports typing)
BENCH = ROOT / "evaluation" / "benchmarks"     # moved here by the ai-engine layout refactor
spec = importlib.util.spec_from_file_location("expected_orders", BENCH / "expected_orders.py")
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load expected-order definitions from {BENCH / 'expected_orders.py'}")
eo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eo)
ARCHETYPE = {"Team_Alpha": "high_performing", "Team_Delta": "good_collab_low_output", "Team_Epsilon": "imbalanced_high_output",
             "Team_Theta": "lone_contributor_poor_outcome", "Team_Gamma": "struggling"}   # evaluation/benchmarks/synthetic_v2.py
BUNDLE_LABEL = {"cs203g6": "CS203 G6", "fa7d4476-78fd-4013-8d66-1e290a65fe1c": "CS203 JY", **{k: k.removeprefix("Team_") for k in ARCHETYPE}}

# ---------------- reference scores ----------------
def load_gold():
    gold = {}
    for f in (BENCH / "data" / "gold").glob("*_GOLD.json"):
        d = json.loads(f.read_text())
        gold[d["team_id"]] = {k: v["score"] for k, v in d["rubric_scores"].items()}
    src = (BENCH / "cs203.py").read_text()
    g6 = src.split("CS203G6_GOLD")[1].split("CS203JY_BUNDLE")[0]
    gold["cs203g6"] = {d: int(s) for d, s in re.findall(r'dimension="(\w+)", score=(\d+)', g6)}
    return gold
GOLD = load_gold()

# ---------------- batch files ----------------
now = dt.datetime.now(dt.UTC)
def session_of(p):
    match = re.search(r"_(\d{8}T\d{6})\.json", p.name)
    if match is None:
        raise ValueError(f"Could not find a session timestamp in {p.name!r}")
    return match.group(1)

def matches_filter(p):
    if args.experiment and args.experiment not in p.name: return False
    return not (args.since and session_of(p)[:8] < args.since.replace("-", ""))

all_files = sorted(p for p in RES.iterdir() if p.name.startswith(("raw_", "summary_")))
batch_files = [p for p in all_files if matches_filter(p)]
older_files = [p.name for p in all_files if not matches_filter(p)]   # files excluded by --since / --experiment

invocations: dict[str, dict[str, Any]] = {}
for p in batch_files:
    s = session_of(p)
    inv = invocations.setdefault(s, {"session": s, "files": {}})
    kind = "judge" if p.name.startswith("raw_judge_results_") else "raw" if p.name.startswith("raw_results_") else "summary"
    inv["files"][kind] = p
    inv["script"] = "cs203" if "_CS203_" in p.name else "fixture"
    # the judge is chosen from the experiment name: OpenAI-judged fixture sessions say "openai" in the file name
    inv["judge_actual"] = "gpt-4o-mini (OpenAI)" if "openai" in p.name else "sprintsight-judge-phi (Ollama)"

# judge-only sessions (no raw_results file, so no model or runs to analyse) are skipped
judge_only = [s for s, i in invocations.items() if "raw" not in i["files"]]
for s in judge_only: del invocations[s]
batch_files = [p for p in batch_files if session_of(p) not in judge_only]

def parse_ts(s): return dt.datetime.fromisoformat(s)

# ---------------- runs ----------------
runs = []
for s, inv in sorted(invocations.items()):
    raw = inv["files"].get("raw")
    lines = raw.read_text().splitlines() if raw else []
    inv["raw_lines"], inv["bad_json"] = len(lines), 0
    rep: collections.Counter[str] = collections.Counter()
    for i, line in enumerate(lines, 1):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            inv["bad_json"] += 1; continue
        rep[r["team_id"]] += 1
        end = parse_ts(r["timestamp"])
        runs.append({"session": s, "script": inv["script"], "line": i, "model": r["model"].removeprefix("sprintsight-"),
                     "bundle": r["team_id"], "bundle_label": BUNDLE_LABEL.get(r["team_id"], r["team_id"]),
                     "archetype": ARCHETYPE.get(r["team_id"], ""), "repeat": rep[r["team_id"]], "trace_id": r["trace_id"],
                     "overall": r["overall_score"], "scores": r["dimension_scores"], "failed": r["failed_dimensions"],
                     "duration": r["duration_seconds"], "end": end, "start": end - dt.timedelta(seconds=r["duration_seconds"]),
                     "prompt_versions": r["prompt_versions"]})
    inv["model"] = runs[-1]["model"] if runs and runs[-1]["session"] == s else None

# ---------------- audit logs (calls inside the batch window) ----------------
SECTION = re.compile(r"\n([A-Z][A-Z /]+)\n-+\n(.*?)(?=\n[A-Z][A-Z /]+\n-+\n|\Z)", re.DOTALL)
if not runs: raise SystemExit("No runs found for these filters.")
t0 = min(r["start"] for r in runs) - dt.timedelta(minutes=5)
t1 = max(r["end"] for r in runs) + dt.timedelta(minutes=30)
audit = []
for p in AUD.iterdir():
    m = re.match(r"llm_(\d{8}T\d{6})", p.name)
    if not m:
        continue
    ts = dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=dt.UTC)
    if not (t0 - dt.timedelta(hours=1) <= ts <= t1 + dt.timedelta(hours=1)):
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    sec = dict(SECTION.findall(text))
    try:
        meta_match = re.search(r"METADATA\n-+\n(\{.*?\n\})\n", text, re.DOTALL)
        if meta_match is None:
            raise ValueError(f"Missing metadata section in {p.name}")
        meta = json.loads(meta_match.group(1))
    except Exception:  # noqa: BLE001
        meta = {}
    rec: dict[str, Any] = {"file": p.name, "ts": parse_ts(meta["logged_at"]) if meta.get("logged_at") else ts, "model": (meta.get("model") or "").removeprefix("sprintsight-"),
           "team": meta.get("team_id"), "dim": meta.get("dimension"), "error": sec.get("CLIENT ERROR", "").strip(),
           "est": meta.get("estimated_prompt_tokens"), "num_ctx": meta.get("num_ctx"), "jira": meta.get("jira_ticket_count"),
           "peer": meta.get("peer_evaluation_count"), "path": p}
    raw_out = sec.get("RAW OUTPUT FROM OLLAMA", "").strip()
    rec["think"] = "<think>" in raw_out
    try:
        body = json.loads(raw_out)
        rec["prompt_tokens"] = (body.get("usage") or {}).get("prompt_tokens")
        rec["completion_tokens"] = (body.get("usage") or {}).get("completion_tokens")
        rec["finish"] = body["choices"][0].get("finish_reason")
        rec["content"] = body["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        rec["prompt_tokens"] = rec["completion_tokens"] = rec["finish"] = rec["content"] = None
    audit.append(rec)

def prompt_text(rec):
    try:
        body = json.loads(dict(SECTION.findall(rec["path"].read_text(encoding="utf-8", errors="replace")))["INPUT SENT TO OLLAMA"])
        return "\n".join(m["content"] for m in body["messages"] if m["role"] == "user")
    except Exception:  # noqa: BLE001
        return ""

def cite_found(ident, prompt):
    s = (ident or "").strip()
    if not s:
        return False
    if s in prompt:
        return True
    base, _, sha = s.partition("@")
    base = base.split(":")[0].strip()
    return bool(base) and base in prompt and (not sha or sha.strip() in prompt)

# contributor-summary lines the prompt shows, e.g. "Student3: 20 commits, +170/-201 lines, 1 active day(s)"
AUTHOR_LINE = re.compile(r"\d+ commits?, \+\d+/-\d+ lines")

# link every run+dimension to its audit calls
by_key = collections.defaultdict(list)
for a in audit:
    by_key[(a["model"], a["team"], a["dim"])].append(a)
score_mismatch = []
for r in runs:
    r["dims"] = {}
    for d in DIMS:
        calls = sorted((a for a in by_key[(r["model"], r["bundle"], d)] if r["start"] - dt.timedelta(seconds=3) <= a["ts"] <= r["end"]), key=lambda a: a["ts"])
        ok = None
        for a in reversed(calls):
            if not a["error"] and a["content"]:
                try:
                    ok = (a, json.loads(a["content"])); break
                except json.JSONDecodeError:
                    continue
        info: dict[str, Any] = {"attempts": len(calls), "errors": sum(1 for a in calls if a["error"]), "citations": None, "found": None, "audit_score": None}
        if ok and d not in r["failed"]:      # a failed dimension's last output parsed but did not validate
            a, out = ok
            cits = out.get("evidence_citations") or []
            prompt = prompt_text(a)
            info.update(citations=len(cits), found=sum(cite_found(c.get("identifier"), prompt) for c in cits),
                        author_summary=sum(1 for c in cits if AUTHOR_LINE.search(str(c.get("identifier", "")))),
                        identifiers=[str(c.get("identifier", "")) for c in cits],
                        audit_score=out.get("score"), completion_tokens=a["completion_tokens"], file=a["file"])
            if r["scores"][d] is not None and out.get("score") != r["scores"][d]:
                score_mismatch.append((r["session"], r["line"], d, out.get("score"), r["scores"][d]))
        r["dims"][d] = info

# ---------------- failure classification ----------------
def classify(msg):
    m = msg.lower()
    if "connection" in m: return "connection / model unavailable"
    if "max_tokens" in m: return "output truncated (max_tokens)"
    if "string_too_long" in m: return "schema: justification over 500 chars"
    if "validation error" in m: return "schema validation"
    if "timed out" in m or "timeout" in m: return "timeout"
    return "other"

durations_by_model: dict[tuple[str, str], list[float]] = {}
for r in runs:
    durations_by_model.setdefault((r["model"], r["script"]), []).append(r["duration"])
med = {k: st.median(v) for k, v in durations_by_model.items()}
for r in runs:
    r["spiral"] = r["duration"] > 3 * med[(r["model"], r["script"])]
    r["instant"] = r["duration"] < 2
    r["failure_class"] = {d: classify(m) for d, m in r["failed"].items()}

# ---------------- judge rows ----------------
judge = {}
for inv in invocations.values():
    p = inv["files"].get("judge")
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p else []
    inv["judge_rows"] = len(rows)
    for j in rows:
        judge[j["trace_id"]] = j
for r in runs:
    j = judge.get(r["trace_id"])
    r["judge"] = j["scores"] if j else None
    r["judge_label"] = j["judge_model"] if j else None
    r["judge_actual"] = invocations[r["session"]]["judge_actual"] if j else None

# ---------------- helpers ----------------
def pct(n, d): return round(n / d, 4) if d else None
def p95(xs):
    xs = sorted(xs); return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]
def mean(xs):
    xs = [x for x in xs if x is not None]; return round(st.mean(xs), 4) if xs else None
def sd(xs):
    xs = [x for x in xs if x is not None]; return round(st.stdev(xs), 4) if len(xs) >= 2 else None
def pearson(a, b):
    if len(a) < 5: return None
    ma, mb = st.mean(a), st.mean(b)
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=False)) / math.sqrt(va * vb), 3) if va and vb else None

models = list(dict.fromkeys(r["model"] for r in sorted(runs, key=lambda r: r["session"])))
MODEL_ORDER = [m for m in ["qwen25-32b", "qwen", "gemma", "r1-32b", "coder-32b"] if m in models] + [m for m in models if m not in ["qwen25-32b", "qwen", "gemma", "r1-32b", "coder-32b"]]

# ---------------- STEP 1: health ----------------
EXPECTED_BUNDLES = {"cs203": 2, "fixture": 5}
health = []
for s, inv in sorted(invocations.items(), key=lambda kv: (kv[1]["script"], MODEL_ORDER.index(kv[1]["model"]))):
    rs = [r for r in runs if r["session"] == s]
    summ = json.loads(inv["files"]["summary"].read_text()) if "summary" in inv["files"] else None
    mism = []
    if summ:
        for team, v in summ["teams"].items():
            tr = [r for r in rs if r["bundle"] == team]
            if v["runs"] != len(tr): mism.append(f"{team} runs {v['runs']}≠{len(tr)}")
            if abs(st.mean(r["overall"] for r in tr) - v["mean_overall_score"]) > 1e-3: mism.append(f"{team} overall")
            for d in DIMS:
                vals = [r["scores"][d] for r in tr if r["scores"][d] is not None]
                m = round(st.mean(vals), 3) if vals else None
                if m != v["mean_dimension_scores"][d]: mism.append(f"{team} {d} {m}≠{v['mean_dimension_scores'][d]}")
    overall_bad = [r["line"] for r in rs if [r["scores"][d] for d in DIMS if r["scores"][d] is not None] and
                   abs(r["overall"] - st.mean(r["scores"][d] for d in DIMS if r["scores"][d] is not None)) > 1e-6]
    reps = collections.Counter(r["bundle"] for r in rs)
    expected_runs = EXPECTED_BUNDLES[inv["script"]] * max(reps.values(), default=0)   # repeats are read from the file, not assumed to be 3
    fails = collections.Counter(c for r in rs for c in r["failure_class"].values())
    scored = sum(1 for r in rs for d in DIMS if r["scores"][d] is not None)
    complete = sum(1 for r in rs if not r["failed"])
    files_present = sorted(inv["files"])
    reasons = []
    if len(rs) != expected_runs: reasons.append(f"{len(rs)} of {expected_runs} runs")
    if inv["bad_json"]: reasons.append(f"{inv['bad_json']} unreadable lines")
    if mism: reasons.append("summary disagrees with raw")
    if set(files_present) != {"raw", "summary", "judge"}: reasons.append("missing " + ", ".join({"raw", "summary", "judge"} - set(files_present)))
    if fails: reasons.append(f"{sum(fails.values())} failed dimensions: " + "; ".join(f"{v}× {k}" for k, v in fails.items()))
    if inv["judge_rows"] != len(rs): reasons.append(f"judge rows {inv['judge_rows']} vs runs {len(rs)}")
    verdict = "FAILED" if not rs or complete == 0 and scored < len(rs) * 3 else ("OK" if not reasons else "PARTIAL")
    health.append({"session": s, "script": inv["script"], "model": inv["model"], "files_expected": 3, "files": files_present,
                   "file_names": {k: v.name for k, v in inv["files"].items()},
                   "runs_expected": expected_runs, "raw_lines": inv["raw_lines"], "summary_runs": summ["total_runs"] if summ else None,
                   "repeats_per_bundle": dict(reps), "dims_scored": scored, "dims_expected": expected_runs * 6, "complete_runs": complete,
                   "failures": dict(fails), "summary_mismatches": mism, "overall_not_mean": overall_bad, "judge_rows": inv["judge_rows"],
                   "spiral_runs": sum(r["spiral"] for r in rs), "instant_runs": sum(r["instant"] for r in rs),
                   "latency_median": round(st.median(r["duration"] for r in rs), 1) if rs else None,
                   "verdict": verdict, "reason": "; ".join(reasons) or "all runs, dimensions, summary and judge rows as expected",
                   "experiment": summ["experiment"] if summ else None})

# truncation-warning check against llm_client._prompt_truncated
batch_calls = [a for a in audit if t0 <= a["ts"] <= t1 and a["model"] in models and a["prompt_tokens"]]
trunc = {"calls": len(batch_calls),
         "at_ceiling": sum(1 for a in batch_calls if a["num_ctx"] and a["prompt_tokens"] >= 0.98 * a["num_ctx"]),
         "shrunk_flag": sum(1 for a in batch_calls if a["est"] and a["prompt_tokens"] < 0.75 * a["est"]),
         "max_prompt_over_ctx": round(max((a["prompt_tokens"] / a["num_ctx"] for a in batch_calls if a["num_ctx"]), default=0), 3),
         "median_reported_over_estimate": round(st.median([a["prompt_tokens"] / a["est"] for a in batch_calls if a["est"]] or [0]), 3),
         "think_tags": sum(1 for a in audit if a["think"])}
after = [a for a in audit if a["ts"] > max(r["end"] for r in runs) + dt.timedelta(minutes=20)]
out_of_batch: dict[str, Any] = {"calls_after_batch": len(after), "by": collections.Counter(f"{a['model']} | {a['error'][:40] or 'ok'}" for a in after),
                "first": min((a["ts"] for a in after), default=None), "last": max((a["ts"] for a in after), default=None)}
judge_calls: collections.Counter[str] = collections.Counter(a["model"] for a in audit if t0 <= a["ts"] <= t1 and a["model"] in ("gpt-4o-mini", "judge-phi"))

# ---------------- STEP 2: analysis ----------------
def valid_scores(rs, d): return [r["scores"][d] for r in rs if r["scores"][d] is not None]
scorecard: list[dict[str, Any]] = []
cs_cells: list[dict[str, Any]] = []
fx_cells: list[dict[str, Any]] = []
ordering: list[dict[str, Any]] = []
for m in MODEL_ORDER:
    for script in ("cs203", "fixture"):
        rs = [r for r in runs if r["model"] == m and r["script"] == script]
        if not rs: continue
        n = len(rs)
        row = {"model": m, "script": script, "runs": n, "complete_runs": sum(1 for r in rs if not r["failed"]),
               "dim_validity": {d: pct(len(valid_scores(rs, d)), n) for d in DIMS},
               "lat_mean": round(st.mean(r["duration"] for r in rs), 1), "lat_median": round(st.median(r["duration"] for r in rs), 1),
               "lat_p95": p95([r["duration"] for r in rs]), "lat_max": max(r["duration"] for r in rs)}
        # reliability: stdev over repeats per (bundle, dim)
        cells = []
        for b in sorted({r["bundle"] for r in rs}):
            for d in DIMS:
                v = valid_scores([r for r in rs if r["bundle"] == b], d)
                if len(v) >= 2: cells.append(st.stdev(v))
        row.update(stab_mean_sd=round(st.mean(cells), 3) if cells else None, stab_cells=len(cells),
                   stab_zero_share=pct(sum(1 for c in cells if c == 0), len(cells)))
        # grounding
        js = [r["judge"] for r in rs if r["judge"]]
        jv = [j for j in js if j.get("citation_hallucination_rate") is not None]
        cit = [r["dims"][d] for r in rs for d in DIMS if r["dims"][d]["citations"] is not None]
        row.update(judge_rows=len(js), judge_valid=len(jv), judge_actual=rs[0]["judge_actual"],
                   grounded=mean([j.get("citation_grounded_rate") for j in jv]), halluc=mean([j.get("citation_hallucination_rate") for j in jv]),
                   dropped_by_code=sum(int(j.get("citations_dropped_by_code") or 0) for j in js),
                   cites_total=sum(c["citations"] for c in cit), cites_found=sum(c["found"] for c in cit),
                   cites_found_share=pct(sum(c["found"] for c in cit), sum(c["citations"] for c in cit)),
                   author_summary_cites=sum(c.get("author_summary", 0) for c in cit),
                   retried_dims=sum(1 for r in rs for d in DIMS if r["dims"][d]["attempts"] > 1),
                   missing_data_ones={d: sum(1 for r in rs if r["scores"][d] == 1 and r["dims"][d]["citations"] == 0) for d in DATA_DIMS},
                   ones={d: sum(1 for r in rs if r["scores"][d] == 1) for d in DATA_DIMS})
        # accuracy vs reference
        present_all = [d for d in DIMS if all(r["scores"][d] is not None for r in rs)]
        row["dims_in_every_run"] = present_all
        def mae(dims, _rs=rs):
            e = [r["scores"][d] - GOLD[r["bundle"]][d] for r in _rs for d in dims]
            b = [BASELINE - GOLD[r["bundle"]][d] for r in _rs for d in dims]
            return {"n": len(e), "mae": round(st.mean(abs(x) for x in e), 3) if e else None, "bias": round(st.mean(e), 3) if e else None,
                    "baseline_mae": round(st.mean(abs(x) for x in b), 3) if b else None}
        row["acc_all"] = mae(present_all)
        row["acc_commit"] = mae([d for d in present_all if d in COMMIT_DIMS])
        row["acc_data"] = mae([d for d in present_all if d in DATA_DIMS])
        cells_out = cs_cells if script == "cs203" else fx_cells
        for b in sorted({r["bundle"] for r in rs}):
            br = [r for r in rs if r["bundle"] == b]
            for d in DIMS + ["overall"]:
                v = [r["overall"] for r in br if not r["failed"]] if d == "overall" else valid_scores(br, d)
                g = (st.mean(GOLD[b].values()) if d == "overall" else GOLD[b][d])
                cells_out.append({"model": m, "script": script, "bundle": b, "bundle_label": BUNDLE_LABEL.get(b, b), "archetype": ARCHETYPE.get(b, ""),
                                  "dim": d, "n": len(v), "mean": round(st.mean(v), 3) if v else None, "sd": round(st.stdev(v), 3) if len(v) >= 2 else (0.0 if len(v) == 1 else None),
                                  "gold": round(g, 3), "err": round(st.mean(v) - g, 3) if v else None, "values": v})
        if script == "fixture":
            links_ok = links_total = links_na = 0
            for d in DIMS + ["overall"]:
                order = eo.COLLABORATION_ORDER if d == "collaboration" else eo.GENERAL_ORDER
                cm = {c["archetype"]: c for c in fx_cells if c["model"] == m and c["dim"] == d}
                for link in order:
                    key = f"{link.higher} {link.op} {link.lower}"
                    hi, lo = cm.get(link.higher), cm.get(link.lower)
                    if not hi or not lo or hi["mean"] is None or lo["mean"] is None:
                        ordering.append({"model": m, "dim": d, "link": key, "holds": None, "gap": None, "note": "no valid scores"}); links_na += 1; continue
                    res = eo.check_order({link.higher: hi["mean"], link.lower: lo["mean"]}, [link],
                                         {link.higher: hi["sd"] or 0.0, link.lower: lo["sd"] or 0.0})[key]
                    ordering.append({"model": m, "dim": d, "link": key, **res})
                    links_total += 1; links_ok += res["holds"]
            row.update(order_held=links_ok, order_total=links_total, order_na=links_na)
            fxe = [abs(r["scores"][d] - GOLD[r["bundle"]][d]) for r in rs for d in present_all]
            row["fixture_gold_mae"] = round(st.mean(fxe), 3) if fxe else None
        scorecard.append(row)

# does the team-authored gold itself satisfy each expected-order link? (point check, no noise band)
gold_order = {}
inv_arch = {v: k for k, v in ARCHETYPE.items()}
for d in DIMS + ["overall"]:
    order = eo.COLLABORATION_ORDER if d == "collaboration" else eo.GENERAL_ORDER
    pts = {a: (st.mean(GOLD[t].values()) if d == "overall" else GOLD[t][d]) for a, t in inv_arch.items()}
    for key, res in eo.check_order(pts, order).items():
        gold_order[f"{d}|{key}"] = res["holds"]
for o in ordering:
    o["gold_holds"] = gold_order.get(f"{o['dim']}|{o['link']}")
for row in scorecard:
    if row["script"] == "fixture":
        mine = [o for o in ordering if o["model"] == row["model"] and o["holds"] is not None and o["gold_holds"]]
        row["order_held_gold_consistent"] = sum(o["holds"] for o in mine)
        row["order_total_gold_consistent"] = len(mine)

# common dims across models for a like-for-like CS203 comparison
common_cs = [d for d in DIMS if all(all(r["scores"][d] is not None for r in runs if r["model"] == m and r["script"] == "cs203") for m in MODEL_ORDER)]
for row in scorecard:
    if row["script"] != "cs203": continue
    rs = [r for r in runs if r["model"] == row["model"] and r["script"] == "cs203"]
    e = [r["scores"][d] - GOLD[r["bundle"]][d] for r in rs for d in common_cs]
    if not e:   # no dimension is scored in every run of every model (likely when many sessions are pooled)
        row["acc_common"] = {"dims": common_cs, "n": 0, "mae": None, "bias": None, "baseline_mae": None}
        continue
    row["acc_common"] = {"dims": common_cs, "n": len(e), "mae": round(st.mean(abs(x) for x in e), 3), "bias": round(st.mean(e), 3),
                         "baseline_mae": round(st.mean(abs(BASELINE - GOLD[r["bundle"]][d]) for r in rs for d in common_cs), 3)}

# cross-model agreement on matched (bundle, dim) means
cell_mean = {(c["model"], c["bundle"], c["dim"]): c["mean"] for c in cs_cells + fx_cells if c["dim"] != "overall" and c["mean"] is not None}
agreement = []
for i, a in enumerate(MODEL_ORDER):
    for b in MODEL_ORDER[i + 1:]:
        keys = sorted({(x[1], x[2]) for x in cell_mean if x[0] == a} & {(x[1], x[2]) for x in cell_mean if x[0] == b})
        xa, xb = [cell_mean[(a, *k)] for k in keys], [cell_mean[(b, *k)] for k in keys]
        matched_pairs = [(x, y) for x, y in zip(xa, xb, strict=False) if not (x == 1 and y == 1)]
        agreement.append({"a": a, "b": b, "n": len(keys), "r": pearson(xa, xb), "shared_ones": len(keys) - len(matched_pairs),
                          "n_excl": len(matched_pairs), "r_excl_shared_ones": pearson([pair[0] for pair in matched_pairs], [pair[1] for pair in matched_pairs])})

# ---------------- tidy table ----------------
tidy = []
for r in sorted(runs, key=lambda r: (r["script"], MODEL_ORDER.index(r["model"]), r["bundle"], r["repeat"])):
    for d in DIMS:
        g = GOLD.get(r["bundle"], {}).get(d)
        s = r["scores"][d]
        info = r["dims"][d]
        tidy.append({"script": r["script"], "session": r["session"], "model": r["model"], "bundle": r["bundle"], "bundle_label": r["bundle_label"],
                     "archetype": r["archetype"], "repeat": r["repeat"], "trace_id": r["trace_id"], "dimension": d, "score": s, "reference": g,
                     "signed_error": (s - g) if s is not None and g is not None else None, "failed": d in r["failed"],
                     "failure_class": r["failure_class"].get(d, ""), "attempts": info["attempts"], "citations": info["citations"],
                     "citations_found_in_prompt": info["found"], "run_overall": r["overall"], "run_seconds": r["duration"],
                     "retry_spiral": r["spiral"], "judge": r["judge_actual"],
                     "judge_grounded_rate": (r["judge"] or {}).get("citation_grounded_rate"),
                     "judge_hallucination_rate": (r["judge"] or {}).get("citation_hallucination_rate"),
                     "citations_dropped_by_code": (r["judge"] or {}).get("citations_dropped_by_code")})
with (HERE / "results_tidy.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(tidy[0])); w.writeheader(); w.writerows(tidy)

explorer = [{"script": r["script"], "model": r["model"], "bundle": r["bundle_label"], "archetype": r["archetype"], "repeat": r["repeat"],
             "scores": [r["scores"][d] for d in DIMS], "overall": round(r["overall"], 2), "failed": [f"{d}: {r['failure_class'][d]}" for d in r["failed"]],
             "seconds": r["duration"], "spiral": r["spiral"], "session": r["session"], "line": r["line"],
             "grounded": (r["judge"] or {}).get("citation_grounded_rate"), "halluc": (r["judge"] or {}).get("citation_hallucination_rate"),
             "cites": sum(r["dims"][d]["citations"] or 0 for d in DIMS), "found": sum(r["dims"][d]["found"] or 0 for d in DIMS),
             "retries": sum(max(0, r["dims"][d]["attempts"] - 1) for d in DIMS)}
            for r in sorted(runs, key=lambda r: (r["script"], MODEL_ORDER.index(r["model"]), r["bundle"], r["repeat"]))]

result: dict[str, Any] = {"generated": now.isoformat(timespec="seconds"), "dims": DIMS, "models": MODEL_ORDER, "gold": GOLD,
          "batch_files": [p.name for p in batch_files], "older_files": older_files, "health": health, "truncation": trunc,
          "out_of_batch": {**out_of_batch, "by": dict(out_of_batch["by"]), "first": str(out_of_batch["first"]), "last": str(out_of_batch["last"])},
          "judge_calls_in_window": dict(judge_calls), "score_mismatch_audit_vs_raw": score_mismatch,
          "scorecard": scorecard, "cs_cells": cs_cells, "fx_cells": fx_cells, "ordering": ordering, "agreement": agreement,
          "common_cs_dims": common_cs, "explorer": explorer,
          "audit_link_coverage": {"dims": len(runs) * 6, "linked_ok": sum(1 for r in runs for d in DIMS if r["dims"][d]["citations"] is not None)}}
result["gold_order_violations"] = [k for k, v in gold_order.items() if not v]
(HERE / "analysis.json").write_text(json.dumps(result, indent=1, default=str))

# ---------------- run_health.md ----------------
L = ["# Run health: local-LLM grading batch", "",
     f"Generated {result['generated']} by `research/dashboard/analyze.py` (read-only on `results/` and `audit_logs/`).", "",
     f"Files analysed from `ai-engine/results/`: **{len(batch_files)}** (filters: since={args.since or 'none'}, experiment={args.experiment or 'none'}). Excluded by filters: {len(older_files)}. Judge-only sessions skipped: {len(judge_only)}.", "",
     "Each invocation writes 3 files sharing one session timestamp (`services/save_results.py`: `_SESSION_TS` is set once per process): `raw_results_<experiment>_<ts>.jsonl`, `summary_<experiment>_<ts>.json` and `raw_judge_results_<experiment>_<ts>.jsonl`. Nothing is overwritten on re-run unless two processes start in the same second.", "",
     "| Script | Model | Session | Files | Runs (expected / raw lines / summary) | Repeats per bundle | Dims scored | Complete runs | Judge rows | Median s | Verdict | Reason |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for h in health:
    L.append(f"| {h['script']} | {h['model']} | {h['session']} | {len(h['files'])}/3 | {h['runs_expected']} / {h['raw_lines']} / {h['summary_runs']} | "
             f"{', '.join(f'{BUNDLE_LABEL.get(k, k)} {v}' for k, v in h['repeats_per_bundle'].items())} | {h['dims_scored']}/{h['dims_expected']} | "
             f"{h['complete_runs']}/{h['raw_lines']} | {h['judge_rows']} | {h['latency_median']} | **{h['verdict']}** | {h['reason']} |")
L += ["", "## Failed dimensions", "", "| Script | Model | Bundle | Repeat | Dimension | Class | Run seconds | Audit attempts |", "|---|---|---|---|---|---|---|---|"]
for r in sorted(runs, key=lambda r: (r["script"], MODEL_ORDER.index(r["model"]), r["bundle"], r["repeat"])):
    for d, c in r["failure_class"].items():
        L.append(f"| {r['script']} | {r['model']} | {r['bundle_label']} | {r['repeat']} | {d} | {c} | {r['duration']} | {r['dims'][d]['attempts']} |")
L += ["", "## Checks", "",
      f"- Summary files agree with raw files for every invocation: {'yes' if all(not h['summary_mismatches'] for h in health) else 'NO'}.",
      f"- Scores in audit logs match raw scores on {result['audit_link_coverage']['linked_ok']} linked dimensions; mismatches: {len(score_mismatch)}.",
      f"- `<think>` tags in raw model output: {trunc['think_tags']}. Calls at the num_ctx ceiling: {trunc['at_ceiling']}; largest prompt = {trunc['max_prompt_over_ctx']:.0%} of num_ctx.",
      f"- Calls that trip the 'prompt most likely truncated' warning (reported < 75% of estimate): {trunc['shrunk_flag']} of {trunc['calls']}; median reported/estimate = {trunc['median_reported_over_estimate']}. None is near the context limit, so these warnings are false positives from the chars/4 estimate.",
      f"- Instant failures (< 2 s): {sum(h['instant_runs'] for h in health)}. Retry spirals (> 3x model median): {sum(h['spiral_runs'] for h in health)}.",
      f"- Judge calls in the batch window: {dict(judge_calls)}. Fixture traces are judged by gpt-4o-mini through OpenAI (`judges/citation_ground_custom_judge.py:199-201`), although the judge files label every row `sprintsight-judge-phi`.",
      f"- Activity after the batch: {out_of_batch['calls_after_batch']} calls {dict(out_of_batch['by'])} between {out_of_batch['first']} and {out_of_batch['last']} UTC, with no result files.",
      f"- Expected-order links the team-authored gold itself violates: {', '.join(result['gold_order_violations']) or 'none'}."]
(HERE / "run_health.md").write_text("\n".join(L) + "\n")
print("runs", len(runs), "batch files", len(batch_files), "older", len(older_files))
print("audit link", result["audit_link_coverage"], "score mismatches", len(score_mismatch), score_mismatch[:5])
print("truncation", trunc); print("out of batch", result["out_of_batch"]); print("judge calls", dict(judge_calls))
for h in health: print(h["verdict"], h["script"], h["model"], h["raw_lines"], h["summary_runs"], h["dims_scored"], "/", h["dims_expected"], h["judge_rows"], "|", h["reason"])
