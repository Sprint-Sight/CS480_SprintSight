"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type JiraBurndownResponse = {
  sprint_id: string | null;
  total_story_points: number;
  total_tickets: number;
  start_date: string | null;
  end_date: string | null;
  daily_points: Array<{
    date: string;
    remaining_points: number;
    completed_tickets: number;
    completed_points: number;
  }>;
  ideal_line: Array<{ date: string; remaining_points: number }>;
};

export type JiraBurndownChartPoint = {
  date: string;
  actual_remaining: number | null;
  ideal_remaining: number | null;
};

export function buildBurndownChartData(
  burndown: JiraBurndownResponse,
): JiraBurndownChartPoint[] {
  const actualByDate = new Map(
    burndown.daily_points.map((point) => [point.date, point.remaining_points]),
  );
  const idealByDate = new Map(
    burndown.ideal_line.map((point) => [point.date, point.remaining_points]),
  );
  const dates = new Set([...actualByDate.keys(), ...idealByDate.keys()]);

  return [...dates]
    .sort((left, right) => left.localeCompare(right))
    .map((date) => ({
      date,
      actual_remaining: actualByDate.get(date) ?? null,
      ideal_remaining: idealByDate.get(date) ?? null,
    }));
}

type JiraBurndownChartProps = {
  burndown: JiraBurndownResponse;
};

export function JiraBurndownChart({ burndown }: JiraBurndownChartProps) {
  const data = buildBurndownChartData(burndown);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-4" aria-label="Sprint burndown">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">
          {burndown.sprint_id || "Sprint"} burndown
        </h3>
        <p className="text-sm text-slate-500">
          {burndown.start_date || "Start date unavailable"} to {burndown.end_date || "End date unavailable"}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Committed story points</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{burndown.total_story_points}</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Sprint issues</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{burndown.total_tickets}</p>
        </div>
        <div className="col-span-2 rounded-lg bg-slate-50 p-3 md:col-span-1">
          <p className="text-xs text-slate-500">Latest remaining points</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">
            {burndown.daily_points.at(-1)?.remaining_points ?? "—"}
          </p>
        </div>
      </div>

      {data.length > 0 ? (
        <div className="h-72 w-full" role="img" aria-label="Chart comparing actual and ideal remaining story points by day">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
              <YAxis allowDecimals={false} width={36} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="actual_remaining"
                name="Actual remaining"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="ideal_remaining"
                name="Ideal remaining"
                stroke="#64748b"
                strokeDasharray="5 5"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-sm text-slate-500">No daily burndown points are available for this sprint.</p>
      )}
      <p className="text-xs text-slate-500">
        Actual remaining points are reconstructed from Jira status and story-point history.
      </p>
    </section>
  );
}
