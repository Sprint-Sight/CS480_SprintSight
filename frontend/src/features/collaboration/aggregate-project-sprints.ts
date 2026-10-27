import type {
  IngestionState,
  PersistedGitMetrics,
  PersistedJiraSnapshot,
} from "@/features/ingestion/state";

type ProjectIngestionAggregate = {
  git: PersistedGitMetrics | undefined;
  jira: PersistedJiraSnapshot | undefined;
  documents: number;
};

export function aggregateProjectSprints(
  state: IngestionState,
  projectId: string,
): ProjectIngestionAggregate {
  const gitRuns = Object.values(state.gitBySprint)
    .filter((run) => run.project_id === projectId)
    .sort((left, right) => left.captured_at.localeCompare(right.captured_at));
  const jiraRuns = Object.values(state.jiraBySprint)
    .filter((run) => run.project_id === projectId)
    .sort((left, right) => left.captured_at.localeCompare(right.captured_at));

  const commitsBySha = new Map<string, PersistedGitMetrics["commits"][number]>();
  for (const run of gitRuns) {
    for (const commit of run.commits) {
      commitsBySha.set(commit.sha, commit);
    }
  }

  const latestGitRun = gitRuns.at(-1);
  const git = latestGitRun
    ? {
        ...latestGitRun,
        commit_frequency: gitRuns.reduce((total, run) => total + run.commit_frequency, 0),
        code_churn: gitRuns.reduce((total, run) => total + run.code_churn, 0),
        commits: Array.from(commitsBySha.values()).sort(
          (left, right) => left.timestamp.localeCompare(right.timestamp),
        ),
        pagination: {
          limit: null,
          offset: null,
          total: gitRuns.reduce(
            (total, run) => total + (run.pagination?.total ?? run.commits.length),
            0,
          ),
          has_more: gitRuns.some((run) => run.pagination?.has_more ?? false),
        },
      }
    : undefined;

  const ticketsById = new Map<string, PersistedJiraSnapshot["tickets"][number]>();
  for (const run of jiraRuns) {
    for (const ticket of run.tickets) {
      ticketsById.set(ticket.ticket_id, ticket);
    }
  }

  const latestJiraRun = jiraRuns.at(-1);
  const jira = latestJiraRun
    ? {
        ...latestJiraRun,
        tickets: Array.from(ticketsById.values()),
      }
    : undefined;

  return {
    git,
    jira,
    documents: state.documentCounts[projectId] || 0,
  };
}
