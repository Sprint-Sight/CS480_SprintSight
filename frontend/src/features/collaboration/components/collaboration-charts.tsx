"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_TICK } from "@/lib/chart-theme";
import { ChartWithTable, type ChartTableColumn } from "@/components/ui/chart-with-table";
import {
  describeMemberChart,
  describeWorkloadChart,
  getCategoryAxisWidth,
} from "@/features/collaboration/chart-layout";
import type {
  CollaborationMetric,
  MemberCommitMetric,
  WorkloadSlice,
} from "@/features/collaboration/types";

type Props = {
  commitsByMember: MemberCommitMetric[];
  workloadDistribution: WorkloadSlice[];
  comparisonMetric: CollaborationMetric;
  onComparisonMetricChange: (metric: CollaborationMetric) => void;
};

const comparisonOptions: Array<{ value: CollaborationMetric; label: string }> = [
  { value: "commits", label: "Commits" },
  { value: "linesChanged", label: "Lines changed" },
];

const DEFAULT_MEMBER_LIMIT = 10;

export function CollaborationCharts({
  commitsByMember,
  workloadDistribution,
  comparisonMetric,
  onComparisonMetricChange,
}: Props) {
  const [showAllMembers, setShowAllMembers] = useState(false);
  const metricLabel = comparisonMetric === "commits" ? "Commits" : "Lines changed";
  const sortedMembers = [...commitsByMember].sort(
    (left, right) => right[comparisonMetric] - left[comparisonMetric],
  );
  const chartData = showAllMembers ? sortedMembers : sortedMembers.slice(0, DEFAULT_MEMBER_LIMIT);
  const chartHeight = Math.max(220, chartData.length * 38);
  const axisWidth = getCategoryAxisWidth(chartData.map((row) => row.member));
  const memberColumns: ChartTableColumn<MemberCommitMetric>[] = [
    { header: "Member", cell: (row) => row.member },
    { header: metricLabel, cell: (row) => row[comparisonMetric].toLocaleString() },
  ];
  const workloadColumns: ChartTableColumn<WorkloadSlice>[] = [
    { header: "Member", cell: (slice) => slice.name },
    { header: "Share", cell: (slice) => `${slice.value}%` },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-blue-950">{metricLabel} by Member</h2>
            <p className="mt-1 text-xs text-slate-500">
              Showing {chartData.length} of {sortedMembers.length} identified contributors
            </p>
          </div>
          <div
            className="inline-flex rounded-lg border border-slate-200 p-1"
            aria-label="Contribution comparison metric"
          >
            {comparisonOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={comparisonMetric === option.value}
                onClick={() => onComparisonMetricChange(option.value)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  comparisonMetric === option.value
                    ? "bg-blue-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {sortedMembers.length > 0 ? (
          <div className="mt-3 max-h-[440px] overflow-y-auto">
            <ChartWithTable
              summary={describeMemberChart(metricLabel, chartData, comparisonMetric)}
              rows={chartData}
              columns={memberColumns}
            >
              <div style={{ height: chartHeight }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    accessibilityLayer
                    data={chartData}
                    layout="vertical"
                    margin={{ top: 4, right: 20, bottom: 4, left: 4 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      horizontal={false}
                      stroke="hsl(var(--border))"
                    />
                    <XAxis type="number" axisLine={false} tickLine={false} tick={CHART_TICK} />
                    <YAxis
                      type="category"
                      dataKey="member"
                      width={axisWidth}
                      axisLine={false}
                      tickLine={false}
                      tick={CHART_TICK}
                    />
                    <Tooltip formatter={(value: number) => [value.toLocaleString(), metricLabel]} />
                    <Bar
                      dataKey={comparisonMetric}
                      name={metricLabel}
                      barSize={20}
                      radius={[0, 6, 6, 0]}
                      fill="hsl(var(--chart-bar))"
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartWithTable>
          </div>
        ) : (
          <div
            className="mt-3 flex h-[220px] items-center justify-center rounded-lg bg-slate-50 px-4 text-center text-sm text-slate-500"
            role="status"
          >
            No Git commits have been matched to project members yet.
          </div>
        )}
        {sortedMembers.length > DEFAULT_MEMBER_LIMIT && (
          <button
            type="button"
            className="mt-3 text-xs font-semibold text-blue-800 hover:text-blue-950"
            onClick={() => setShowAllMembers((showingAll) => !showingAll)}
          >
            {showAllMembers
              ? `Show top ${DEFAULT_MEMBER_LIMIT}`
              : `Show all ${sortedMembers.length} contributors`}
          </button>
        )}
        {sortedMembers.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            Each bar combines all captured commits for that student.
          </p>
        )}
        {comparisonMetric === "linesChanged" && (
          <p className="mt-2 text-xs text-slate-500">
            Lines changed includes lines added and deleted.
          </p>
        )}
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-blue-950">Workload Distribution</h2>
        <div className="mt-3">
          {workloadDistribution.length > 0 ? (
            <ChartWithTable
              summary={describeWorkloadChart(workloadDistribution)}
              rows={workloadDistribution}
              columns={workloadColumns}
            >
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart accessibilityLayer>
                    <Pie
                      data={workloadDistribution}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={48}
                      outerRadius={84}
                      paddingAngle={2}
                    >
                      {workloadDistribution.map((slice) => (
                        <Cell key={slice.id} fill={slice.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => `${value}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </ChartWithTable>
          ) : (
            <div
              className="flex h-[240px] items-center justify-center rounded-lg bg-slate-50 px-4 text-center text-sm text-slate-500"
              role="status"
            >
              No Jira ticket data is available for this project yet. Load a processed Jira snapshot
              to see workload distribution.
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-slate-600">
          {workloadDistribution.map((slice) => (
            <span key={slice.id} className="inline-flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: slice.color }}
                aria-hidden="true"
              />
              {slice.name} ({slice.value}%)
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
