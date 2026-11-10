"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DashboardCommit } from "@/features/dashboard/types";
import { CHART_GRID_STROKE, CHART_TICK, chartColor } from "@/lib/chart-theme";
import { ChartWithTable, type ChartTableColumn } from "@/components/ui/chart-with-table";
import {
  type CommitDayPoint,
  describeCommitActivity,
  groupCommitsByDay,
} from "@/features/dashboard/commit-activity-data";

const tableColumns: ChartTableColumn<CommitDayPoint>[] = [
  { header: "Date", cell: (day) => day.name },
  { header: "Commits", cell: (day) => day.commits },
];

export function CommitActivityChart({ commits }: { commits: DashboardCommit[] }) {
  const chartData = groupCommitsByDay(commits);
  return (
    <div className="min-w-0 rounded-xl border border-slate-100 bg-white p-4 shadow-sm sm:p-6">
      <h3 className="mb-6 text-lg font-bold text-slate-900">Commit Activity</h3>
      <ChartWithTable
        summary={describeCommitActivity(chartData)}
        rows={chartData}
        columns={tableColumns}
      >
        <div className="h-64 w-full min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              accessibilityLayer
              data={chartData}
              margin={{ top: 5, right: 20, bottom: 5, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_STROKE} />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={CHART_TICK} dy={10} />
              <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={CHART_TICK} />
              <Tooltip
                contentStyle={{
                  borderRadius: "8px",
                  border: "none",
                  boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
                }}
              />
              <Line
                type="monotone"
                dataKey="commits"
                stroke={chartColor("chart-1")}
                strokeWidth={3}
                dot={{ r: 4, fill: chartColor("chart-1"), strokeWidth: 0 }}
                activeDot={{ r: 6, fill: chartColor("chart-highlight"), strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartWithTable>
    </div>
  );
}
