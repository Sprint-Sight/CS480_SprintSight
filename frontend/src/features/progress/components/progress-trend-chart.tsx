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
import { ChartWithTable, type ChartTableColumn } from "@/components/ui/chart-with-table";
import type { ProgressDataset } from "@/features/progress/types";
import { CHART_GRID_STROKE, CHART_TICK, chartColor } from "@/lib/chart-theme";

const trendLegend = [
  { key: "requirements", label: "Requirements", color: chartColor("series-1") },
  { key: "codeQuality", label: "Code Quality", color: chartColor("series-2") },
  { key: "testing", label: "Testing", color: chartColor("series-3") },
  { key: "documentation", label: "Documentation", color: chartColor("series-4") },
  { key: "collaboration", label: "Collaboration", color: chartColor("series-5") },
] as const;
type TrendRow = ProgressDataset["categoryTrend"][number];

const trendColumns: ChartTableColumn<TrendRow>[] = [
  { header: "Sprint", cell: (row) => row.sprint },
  ...trendLegend.map((line) => ({ header: line.label, cell: (row: TrendRow) => row[line.key] })),
];

export function ProgressTrendChart({ data }: { data: ProgressDataset["categoryTrend"] }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xl font-semibold text-blue-950">Category Trends Over Sprints</h2>
      <div className="mt-3">
        <ChartWithTable
          summary={`Line chart of ${trendLegend.length} category scores across ${data.length} sprints.`}
          rows={data}
          columns={trendColumns}
        >
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart accessibilityLayer data={data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_STROKE} />
                <XAxis dataKey="sprint" axisLine={false} tickLine={false} tick={CHART_TICK} />
                <YAxis domain={[40, 100]} axisLine={false} tickLine={false} tick={CHART_TICK} />
                <Tooltip />
                {trendLegend.map((line) => (
                  <Line
                    key={line.key}
                    type="monotone"
                    dataKey={line.key}
                    name={line.label}
                    stroke={line.color}
                    strokeWidth={2}
                    dot={{ r: 3, fill: chartColor("background"), strokeWidth: 2 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartWithTable>
      </div>
    </section>
  );
}
