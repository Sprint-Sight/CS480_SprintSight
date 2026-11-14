"use client";

import { DIMENSION_LABELS, type OverrideStats } from "@/features/insights/types";
import { useOverrideStats } from "@/features/insights/hooks/use-insights";
import { getErrorMessage } from "@/lib/api/client";

const pct = (value: number | null) => (value == null ? "—" : `${Math.round(value * 100)}%`);
const signed = (value: number | null) =>
  value == null ? "—" : value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);

/**
 * Override statistics. Deliberately not "accuracy": the instructor saw the AI score first, so
 * these numbers say how often and how far scores were changed, nothing about how right the AI was.
 */
export function OverrideStatsView({ stats }: { stats: OverrideStats }) {
  return (
    <section
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
      aria-label="Override statistics"
    >
      <h2 className="text-base font-semibold text-slate-900">How scores were overridden</h2>
      <p className="text-sm text-slate-700">
        {stats.reportsOverridden} of {stats.reports} reports overridden ({pct(stats.overrideRate)}
        ); {stats.reportsWithChanges} with at least one changed score.
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs font-semibold uppercase text-slate-600">
            <tr>
              <th className="px-3 py-2">Dimension</th>
              <th className="px-3 py-2">Saved</th>
              <th className="px-3 py-2">Changed</th>
              <th className="px-3 py-2">Mean adjustment</th>
              <th className="px-3 py-2">Direction</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {stats.byDimension.map((d) => (
              <tr key={d.dimension}>
                <td className="px-3 py-2 font-medium">{DIMENSION_LABELS[d.dimension]}</td>
                <td className="px-3 py-2 tabular-nums">{d.overridesSaved}</td>
                <td className="px-3 py-2 tabular-nums">
                  {d.changed} ({pct(d.changeRate)})
                </td>
                <td className="px-3 py-2 tabular-nums">{signed(d.meanAdjustment)}</td>
                <td className="px-3 py-2">{d.direction ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">{stats.notice}</p>
    </section>
  );
}

export function OverrideStatsPanel() {
  const stats = useOverrideStats();
  if (stats.isLoading)
    return <p className="text-sm text-slate-500">Loading override statistics…</p>;
  if (stats.error || !stats.data)
    return <p className="text-sm text-red-700">{getErrorMessage(stats.error)}</p>;
  return <OverrideStatsView stats={stats.data} />;
}
