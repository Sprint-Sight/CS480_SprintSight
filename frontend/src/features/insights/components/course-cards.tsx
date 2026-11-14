import { clsx } from "clsx";
import type { InsightsCourse, InsightsMode } from "@/features/insights/types";

type Props = {
  courses: InsightsCourse[];
  selectedId?: string;
  onSelect: (courseId?: string) => void;
  mode?: InsightsMode;
};

export function CourseCards({ courses, selectedId, onSelect, mode = "blind_label" }: Props) {
  if (courses.length === 0)
    return <p className="text-sm text-slate-500">You are not assigned to any courses yet.</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {courses.map((c) => (
        <button
          key={c.courseId}
          type="button"
          aria-pressed={selectedId === c.courseId}
          onClick={() => onSelect(selectedId === c.courseId ? undefined : c.courseId)}
          className={clsx(
            "rounded-lg border bg-white p-4 text-left shadow-sm transition hover:border-indigo-300",
            selectedId === c.courseId
              ? "border-indigo-500 ring-1 ring-indigo-500"
              : "border-slate-200",
          )}
        >
          <p className="text-sm font-semibold text-slate-900">
            {c.code} {c.section}
          </p>
          <p className="truncate text-xs text-slate-500">
            {c.name} · {c.term} {c.year}
          </p>
          <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <div>
              <dt className="text-slate-500">Reports</dt>
              <dd className="text-base font-semibold">{c.reports}</dd>
            </div>
            <div>
              <dt className="text-slate-500">
                {mode === "override_gate" ? "Overridden" : "Labelled by you"}
              </dt>
              <dd className="text-base font-semibold">
                {mode === "override_gate" ? c.overridden : c.labelledByYou}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Judge pending</dt>
              <dd className="text-base font-semibold">{c.judgePending}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-slate-500">
            Last evaluation:{" "}
            {c.lastEvaluationAt ? new Date(c.lastEvaluationAt).toLocaleString() : "none yet"}
          </p>
        </button>
      ))}
    </div>
  );
}
