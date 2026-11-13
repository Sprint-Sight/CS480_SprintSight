import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# run `streamlit run dashboard.py` to launch the dashboard

DIMS = ["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]
GOLD = {  # instructor gold, same order as DIMS (from research/gold and cs203_groundtruth.py)
    "Team_Alpha": [9, 9, 8, 9, 9, 8], "Team_Delta": [6, 6, 6, 6, 8, 5], "Team_Epsilon": [8, 7, 7, 8, 2, 8],
    "Team_Gamma": [3, 2, 1, 2, 3, 1], "Team_Theta": [5, 3, 3, 4, 1, 4],
    "cs203g6": [4, 4, 3, 3, 4, 6], "fa7d4476-78fd-4013-8d66-1e290a65fe1c": [7, 7, 8, 7, 6, 4],
}
LABEL = {"cs203g6": "CS203 G6", "fa7d4476-78fd-4013-8d66-1e290a65fe1c": "CS203 JY"}
kind_of = lambda t: "fixture" if t.startswith("Team_") else "cs203"

st.set_page_config(page_title="SprintSight evaluation", layout="wide")

@st.cache_data
def load(folder: str):
    runs, judges = [], []
    for f in sorted(Path(folder).glob("raw_results_*.jsonl")):
        session = f.stem.rsplit("_", 1)[-1]
        for line in filter(str.strip, f.read_text().splitlines()):
            r = json.loads(line)
            if len(r["failed_dimensions"]) == len(DIMS):      # outage runs are stored as 0.0
                continue
            runs.append({"session": session, "model": r["model"].removeprefix("sprintsight-"),
                         "team": r["team_id"], "trace_id": r["trace_id"], "overall": r["overall_score"],
                         "seconds": r["duration_seconds"], "failed": len(r["failed_dimensions"]),
                         "date": r["timestamp"][:10], **r["dimension_scores"]})
    for f in sorted(Path(folder).glob("raw_judge_results_*.jsonl")):
        judge = "gpt-4o-mini" if "openai" in f.name else "phi"   # the judge_model field is mislabelled
        for line in filter(str.strip, f.read_text().splitlines()):
            j = json.loads(line)
            s = {k: v for k, v in j["scores"].items() if k != "gold"}
            judges.append({"trace_id": j["trace_id"], "judge": judge, **s})
    return pd.DataFrame(runs), pd.DataFrame(judges)

def flags(r):
    out = []
    if pd.notna(r.get("grade_penalised_mae")) and r["grade_penalised_mae"] > 3: out.append("MAE>3")
    h = r.get("citation_hallucination_rate")
    if pd.isna(h): out.append("no judge result")
    elif h > 0.1: out.append("hallucination>10%")
    if pd.notna(r.get("citation_count")) and r["citation_count"] < 10: out.append("<10 citations")
    if pd.notna(r.get("citation_grounded_rate")) and r["citation_grounded_rate"] < 0.5: out.append("grounded<50%")
    if r.get("citations_dropped_by_code", 0) > 0: out.append("dropped by code")
    return ", ".join(out)

DEFAULT_RESULTS = Path(__file__).parents[2] / "results"
folder = st.sidebar.text_input("Results folder", str(DEFAULT_RESULTS))
runs, judges = load(folder)
if runs.empty:
    st.error("No raw_results_*.jsonl files found."); st.stop()

runs["set"] = runs["team"].map(kind_of)
runs["team_label"] = runs["team"].map(lambda t: LABEL.get(t, t.removeprefix("Team_")))
if st.sidebar.checkbox("Drop identical reruns", True):
    runs = runs.drop_duplicates(subset=["set", "model", "team", *DIMS])
sets = st.sidebar.multiselect("Team set", ["fixture", "cs203"], ["fixture", "cs203"])
models = st.sidebar.multiselect("Models", sorted(runs.model.unique()), sorted(runs.model.unique()))
runs = runs[runs["set"].isin(sets) & runs.model.isin(models)]

long = runs.melt(id_vars=["session", "model", "team", "team_label", "set", "date"], value_vars=DIMS,
                 var_name="dimension", value_name="score").dropna(subset=["score"])
long["gold"] = [GOLD[t][DIMS.index(d)] for t, d in zip(long.team, long.dimension)]
long["error"] = long.score - long.gold
long["abs_error"] = long.error.abs()
gold_overall = {t: sum(v) / 6 for t, v in GOLD.items()}
runs["gold_overall"] = runs.team.map(gold_overall)

st.title("SprintSight evaluation")
c = st.columns(5)
c[0].metric("Runs", len(runs))
c[1].metric("Fully scored", f"{(runs.failed == 0).mean():.0%}")
c[2].metric("Within ±1 of gold", f"{(long.abs_error <= 1).mean():.0%}")
c[3].metric("Dimension MAE", f"{long.abs_error.mean():.2f}")
c[4].metric("Bias (+ = generous)", f"{long.error.mean():+.2f}")

t1, t2, t3, t4 = st.tabs(["Models", "Dimensions", "Teams vs gold", "Evidence checks"])

with t1:
    g = long.groupby(["model", "session", "set"]).agg(mae=("abs_error", "mean"), bias=("error", "mean"),
                                                      within1=("abs_error", lambda x: (x <= 1).mean())).reset_index()
    r = runs.groupby(["model", "session", "set"]).agg(seconds=("seconds", "mean"), complete=("failed", lambda x: (x == 0).mean())).reset_index()
    st.dataframe(g.merge(r), use_container_width=True, hide_index=True,
                 column_config={"within1": st.column_config.ProgressColumn("within ±1", min_value=0, max_value=1),
                                "complete": st.column_config.ProgressColumn("fully scored", min_value=0, max_value=1)})
    st.altair_chart(alt.Chart(g).mark_bar().encode(y="model:N", x="mae:Q", color="session:N", yOffset="session:N",
                    tooltip=["model", "session", "mae"]), use_container_width=True)

with t2:
    d = long.groupby(["dimension", "set"]).agg(mae=("abs_error", "mean"), bias=("error", "mean")).reset_index()
    st.altair_chart(alt.Chart(d).mark_bar().encode(y="dimension:N", x="mae:Q", color="set:N", yOffset="set:N",
                    tooltip=["dimension", "set", "mae", "bias"]), use_container_width=True)
    st.dataframe(d, hide_index=True, use_container_width=True)

with t3:
    pts = alt.Chart(runs).mark_circle(size=70).encode(y=alt.Y("team_label:N", sort="-x"), x=alt.X("overall:Q", scale=alt.Scale(domain=[0, 10])),
                                                      color="model:N", tooltip=["model", "session", "overall", "gold_overall"])
    gold = alt.Chart(runs).mark_tick(color="black", thickness=3, size=30).encode(y="team_label:N", x="gold_overall:Q")
    st.altair_chart(pts + gold, use_container_width=True)

with t4:
    if judges.empty:
        st.info("No raw_judge_results_*.jsonl files found.")
    else:
        j = judges.merge(runs[["trace_id", "model", "team_label", "set", "session"]], on="trace_id", how="inner")
        j["flags"] = j.apply(flags, axis=1)
        j["passes"] = j.flags == ""
        s = j.groupby(["model", "judge"]).agg(records=("trace_id", "count"), grounded=("citation_grounded_rate", "mean"),
                                              hallucinated=("citation_hallucination_rate", "mean"),
                                              dropped=("citations_dropped_by_code", "sum"), pass_rate=("passes", "mean")).reset_index()
        st.caption(f"{j.passes.mean():.0%} of {len(j)} judged records pass every review gate.")
        st.dataframe(s, hide_index=True, use_container_width=True)
        st.dataframe(j[~j.passes][["model", "judge", "team_label", "session", "flags"]], hide_index=True, use_container_width=True)