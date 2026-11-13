"""Build the self-contained dashboard from analysis.json (run analyze.py first).
Writes dashboard.html (standalone document) and dashboard_page.html (same page without the document
skeleton, for publishing as an artifact). No CDN, fonts or network calls."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
a = json.loads((HERE / "analysis.json").read_text())
keep = ["generated", "dims", "models", "health", "scorecard", "cs_cells", "fx_cells", "ordering", "agreement", "explorer",
        "truncation", "out_of_batch", "judge_calls_in_window", "gold_order_violations", "common_cs_dims", "batch_files",
        "older_files", "audit_link_coverage", "score_mismatch_audit_vs_raw"]
data = json.dumps({k: a[k] for k in keep}, separators=(",", ":")).replace("</", "<\\/")

PAGE = r"""<title>SprintSight grading trials</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Layout: one column of numbered report sections under a sticky filter bar. */
:root {
  --bg: #f6f7f9; --panel: #ffffff; --fg: #1b1f24; --muted: #5b6573; --line: #d9dee5; --soft: #eef1f5;
  --m0: #0072B2; --m1: #E69F00; --m2: #009E73; --m3: #CC79A7; --m4: #D55E00;
  --neg: #0072B2; --pos: #D55E00; --ok: #00795a; --warn: #9a6400; --bad: #b8460b; --gold: #1b1f24;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12151a; --panel: #1a1f26; --fg: #e8ebef; --muted: #9aa4b2; --line: #2e3640; --soft: #222831;
  --m0: #56B4E9; --m1: #E69F00; --m2: #2fc59a; --m3: #e08fc0; --m4: #ff8a4c;
  --neg: #56B4E9; --pos: #ff8a4c; --ok: #4fd1a5; --warn: #f0b84a; --bad: #ff8a4c; --gold: #e8ebef; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #12151a; --panel: #1a1f26; --fg: #e8ebef; --muted: #9aa4b2; --line: #2e3640; --soft: #222831;
  --m0: #56B4E9; --m1: #E69F00; --m2: #2fc59a; --m3: #e08fc0; --m4: #ff8a4c;
  --neg: #56B4E9; --pos: #ff8a4c; --ok: #4fd1a5; --warn: #f0b84a; --bad: #ff8a4c; --gold: #e8ebef; color-scheme: dark; }
body { background: var(--bg); color: var(--fg); font-family: var(--sans); font-size: 14px; line-height: 1.5; margin: 0; }
.wrap { max-width: 1240px; margin: 0 auto; padding-block: 24px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 28px; }
h1 { font-size: 26px; margin: 0; letter-spacing: -.01em; text-wrap: balance; }
h2 { font-size: 18px; margin: 0; text-wrap: balance; }
h3 { font-size: 14px; margin: 0 0 6px; }
p { margin: 0; max-width: 78ch; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.mono { font-family: var(--mono); font-size: 12px; }
section { display: grid; gap: 12px; min-width: 0; scroll-margin-top: 72px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; min-width: 0; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); }
.bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 20; background: var(--bg); border-bottom: 1px solid var(--line); padding-block: 10px; display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 30; background: var(--bg); }
.bar label { display: inline-flex; gap: 6px; align-items: center; }
select, input[type=search] { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
input[type=checkbox] { accent-color: var(--m0); }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.nav { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; }
.nav a { color: var(--muted); text-decoration: none; } .nav a:hover, .nav a:focus-visible { color: var(--fg); text-decoration: underline; }
.tw { overflow-x: auto; max-width: 100%; }
.tall { max-height: 520px; overflow: auto; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; white-space: nowrap; position: sticky; top: 0; background: var(--panel); }
td.n, th.n { text-align: right; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 600; border: 1px solid currentColor; white-space: nowrap; }
.c-ok { color: var(--ok); } .c-warn { color: var(--warn); } .c-bad { color: var(--bad); } .c-na { color: var(--muted); }
.badge { display: inline-block; font-size: 11px; color: var(--muted); background: var(--soft); border-radius: 4px; padding: 0 6px; margin-left: 4px; white-space: nowrap; }
.badge.warn { color: var(--warn); }
.kpis { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.kpi b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; }
.kpi span { font-size: 12px; color: var(--muted); }
svg { display: block; max-width: 100%; }
svg text { fill: var(--fg); font-family: var(--sans); font-size: 11px; }
svg .mut { fill: var(--muted); }
svg .grid { stroke: var(--line); stroke-width: 1; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--muted); align-items: center; }
.legend span { display: inline-flex; gap: 6px; align-items: center; }
.links { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.small-multiples { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); }
details > summary { cursor: pointer; font-weight: 600; }
ul { margin: 0; padding-left: 18px; display: grid; gap: 6px; max-width: 90ch; }
.caveats { border-left: 3px solid var(--warn); }
.tip { position: absolute; pointer-events: none; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.15); z-index: 40; max-width: 260px; }
.rel { position: relative; }
:focus-visible { outline: 2px solid var(--m0); outline-offset: 2px; }
</style>

