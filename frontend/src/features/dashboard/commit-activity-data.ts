import type { DashboardCommit } from "@/features/dashboard/types";

export type CommitDayPoint = {
  key: string;
  name: string;
  commits: number;
};

function localDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatDayLabel(key: string): string {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// Keys are local ISO dates, so the same month and day in different years stay separate and the axis is chronological.
export function groupCommitsByDay(commits: Pick<DashboardCommit, "timestamp">[]): CommitDayPoint[] {
  const countsByDay = new Map<string, number>();
  for (const commit of commits) {
    const date = new Date(commit.timestamp);
    if (Number.isNaN(date.getTime())) continue;
    const key = localDateKey(date);
    countsByDay.set(key, (countsByDay.get(key) ?? 0) + 1);
  }
  return Array.from(countsByDay.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, count]) => ({ key, name: formatDayLabel(key), commits: count }));
}

export function describeCommitActivity(days: CommitDayPoint[]): string {
  if (days.length === 0) return "Commit activity: no commits";
  const total = days.reduce((sum, day) => sum + day.commits, 0);
  return `Commit activity: ${total} commits from ${days[0].name} to ${days[days.length - 1].name}.`;
}
