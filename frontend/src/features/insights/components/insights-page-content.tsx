"use client";

import { useState } from "react";
import { CourseCards } from "@/features/insights/components/course-cards";
import { RunFiltersBar } from "@/features/insights/components/run-filters";
import { OverrideStatsView } from "@/features/insights/components/override-stats-panel";
import { RunsPagination } from "@/features/insights/components/runs-pagination";
import { RunsTable } from "@/features/insights/components/runs-table";
import {
  useInsightsConfig,
  useMyCourses,
  useOverrideStats,
  useRuns,
} from "@/features/insights/hooks/use-insights";
import type { RunFilters } from "@/features/insights/types";
import { getErrorMessage } from "@/lib/api/client";

export function InsightsPageContent() {
  const [filters, setFilters] = useState<RunFilters>({ labelStatus: "all", page: 1, pageSize: 25 });
  const config = useInsightsConfig();
  const mode = config.data?.mode ?? "blind_label";
  const override = mode === "override_gate";
  const courses = useMyCourses();
  const runs = useRuns(filters);
  const overrideStats = useOverrideStats(override);
  const pages = runs.data ? Math.max(1, Math.ceil(runs.data.total / filters.pageSize)) : 1;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">AI grading insights</h1>
        <p className="text-sm text-slate-600">
          {override
            ? "Review the AI's scores and override them on the Assessment Report page. The judge checks, flagged citations and trace for a report unlock once you have saved your override."
            : "Label runs blind, then compare with the AI and its judge. AI scores stay hidden until you label all six dimensions."}
        </p>
      </header>
      {courses.data && (
        <CourseCards
          courses={courses.data}
          selectedId={filters.courseId}
          onSelect={(courseId) => setFilters({ ...filters, courseId, page: 1 })}
          mode={mode}
        />
      )}
      {override &&
        (overrideStats.isLoading ? (
          <p className="text-sm text-slate-500">Loading override statistics…</p>
        ) : overrideStats.error || !overrideStats.data ? (
          <p className="text-sm text-red-700">{getErrorMessage(overrideStats.error)}</p>
        ) : (
          <OverrideStatsView stats={overrideStats.data} />
        ))}
      <RunFiltersBar
        filters={filters}
        facets={runs.data?.facets}
        onChange={setFilters}
        mode={mode}
      />
      {runs.isLoading && <p className="text-sm text-slate-500">Loading runs…</p>}
      {runs.error && <p className="text-sm text-red-700">{getErrorMessage(runs.error)}</p>}
      {runs.data && <RunsTable items={runs.data.items} mode={mode} />}
      {runs.data && (
        <RunsPagination
          page={filters.page}
          pages={pages}
          onPageChange={(page) => setFilters({ ...filters, page })}
        />
      )}
    </div>
  );
}