<div class="wrap">
  <header style="display:grid;gap:6px">
    <h1>SprintSight grading trials</h1>
    <p class="muted">Five local Ollama models graded two real CS203 sprints and five synthetic fixtures, three repeats each, on six rubric dimensions. Pilot with small n: no significance claims, and every figure shows its n.</p>
    <p class="small muted" id="meta"></p>
  </header>

  <div class="bar" role="region" aria-label="Filters">
    <label for="f-script">Script
      <select id="f-script"><option value="all">Both</option><option value="cs203">CS203 (real sprints)</option><option value="fixture">Fixtures (synthetic)</option></select>
    </label>
    <div id="f-models" style="display:flex;flex-wrap:wrap;gap:4px 12px" aria-label="Models"></div>
    <nav class="nav" aria-label="Sections">
      <a href="#s1">Run health</a><a href="#s2">Scorecard</a><a href="#s3">Signed error</a><a href="#s4">Fixtures</a><a href="#s5">Reliability</a><a href="#s6">Grounding</a><a href="#s7">Runs</a><a href="#caveats">Caveats</a>
    </nav>
  </div>

  <section id="s1">
    <h2>1. Run health</h2>
    <div class="kpis" id="kpis"></div>
    <div class="card"><h3>Expected versus actual, per invocation</h3>
      <p class="small muted">Expected = bundles x 3 repeats (CS203: 2 bundles, fixtures: 5) and 3 files per invocation (raw, summary, judge).</p>
      <div class="tw"><table id="t-health"></table></div></div>
    <div class="grid">
      <div class="card"><h3>Failed dimensions by cause</h3><div class="tw"><table id="t-fail-class"></table></div></div>
      <div class="card"><h3>Failed dimensions by rubric dimension</h3><div class="tw"><table id="t-fail-dim"></table></div></div>
    </div>
  </section>

  <section id="s2">
    <h2>2. Per-model scorecard</h2>
    <p class="small muted">No composite score. Accuracy uses only dimensions present in every run of that model and script (the coverage badge says which). The baseline always predicts 5.5 on the same cells. Ordering counts expected-order links that pass the noise-aware check; "gold-consistent" drops the link the team-authored gold itself breaks.</p>
    <div class="card"><div class="tw"><table id="t-score"></table></div></div>
    <div class="card"><h3>Cross-model agreement</h3>
      <p class="small muted">Pearson r on matched bundle x dimension means across both scripts. Not shown below 5 points. Points where both models scored 1 inflate r, so r is also shown without them.</p>
      <div class="tw"><table id="t-agree"></table></div></div>
  </section>

  <section id="s3">
    <h2>3. Signed error against the reference</h2>
    <p class="small muted">Mean over repeats of model score minus reference score. Blue means harsher than the reference, orange more generous. Each cell shows the error and its n of valid repeats. Overall uses complete runs only.</p>
    <div class="legend" id="heat-legend"></div>
    <div class="grid" id="heat"></div>
  </section>

  <section id="s4">
    <h2>4. Fixture trajectories and expected order</h2>
    <p class="small muted">Fixtures are placed in the expected order for the chosen dimension, best first. Dots are means over three repeats, with bars of one standard deviation. Hollow diamonds are the team-authored gold. Chips show each link of the expected order: pass, fail, or no data.</p>
    <label for="f-dim">Dimension <select id="f-dim"></select></label>
    <div class="small-multiples" id="traj"></div>
  </section>

  <section id="s5">
    <h2>5. Reliability and latency</h2>
    <div class="card"><h3>Seconds per run</h3>
      <p class="small muted">Each dot is one run. The tall tick is the median and the short tick is p95. Ringed dots took more than 3x the model's median (retry spiral).</p>
      <div id="lat" class="rel"></div></div>
    <div class="card"><h3>Latency and stability table</h3>
      <p class="small muted">Stability is the standard deviation across the 3 repeats per bundle x dimension, averaged. Temperature is 0, so near-zero spread reflects deterministic decoding, not validity.</p>
      <div class="tw"><table id="t-lat"></table></div></div>
  </section>

  <section id="s6">
    <h2>6. Grounding</h2>
    <p class="small muted">Judge coverage is runs with citation metrics over runs. The code check asks whether each cited identifier appears in the prompt the model was sent (from audit logs). "Dropped by code" is the pipeline's own resolver. Contributor-summary citations are lines such as "Student3: 20 commits, +170/-201 lines" that the prompt shows but the resolver cannot match.</p>
    <div class="card"><div class="tw"><table id="t-ground"></table></div></div>
  </section>

  <section id="s7">
    <h2>7. Run explorer</h2>
    <div style="display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center">
      <label for="f-q">Search <input type="search" id="f-q" placeholder="bundle, error, session"></label>
      <label><input type="checkbox" id="f-failed"> Only runs with failed dimensions</label>
      <span class="small muted" id="exp-count"></span>
    </div>
    <div class="card"><div class="tw tall"><table id="t-runs"></table></div></div>
  </section>

  <section id="caveats" class="card caveats">
    <h2>Caveats</h2>
    <ul id="cav"></ul>
  </section>
