import type { CollaborationMetric, MemberCommitMetric, WorkloadSlice } from "@/features/collaboration/types";

const AXIS_CHAR_WIDTH_PX = 6.5;
const AXIS_PADDING_PX = 12;
const MIN_AXIS_WIDTH_PX = 72;
const MAX_AXIS_WIDTH_PX = 200;

// Estimates the width of the member-name axis from the longest label. Names beyond the cap are still truncated by the axis.
export function getCategoryAxisWidth(labels: string[]): number {
  const longest = labels.reduce((max, label) => Math.max(max, label.length), 0);
  const width = Math.ceil(longest * AXIS_CHAR_WIDTH_PX) + AXIS_PADDING_PX;
  return Math.min(MAX_AXIS_WIDTH_PX, Math.max(MIN_AXIS_WIDTH_PX, width));
}

export function describeMemberChart(
  metricLabel: string,
  rows: MemberCommitMetric[],
  metric: CollaborationMetric,
): string {
  if (rows.length === 0) return `${metricLabel} by member: no data`;
  const top = rows.reduce((best, row) => (row[metric] > best[metric] ? row : best), rows[0]);
  return `${metricLabel} by member for ${rows.length} contributors. Highest: ${top.member} with ${top[metric].toLocaleString()}.`;
}

export function describeWorkloadChart(slices: WorkloadSlice[]): string {
  if (slices.length === 0) return "Workload distribution: no Jira ticket data";
  const parts = slices.map((slice) => `${slice.name} ${slice.value}%`);
  return `Workload distribution: ${parts.join(", ")}.`;
}
