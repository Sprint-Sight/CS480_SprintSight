import { clsx } from "clsx";
import type {
  RevealDimension,
  Tile,
  TraceView,
  UnacceptedCitation,
} from "@/features/insights/types";

export function DegradedNotice({ notice }: { notice: string | null }) {
  if (!notice) return null;
  return (
    <p
      role="status"
      className="rounded-md border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900"
    >
      {notice}
    </p>
  );
}

export function RevealComparison({
  dimensions,
  mode = "blind_label",
}: {
  dimensions: RevealDimension[];
  mode?: "blind_label" | "override";
}) {
  const override = mode === "override";
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
          <tr>
            <th className="px-3 py-2">Dimension</th>
            <th className="px-3 py-2">AI (original)</th>
            <th className="px-3 py-2">{override ? "Instructor override" : "You"}</th>
            <th className="px-3 py-2">{override ? "Adjustment" : "Difference"}</th>
            {!override && <th className="px-3 py-2">Within 1 point</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {dimensions.map((d) => (
            <tr key={d.dimension}>
              <td className="px-3 py-2 font-medium">{d.label}</td>
              <td className="px-3 py-2 tabular-nums">
                {d.aiScore ?? "—"}
                {d.overridden && !override && (
                  <span className="ml-1 text-xs text-slate-500">(now {d.aiScoreCurrent})</span>
                )}
              </td>
              <td className="px-3 py-2 tabular-nums" title={d.yourReason ?? undefined}>
                {d.yourScore ?? "—"}
                {override && d.overridden && (
                  <span className="ml-2 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-800">
                    changed
                  </span>
                )}
              </td>
              <td className="px-3 py-2 tabular-nums">
                {d.diff == null ? "—" : d.diff > 0 ? `+${d.diff}` : d.diff}
              </td>
              {!override && (
                <td className="px-3 py-2">
                  {d.within1 == null ? (
                    "—"
                  ) : d.within1 ? (
                    <span className="text-emerald-700">✓ Yes</span>
                  ) : (
                    <span className="text-red-700">✗ No</span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SEVERITY = {
  ok: "border-emerald-200 bg-emerald-50",
  warn: "border-amber-200 bg-amber-50",
  bad: "border-red-200 bg-red-50",
  na: "border-slate-200 bg-slate-50",
};

export function JudgeTiles({ tiles }: { tiles: Tile[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {tiles.map((t) => (
        <div key={t.key} className={clsx("rounded-lg border p-3", SEVERITY[t.severity])}>
          <p className="text-xs font-medium uppercase text-slate-600">{t.label}</p>
          <p className="text-xl font-semibold text-slate-900">{t.value}</p>
          {t.detail && <p className="text-xs text-slate-600">{t.detail}</p>}
        </div>
      ))}
    </div>
  );
}

export function UnacceptedCitationsTable({
  rows,
  truncated,
}: {
  rows: UnacceptedCitation[];
  truncated: boolean;
}) {
  if (rows.length === 0)
    return <p className="text-sm text-slate-600">The judge accepted every citation it checked.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
          <tr>
            <th className="px-3 py-2">Claim</th>
            <th className="px-3 py-2">Verdict</th>
            <th className="px-3 py-2">Severity</th>
            <th className="px-3 py-2">Judge reasoning</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.citationId} className="align-top">
              <td className="px-3 py-2">
                <span className="font-mono text-xs text-slate-500">
                  {r.citationId} · {r.dimension}
                </span>
                <br />
                {r.claim ?? <em className="text-slate-500">claim text unavailable</em>}
              </td>
              <td className="px-3 py-2">{r.verdict.replace(/_/g, " ")}</td>
              <td className="px-3 py-2">{r.severity.replace(/_/g, " ")}</td>
              <td className="px-3 py-2 text-slate-700">{r.reasoning}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="p-2 text-xs text-slate-500">
          Judge output was truncated; some rows may be missing.
        </p>
      )}
    </div>
  );
}

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;

export function TraceTimeline({ trace }: { trace: TraceView }) {
  const total = Math.max(
    trace.durationMs,
    ...trace.spans.map((s) => s.startOffsetMs + s.durationMs),
    1,
  );
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-sm text-slate-600">
        {seconds(trace.durationMs)} total · {trace.llmCallCount} model calls (contents not shown)
      </p>
      <ol className="space-y-1">
        {trace.spans.map((s, i) => (
          <li
            key={`${s.name}-${i}`}
            className="grid grid-cols-[minmax(8rem,14rem)_1fr_4rem] items-center gap-2 text-xs"
          >
            <span className="truncate" title={s.name}>
              {s.parent ? "↳ " : ""}
              {s.name.replace(/_/g, " ")}
            </span>
            <div className="relative h-2 rounded bg-slate-100">
              <div
                className={clsx(
                  "absolute h-2 rounded",
                  s.status === "ERROR" ? "bg-red-400" : "bg-indigo-400",
                )}
                style={{
                  left: `${(s.startOffsetMs / total) * 100}%`,
                  width: `${Math.max((s.durationMs / total) * 100, 0.5)}%`,
                }}
              />
            </div>
            <span className="text-right tabular-nums">{seconds(s.durationMs)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function PromptVersionsList({
  versions,
}: {
  versions: { name: string; version: string }[];
}) {
  if (versions.length === 0)
    return <p className="text-sm text-slate-500">Prompt versions unavailable.</p>;
  return (
    <ul className="grid gap-1 text-sm sm:grid-cols-2">
      {versions.map((v) => (
        <li
          key={v.name}
          className="flex justify-between rounded border border-slate-200 bg-white px-2 py-1"
        >
          <span className="font-mono text-xs">{v.name}</span>
          <span>v{v.version}</span>
        </li>
      ))}
    </ul>
  );
}