</div>

<script type="application/json" id="data">__DATA__</script>
<script>
(() => {
  const D = JSON.parse(document.getElementById('data').textContent);
  const DIMS = D.dims, MODELS = D.models;
  const DL = {code_quality: 'Code quality', testing: 'Testing', documentation: 'Docs', requirements: 'Requirements', collaboration: 'Collab.', cicd: 'CI/CD', overall: 'Overall'};
  const ARCH = {high_performing: 'Alpha (high performing)', imbalanced_high_output: 'Epsilon (imbalanced)', good_collab_low_output: 'Delta (good collab)', lone_contributor_poor_outcome: 'Theta (lone contributor)', struggling: 'Gamma (struggling)'};
  const SHORT = {high_performing: 'HP', imbalanced_high_output: 'IMB', good_collab_low_output: 'GC', lone_contributor_poor_outcome: 'LONE', struggling: 'STR'};
  const GEN = ['high_performing', 'imbalanced_high_output', 'good_collab_low_output', 'lone_contributor_poor_outcome', 'struggling'];
  const COL = ['high_performing', 'good_collab_low_output', 'imbalanced_high_output', 'lone_contributor_poor_outcome', 'struggling'];
  const mcol = (m) => `var(--m${MODELS.indexOf(m) % 5})`;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const f = (v, d = 2) => v === null || v === undefined ? '–' : Number(v).toFixed(d);
  const pc = (v) => v === null || v === undefined ? '–' : Math.round(v * 100) + '%';
  const st = {script: 'all', models: new Set(MODELS), dim: 'code_quality', q: '', failedOnly: false};
  const okS = (s) => st.script === 'all' || st.script === s;
  const okM = (m) => st.models.has(m);

  document.getElementById('meta').textContent = `Batch: ${D.batch_files.length} files in ai-engine/results (older files excluded: ${D.older_files.length}). Analysis generated ${D.generated}. Audit-log scores match raw scores on ${D.audit_link_coverage.linked_ok} dimensions (${D.score_mismatch_audit_vs_raw.length} mismatches).`;

  // filters
  const fm = document.getElementById('f-models');
  MODELS.forEach((m) => {
    const id = 'fm-' + m.replace(/\W/g, '');
    fm.insertAdjacentHTML('beforeend', `<label for="${id}"><input type="checkbox" id="${id}" checked data-m="${esc(m)}"><span class="sw" style="background:${mcol(m)}"></span>${esc(m)}</label>`);
  });
  fm.addEventListener('change', (e) => { const m = e.target.dataset.m; if (!m) return; e.target.checked ? st.models.add(m) : st.models.delete(m); render(); });
  document.getElementById('f-script').addEventListener('change', (e) => { st.script = e.target.value; render(); });
  const dimSel = document.getElementById('f-dim');
  [...DIMS, 'overall'].forEach((d) => dimSel.insertAdjacentHTML('beforeend', `<option value="${d}">${DL[d]}</option>`));
  dimSel.addEventListener('change', (e) => { st.dim = e.target.value; renderTraj(); });
  document.getElementById('f-q').addEventListener('input', (e) => { st.q = e.target.value.toLowerCase(); renderRuns(); });
  document.getElementById('f-failed').addEventListener('change', (e) => { st.failedOnly = e.target.checked; renderRuns(); });

  const chip = (v) => ({OK: '<span class="chip c-ok">✓ OK</span>', PARTIAL: '<span class="chip c-warn">◐ PARTIAL</span>', FAILED: '<span class="chip c-bad">✕ FAILED</span>'}[v] || esc(v));
  const table = (id, head, rows) => { document.getElementById(id).innerHTML = `<thead><tr>${head.map((h) => `<th class="${h[1] || ''}">${h[0]}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${head.length}" class="muted">No rows for this filter.</td></tr>`}</tbody>`; };

  function renderHealth() {
    const H = D.health.filter((h) => okS(h.script) && okM(h.model));
    const runs = D.explorer.filter((r) => okS(r.script) && okM(r.model));
    const exp = H.reduce((s, h) => s + h.runs_expected, 0), got = H.reduce((s, h) => s + h.raw_lines, 0);
    const files = H.reduce((s, h) => s + h.files.length, 0), dims = H.reduce((s, h) => s + h.dims_scored, 0), dexp = H.reduce((s, h) => s + h.dims_expected, 0);
    const kp = [[`${got} / ${exp}`, 'runs recorded / expected'], [`${files} / ${H.length * 3}`, 'files present / expected'], [`${dims} / ${dexp}`, 'dimensions scored'],
      [`${runs.filter((r) => !r.failed.length).length} / ${runs.length}`, 'runs with all 6 dimensions'], [`${H.filter((h) => h.verdict === 'OK').length} OK · ${H.filter((h) => h.verdict === 'PARTIAL').length} partial · ${H.filter((h) => h.verdict === 'FAILED').length} failed`, 'invocations']];
    document.getElementById('kpis').innerHTML = kp.map(([b, s]) => `<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
    table('t-health', [['Script'], ['Model'], ['Session'], ['Files', 'n'], ['Runs exp / raw / summary', 'n'], ['Repeats per bundle'], ['Dims scored', 'n'], ['Complete runs', 'n'], ['Judge rows', 'n'], ['Median s', 'n'], ['Status'], ['Reason']],
      H.map((h) => `<tr><td>${h.script}</td><td><span class="sw" style="background:${mcol(h.model)}"></span> ${esc(h.model)}</td><td class="mono">${h.session}</td><td class="n">${h.files.length}/3</td><td class="n">${h.runs_expected} / ${h.raw_lines} / ${h.summary_runs}</td><td class="small">${Object.entries(h.repeats_per_bundle).map(([k, v]) => `${esc(k.length > 12 ? k.slice(0, 8) + '…' : k.replace('Team_', ''))} ${v}`).join(', ')}</td><td class="n">${h.dims_scored}/${h.dims_expected}</td><td class="n">${h.complete_runs}/${h.raw_lines}</td><td class="n">${h.judge_rows}</td><td class="n">${f(h.latency_median, 0)}</td><td>${chip(h.verdict)}</td><td class="small">${esc(h.reason)}</td></tr>`));
    const classes = [...new Set(runs.flatMap((r) => r.failed.map((x) => x.split(': ')[1])))];
    const ms = MODELS.filter(okM);
    table('t-fail-class', [['Cause'], ...ms.map((m) => [esc(m), 'n'])], classes.map((c) => `<tr><td>${esc(c)}</td>${ms.map((m) => `<td class="n">${runs.filter((r) => r.model === m).reduce((s, r) => s + r.failed.filter((x) => x.endsWith(c)).length, 0) || ''}</td>`).join('')}</tr>`));
    table('t-fail-dim', [['Dimension'], ...ms.map((m) => [esc(m), 'n'])], DIMS.map((d) => `<tr><td>${DL[d]}</td>${ms.map((m) => { const n = runs.filter((r) => r.model === m).reduce((s, r) => s + r.failed.filter((x) => x.startsWith(d + ':')).length, 0); const t = runs.filter((r) => r.model === m).length; return `<td class="n">${n ? `${n}/${t}` : ''}</td>`; }).join('')}</tr>`));
  }

  const accCell = (a, extra) => !a || a.n === 0 || a.mae === null ? '<span class="muted">–</span>' :
    `${f(a.mae)} <span class="muted">vs ${f(a.baseline_mae)}</span> ${a.mae < a.baseline_mae ? '<span class="chip c-ok">beats 5.5</span>' : '<span class="chip c-bad">not better than 5.5</span>'}<br><span class="small muted">bias ${a.bias > 0 ? '+' : ''}${f(a.bias)}</span><span class="badge">n=${a.n}${extra ? ' · ' + extra : ''}</span>`;
  function renderScore() {
    const S = D.scorecard.filter((s) => okS(s.script) && okM(s.model));
    table('t-score', [['Model'], ['Script'], ['Structural validity'], ['MAE vs reference (all covered dims)'], ['Commit-based dims'], ['Requirements + collaboration'], ['Fixture order links'], ['Latency p95', 'n'], ['Stability (mean SD)', 'n']],
      S.map((s) => {
        const cov = s.dims_in_every_run.length;
        const covB = `<span class="badge ${cov < 6 ? 'warn' : ''}">${cov}/6 dims</span>`;
        const valid = Object.values(s.dim_validity).reduce((a, b) => a + b, 0) / 6;
        const ord = s.script === 'fixture' ? `${s.order_held}/${s.order_total} <span class="badge">${s.order_na} n/a</span><br><span class="small muted">gold-consistent ${s.order_held_gold_consistent}/${s.order_total_gold_consistent}</span>` : '<span class="muted">–</span>';
        return `<tr><td><span class="sw" style="background:${mcol(s.model)}"></span> ${esc(s.model)}</td><td>${s.script}</td>
          <td>${s.complete_runs}/${s.runs} runs complete<br><span class="small muted">${pc(valid)} of dimensions scored</span></td>
          <td>${accCell(s.acc_all)} ${covB}</td><td>${accCell(s.acc_commit)}</td><td>${accCell(s.acc_data)}</td><td>${ord}</td>
          <td class="n">${f(s.lat_p95, 0)} s<br><span class="small muted">n=${s.runs}</span></td>
          <td class="n">${f(s.stab_mean_sd, 2)}<br><span class="small muted">${pc(s.stab_zero_share)} cells SD 0 · n=${s.stab_cells}</span></td></tr>`;
      }));
    const A = D.agreement.filter((g) => okM(g.a) && okM(g.b));
    table('t-agree', [['Model A'], ['Model B'], ['Matched points', 'n'], ['Pearson r', 'n'], ['Both scored 1', 'n'], ['r without shared 1s', 'n']],
      A.map((g) => `<tr><td>${esc(g.a)}</td><td>${esc(g.b)}</td><td class="n">${g.n}</td><td class="n">${g.n >= 5 ? f(g.r, 2) : 'n<5'}</td><td class="n">${g.shared_ones}</td><td class="n">${g.n_excl >= 5 ? f(g.r_excl_shared_ones, 2) : 'n<5'}</td></tr>`));
  }

  function renderHeat() {
    const cells = [...D.cs_cells, ...D.fx_cells].filter((c) => okS(c.script) && okM(c.model));
    const bundles = [...new Set(cells.map((c) => c.bundle_label))];
    const cols = [...DIMS, 'overall'], ms = MODELS.filter(okM);
    document.getElementById('heat-legend').innerHTML = `<span><span class="sw" style="background:var(--neg)"></span>harsher than reference</span><span><span class="sw" style="background:var(--pos)"></span>more generous</span><span>colour strength = size of error (capped at 4 points)</span>`;
    const host = document.getElementById('heat');
    host.innerHTML = bundles.map((b) => {
      const bc = cells.filter((c) => c.bundle_label === b);
      const cw = 52, rh = 30, lw = 92, th = 34, W = lw + cols.length * cw, Hh = th + ms.length * rh + 4;
      let s = `<svg viewBox="0 0 ${W} ${Hh}" width="100%" role="img" aria-label="Signed error for ${esc(b)}">`;
      cols.forEach((d, i) => { s += `<text x="${lw + i * cw + cw / 2}" y="${th - 10}" text-anchor="middle" class="mut">${DL[d]}</text>`; });
      ms.forEach((m, j) => {
        const y = th + j * rh;
        s += `<text x="${lw - 8}" y="${y + rh / 2 + 4}" text-anchor="end">${esc(m)}</text>`;
        cols.forEach((d, i) => {
          const c = bc.find((x) => x.model === m && x.dim === d), x = lw + i * cw;
          if (!c || c.err === null) { s += `<rect x="${x + 1}" y="${y + 1}" width="${cw - 2}" height="${rh - 2}" rx="3" fill="var(--soft)"/><text x="${x + cw / 2}" y="${y + rh / 2 + 4}" text-anchor="middle" class="mut">n=0</text>`; return; }
          const op = Math.min(Math.abs(c.err), 4) / 4 * 0.85 + 0.08;
          s += `<rect x="${x + 1}" y="${y + 1}" width="${cw - 2}" height="${rh - 2}" rx="3" fill="${c.err < 0 ? 'var(--neg)' : 'var(--pos)'}" fill-opacity="${c.err === 0 ? 0.06 : op}"><title>${esc(m)} · ${esc(b)} · ${DL[d]}: model ${f(c.mean)} vs reference ${f(c.gold)} (n=${c.n})</title></rect>`;
          s += `<text x="${x + cw / 2}" y="${y + rh / 2 + 1}" text-anchor="middle" style="font-weight:600">${c.err > 0 ? '+' : ''}${f(c.err, 1)}</text><text x="${x + cw / 2}" y="${y + rh / 2 + 11}" text-anchor="middle" class="mut" style="font-size:9px">n=${c.n}</text>`;
        });
      });
      return `<div class="card"><h3>${esc(b)}</h3><div class="tw">${s}</svg></div></div>`;
    }).join('') || '<p class="muted">No data for this filter.</p>';
  }

  function renderTraj() {
    const d = st.dim, order = d === 'collaboration' ? COL : GEN, ms = MODELS.filter(okM);
    const host = document.getElementById('traj');
    if (!okS('fixture')) { host.innerHTML = '<p class="muted">Fixtures are filtered out. Choose "Both" or "Fixtures".</p>'; return; }
    host.innerHTML = ms.map((m) => {
      const cs = D.fx_cells.filter((c) => c.model === m && c.dim === d);
      const W = 300, H = 210, l = 30, r = 10, t = 12, b = 46, x = (i) => l + i * (W - l - r) / (order.length - 1), y = (v) => t + (10 - v) / 10 * (H - t - b);
      let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(m)} ${DL[d]} by fixture">`;
      [0, 2, 4, 6, 8, 10].forEach((v) => { s += `<line class="grid" x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end" class="mut">${v}</text>`; });
      const pts = order.map((a, i) => ({i, c: cs.find((c) => c.archetype === a)}));
      const gp = pts.filter((p) => p.c).map((p) => `${x(p.i)},${y(p.c.gold)}`).join(' ');
      s += `<polyline points="${gp}" fill="none" stroke="var(--gold)" stroke-dasharray="3 3" stroke-width="1" opacity=".55"/>`;
      const mp = pts.filter((p) => p.c && p.c.mean !== null);
      s += `<polyline points="${mp.map((p) => `${x(p.i)},${y(p.c.mean)}`).join(' ')}" fill="none" stroke="${mcol(m)}" stroke-width="2" stroke-linejoin="round"/>`;
      pts.forEach((p) => {
        const c = p.c; s += `<text x="${x(p.i)}" y="${H - b + 16}" text-anchor="middle" class="mut">${SHORT[order[p.i]]}</text>`;
        if (!c) return;
        s += `<path d="M${x(p.i)} ${y(c.gold) - 5}l5 5-5 5-5-5z" fill="none" stroke="var(--gold)" stroke-width="1.2"><title>gold ${c.gold}</title></path>`;
        if (c.mean === null) { s += `<text x="${x(p.i)}" y="${H - b + 30}" text-anchor="middle" class="mut">n=0</text>`; return; }
        if (c.sd) s += `<line x1="${x(p.i)}" x2="${x(p.i)}" y1="${y(c.mean + c.sd)}" y2="${y(c.mean - c.sd)}" stroke="${mcol(m)}" stroke-width="2"/>`;
        s += `<circle cx="${x(p.i)}" cy="${y(c.mean)}" r="4.5" fill="${mcol(m)}"><title>${esc(ARCH[order[p.i]])}: mean ${f(c.mean)} ± ${f(c.sd)} (n=${c.n}), gold ${c.gold}</title></circle>`;
        s += `<text x="${x(p.i)}" y="${H - b + 30}" text-anchor="middle" class="mut">n=${c.n}</text>`;
      });
      s += '</svg>';
      const links = D.ordering.filter((o) => o.model === m && o.dim === d).map((o) => {
        const cls = o.holds === null ? 'c-na' : o.holds ? 'c-ok' : 'c-bad';
        const lab = o.link.split(' ').map((w) => SHORT[w] || w).join(' ');
        return `<span class="chip ${cls}" title="${esc(o.note)}${o.gap !== null ? ' · gap ' + o.gap : ''}${o.gold_holds === false ? ' · the gold itself breaks this link' : ''}">${o.holds === null ? '? ' : o.holds ? '✓ ' : '✕ '}${esc(lab)}${o.gold_holds === false ? ' (gold breaks)' : ''}</span>`;
      }).join('');
      return `<div class="card"><h3><span class="sw" style="background:${mcol(m)}"></span> ${esc(m)} · ${DL[d]}</h3>${s}<div class="links">${links}</div></div>`;
    }).join('');
  }

  function renderLat() {
    const R = D.explorer.filter((r) => okS(r.script) && okM(r.model));
    const groups = [];
    MODELS.filter(okM).forEach((m) => ['cs203', 'fixture'].filter(okS).forEach((s) => { const rs = R.filter((r) => r.model === m && r.script === s); if (rs.length) groups.push({m, s, rs}); }));
    const host = document.getElementById('lat');
    const W = Math.max(320, host.clientWidth || 800), lw = 150, r = 20, rh = 28, t = 8, b = 28, H = t + groups.length * rh + b;
    const max = Math.max(60, ...R.map((x) => x.seconds)) * 1.05, x = (v) => lw + v / max * (W - lw - r);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Seconds per run">`;
    const step = max > 400 ? 100 : 50;
    for (let v = 0; v <= max; v += step) s += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${t}" y2="${H - b}"/><text x="${x(v)}" y="${H - b + 16}" text-anchor="middle" class="mut">${v}s</text>`;
    groups.forEach((g, i) => {
      const y = t + i * rh + rh / 2, d = g.rs.map((r) => r.seconds).sort((a, b) => a - b);
      const med = d.length % 2 ? d[(d.length - 1) / 2] : (d[d.length / 2 - 1] + d[d.length / 2]) / 2, p95 = d[Math.max(0, Math.ceil(0.95 * d.length) - 1)];
      s += `<text x="${lw - 8}" y="${y + 4}" text-anchor="end">${esc(g.m)} · ${g.s} (n=${d.length})</text>`;
      g.rs.forEach((r, k) => { s += `<circle cx="${x(r.seconds)}" cy="${y + ((k % 3) - 1) * 4}" r="3.2" fill="${mcol(g.m)}" fill-opacity=".75" ${r.spiral ? 'stroke="var(--bad)" stroke-width="2"' : ''}><title>${esc(r.bundle)} rep ${r.repeat}: ${r.seconds}s${r.failed.length ? ' · failed ' + esc(r.failed.join(', ')) : ''}</title></circle>`; });
      s += `<line x1="${x(med)}" x2="${x(med)}" y1="${y - 10}" y2="${y + 10}" stroke="var(--fg)" stroke-width="2"/><line x1="${x(p95)}" x2="${x(p95)}" y1="${y - 6}" y2="${y + 6}" stroke="var(--fg)" stroke-width="1.5"/>`;
    });
    host.innerHTML = s + '</svg>';
    const S = D.scorecard.filter((x) => okS(x.script) && okM(x.model));
    table('t-lat', [['Model'], ['Script'], ['Runs', 'n'], ['Mean s', 'n'], ['Median s', 'n'], ['p95 s', 'n'], ['Max s', 'n'], ['Dims retried', 'n'], ['Mean SD over repeats', 'n'], ['Cells with SD 0', 'n']],
      S.map((s) => `<tr><td>${esc(s.model)}</td><td>${s.script}</td><td class="n">${s.runs}</td><td class="n">${f(s.lat_mean, 0)}</td><td class="n">${f(s.lat_median, 0)}</td><td class="n">${f(s.lat_p95, 0)}</td><td class="n">${f(s.lat_max, 0)}</td><td class="n">${s.retried_dims}</td><td class="n">${f(s.stab_mean_sd)} <span class="badge">n=${s.stab_cells}</span></td><td class="n">${pc(s.stab_zero_share)}</td></tr>`));
  }

  function renderGround() {
    const S = D.scorecard.filter((x) => okS(x.script) && okM(x.model));
    table('t-ground', [['Model'], ['Script'], ['Judge (actual)'], ['Judge coverage', 'n'], ['Grounded', 'n'], ['Hallucinated', 'n'], ['Dropped by code', 'n'], ['Contributor-summary cites', 'n'], ['Code check: cited id in prompt', 'n'], ['Req = 1, no citations', 'n']],
      S.map((s) => `<tr><td>${esc(s.model)}</td><td>${s.script}</td><td class="small">${esc(s.judge_actual)}${String(s.judge_actual).includes('OpenAI') ? ' <span class="chip c-bad">cloud</span>' : ''}</td>
        <td class="n">${s.judge_valid}/${s.runs}</td><td class="n">${pc(s.grounded)}</td><td class="n">${pc(s.halluc)}</td><td class="n">${s.dropped_by_code}</td><td class="n">${s.author_summary_cites}</td>
        <td class="n">${s.cites_found}/${s.cites_total} <span class="muted">(${pc(s.cites_found_share)})</span></td><td class="n">${s.missing_data_ones.requirements}/${s.runs}</td></tr>`));
  }

  function renderRuns() {
    const R = D.explorer.filter((r) => okS(r.script) && okM(r.model) && (!st.failedOnly || r.failed.length) &&
      (!st.q || `${r.bundle} ${r.archetype} ${r.session} ${r.failed.join(' ')} ${r.model}`.toLowerCase().includes(st.q)));
    document.getElementById('exp-count').textContent = `${R.length} of ${D.explorer.length} runs`;
    table('t-runs', [['Script'], ['Model'], ['Bundle'], ['Rep', 'n'], ...DIMS.map((d) => [DL[d], 'n']), ['Overall', 'n'], ['Failed dimensions (cause)'], ['Seconds', 'n'], ['Retries', 'n'], ['Cites in prompt', 'n'], ['Grounded', 'n'], ['Halluc.', 'n'], ['Source']],
      R.map((r) => `<tr><td>${r.script}</td><td>${esc(r.model)}</td><td>${esc(r.bundle)}</td><td class="n">${r.repeat}</td>${r.scores.map((v) => `<td class="n">${v ?? '<span class="c-bad">✕</span>'}</td>`).join('')}<td class="n">${f(r.overall)}</td>
        <td class="small">${esc(r.failed.join('; '))}</td><td class="n">${r.seconds}${r.spiral ? ' <span class="chip c-bad">3x</span>' : ''}</td><td class="n">${r.retries}</td><td class="n">${r.found}/${r.cites}</td><td class="n">${pc(r.grounded)}</td><td class="n">${pc(r.halluc)}</td><td class="mono">${r.session}:${r.line}</td></tr>`));
  }

  const T = D.truncation, O = D.out_of_batch;
  const cav = [
    `Small pilot: 2 real sprints and 5 synthetic fixtures, 3 repeats each. No significance claims; read every number with its n.`,
    `Fixture runs were judged by gpt-4o-mini through the OpenAI API (judges/citation_ground_custom_judge.py lines 199-201), which breaks the local-only constraint. The judge files label every row sprintsight-judge-phi, so the label is wrong for fixtures. Judge calls in the batch window: ${Object.entries(D.judge_calls_in_window).map(([k, v]) => `${k} ${v}`).join(', ')}.`,
    `Both CS203 bundles contain no Jira tickets and no peer evaluations, yet the reference scores requirements and collaboration (G6: 3 and 4, JY: 7 and 6). Error on those two dimensions measures a missing-data policy, not grading skill.`,
    `Every model scored requirements 1 on all 30 CS203 runs, almost always with zero citations.`,
    `The expected order "lone_contributor > struggling" on collaboration is broken by the team-authored gold itself (Theta 1, Gamma 3), so that link cannot be passed while agreeing with the gold.`,
    `Accuracy uses only dimensions scored in every run of a model, so models with failures (gemma, r1-32b, qwen) are compared on fewer dimensions. The coverage badge shows how many.`,
    `Temperature is 0, so near-zero spread across repeats reflects deterministic decoding, not validity.`,
    `${T.shrunk_flag} of ${T.calls} calls tripped the pipeline's "prompt most likely truncated" warning, but no prompt exceeded ${Math.round(T.max_prompt_over_ctx * 100)}% of num_ctx. The warning compares Ollama's token count with a chars/4 estimate that runs about ${Math.round((1 - T.median_reported_over_estimate) * 100)}% high, so these are false positives.`,
    `Most of the pipeline's CS203 "fabricated citation" drops are contributor-summary lines that the prompt shows but the resolver cannot match. The dropped-by-code count overstates fabrication on CS203.`,
    `The code check counts a citation as grounded when its identifier appears verbatim in the prompt. That is looser than the pipeline's resolver and says nothing about whether the claim is true.`,
    `${O.calls_after_batch} calls after the batch (${Object.keys(O.by).join(', ')}, ${O.first} to ${O.last} UTC) left no result files. They are outside this analysis.`,
    `Pearson r is computed across bundles of very different quality, so a high r mostly reflects agreement on which team is strong, not on exact scores.`,
  ];
  document.getElementById('cav').innerHTML = cav.map((c) => `<li>${esc(c)}</li>`).join('');

  function render() { renderHealth(); renderScore(); renderHeat(); renderTraj(); renderLat(); renderGround(); renderRuns(); }
  render();
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(renderLat, 150); });
})();
</script>
"""

page = PAGE.replace("__DATA__", data)
(HERE / "dashboard_page.html").write_text(page, encoding="utf-8")
(HERE / "dashboard.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                                     + page.replace("<style>", "<style>\n:root { padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }", 1)
                                       .replace('<div class="wrap">', '</head><body>\n<div class="wrap">', 1)
                                     + "\n</body></html>\n", encoding="utf-8")
print("dashboard.html", len((HERE / "dashboard.html").read_bytes()), "bytes")
