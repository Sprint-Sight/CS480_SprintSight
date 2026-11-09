import type {
  CollaborationDataset,
  HeatmapRow,
  MemberCommitMetric,
  UnmatchedCommit,
  WorkloadSlice,
} from "@/features/collaboration/types";
import type {
  PersistedGitMetrics,
  PersistedJiraSnapshot,
} from "@/features/ingestion/types";

type IngestionAggregate = {
  git: PersistedGitMetrics | undefined;
  jira: PersistedJiraSnapshot | undefined;
};

function displayStudentName(studentId: string, memberNames: Map<string, string>) {
  return memberNames.get(studentId) || `Student ${studentId.slice(0, 8)}`;
}

export function aggregateCollaborationMetrics(
  ingestion: IngestionAggregate,
  memberNames: Map<string, string>,
  projectLabel: string,
): Pick<
  CollaborationDataset,
  "commitsByMember" | "unmatchedCommits" | "workloadDistribution" | "participationHeatmap" | "riskIndicators"
> | null {
  const commits = ingestion.git?.commits || [];
  const tickets = ingestion.jira?.tickets || [];
  if (!ingestion.git && !ingestion.jira) return null;

  const commitMetrics = new Map<string, MemberCommitMetric>();
  const heatmapMetrics = new Map<string, HeatmapRow>();
  const unmatchedCommits: UnmatchedCommit[] = [];
  const timestamps = commits
    .map((commit) => new Date(commit.timestamp).getTime())
    .filter(Number.isFinite);
  const firstTimestamp = timestamps.length ? Math.min(...timestamps) : Date.now();

  for (const commit of commits) {
    const studentId = commit.student_id || null;
    if (!studentId) {
      unmatchedCommits.push({
        sha: commit.sha,
        author: commit.author || "Unknown author",
        timestamp: commit.timestamp,
        linesAdded: commit.lines_added,
        linesDeleted: commit.lines_deleted,
      });
      continue;
    }

    const displayName = displayStudentName(studentId, memberNames);
    const identity = `student:${studentId}`;
    const metric = commitMetrics.get(identity) || {
      id: identity,
      student_id: studentId,
      member: displayName,
      commits: 0,
      linesChanged: 0,
    };
    metric.commits += 1;
    metric.linesChanged += commit.lines_added + commit.lines_deleted;
    commitMetrics.set(identity, metric);

    const heatmapRow = heatmapMetrics.get(identity) || {
      id: identity,
      student_id: studentId,
      member: displayName,
      week1: 0,
      week2: 0,
      week3: 0,
      week4: 0,
    };
    const timestamp = new Date(commit.timestamp).getTime();
    const week = Number.isFinite(timestamp)
      ? Math.min(3, Math.max(0, Math.floor((timestamp - firstTimestamp) / (7 * 24 * 60 * 60 * 1000))))
      : 0;
    const weekKeys = ["week1", "week2", "week3", "week4"] as const;
    heatmapRow[weekKeys[week]] += 1;
    heatmapMetrics.set(identity, heatmapRow);
  }

  const commitsByMember = Array.from(commitMetrics.values()).sort(
    (left, right) => right.commits - left.commits || left.member.localeCompare(right.member),
  );
  const ticketsByIdentity = new Map<string, { student_id: string | null; name: string; value: number }>();
  for (const ticket of tickets) {
    const studentId = ticket.student_id || null;
    const identity = studentId
      ? `student:${studentId}`
      : `unmatched-jira:${ticket.ticket_id}`;
    const name = studentId
      ? displayStudentName(studentId, memberNames)
      : `Unmatched Jira: ${ticket.assignee || "Unassigned"} (${ticket.ticket_id})`;
    const slice = ticketsByIdentity.get(identity) || { student_id: studentId, name, value: 0 };
    slice.value += 1;
    ticketsByIdentity.set(identity, slice);
  }

  const totalTickets = tickets.length || 1;
  const palette = ["hsl(var(--chart-1))", "hsl(var(--chart-2))", "hsl(var(--chart-3))", "hsl(var(--chart-4))", "hsl(var(--chart-5))"];
  const workloadDistribution: WorkloadSlice[] = Array.from(
    ticketsByIdentity.entries(),
    ([id, slice], index) => ({
      id,
      student_id: slice.student_id,
      name: slice.name,
      value: Math.round((slice.value / totalTickets) * 100),
      color: palette[index % palette.length],
    }),
  );
  const participationHeatmap = Array.from(heatmapMetrics.values());
  const totalCommits = commitsByMember.reduce((sum, item) => sum + item.commits, 0);
  const counts = commitsByMember.map((item) => item.commits);
  const balanceScore = counts.length
    ? Math.round((1 - (Math.max(...counts) - Math.min(...counts)) / Math.max(1, totalCommits)) * 100)
    : 0;

  return {
    commitsByMember,
    unmatchedCommits,
    workloadDistribution,
    participationHeatmap,
    riskIndicators: [{
      team: projectLabel.trim() || "—",
      risk: balanceScore >= 70 ? "Low" : balanceScore >= 45 ? "Medium" : "High",
      summary: `${commitsByMember.length} Git contributors across ${totalCommits} commits`,
      balanceScore,
    }],
  };
}
