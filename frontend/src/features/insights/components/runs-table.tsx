import Link from "next/link";
import { CitationChip, HiddenValue, JudgeChip } from "@/features/insights/components/chips";
import type { InsightsMode, RunItem } from "@/features/insights/types";

const HEADERS = ["Team", "Course · Sprint", "Model", "AI score", "Citation check", "Judge"];

export const UNLOCKS_AFTER_OVERRIDE = "Unlocks after override";

export function RunsTable({
  items,
  mode = "blind_label",
}: {
  items: RunItem[];
  mode?: InsightsMode;
}) {
  const override = mode === "override_gate";
  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500">
        No grading runs match these filters.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            {[...HEADERS, override ? "Overridden" : "Your labels"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2">
                {h}
              </th>
            ))}
            <th scope="col" className="px-3 py-2">
              <span className="sr-only">Action</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((run) => (
            <tr key={run.reportId}>
              <td className="px-3 py-2 font-medium text-slate-900">{run.teamName}</td>
              <td className="px-3 py-2 text-slate-700">
                {run.courseCode} {run.section} · {run.sprintId}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-slate-700">{run.modelName}</td>
              <td className="px-3 py-2">
                {run.aiScoreHidden ? <HiddenValue /> : `${run.aiScore?.toFixed(1) ?? "—"} / 10`}
              </td>
              <td className="px-3 py-2">
                {override && !run.insightsUnlocked ? (
                  <span className="text-xs italic text-slate-500">{UNLOCKS_AFTER_OVERRIDE}</span>
                ) : (
                  <CitationChip check={run.citationCheck} hidden={!override && run.aiScoreHidden} />
                )}
              </td>
              <td className="px-3 py-2">
                <JudgeChip status={run.judgeStatus} />
              </td>
              <td className="px-3 py-2 tabular-nums">
                {override ? (run.overridden ? "✓" : "—") : `${run.labelsDone} of 6`}
              </td>
              <td className="px-3 py-2 text-right">
                {override && !run.insightsUnlocked ? (
                  <Link
                    href="/assessment-report"
                    className="font-medium text-indigo-600 hover:underline"
                  >
                    Override to unlock
                  </Link>
                ) : (
                  <Link
                    href={`/insights/reports/${run.reportId}`}
                    className="font-medium text-indigo-600 hover:underline"
                  >
                    {override || run.labelsDone >= 6 ? "View insights" : "Label"}
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
