import { describe, expect, it } from "vitest";
import type { PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/types";
import { indexIngestionRuns, summarizeIngestionRuns } from "@/features/ingestion/ingestion-query";

function gitRun(sprintId: string, overrides: Partial<PersistedGitMetrics> = {}): PersistedGitMetrics {
  return {
    course_id: "course-1",
    project_id: "project-1",
    sprint_id: sprintId,
    head_sha: "head",
    captured_at: "2026-10-01T10:00:00Z",
    commit_frequency: 1,
    code_churn: 10,
    pr_turnaround_hours: 0,
    assigned_story_points: 0,
    completion_percent: 0,
    commits: [],
    pagination: { limit: null, offset: null, total: 2, has_more: false },
    ...overrides,
  } as PersistedGitMetrics;
}

function jiraSnapshot(sprintId: string, ticketCount: number): PersistedJiraSnapshot {
  return {
    normalization_version: "v1",
    source: "jira",
    jira_project_key: "DEMO",
    course_id: "course-1",
    project_id: "project-1",
    sprint_id: sprintId,
    captured_at: "2026-10-01T10:00:00Z",
    tickets: Array.from({ length: ticketCount }, (_, index) => ({
      ticket_id: `DEMO-${index}`,
      summary: "s",
      assignee: "a",
      student_id: "a",
      status: "To Do",
      issue_type: "Task",
      story_points: 1,
      sprint_id: sprintId,
    })),
  } as PersistedJiraSnapshot;
}

describe("summarizeIngestionRuns", () => {
  it("reports no data when no runs are loaded", () => {
    expect(summarizeIngestionRuns([], [])).toEqual({ hasData: false, gitCommits: 0, codeChurn: 0, jiraTickets: 0 });
  });

  it("sums commits, churn, and tickets across runs", () => {
    const totals = summarizeIngestionRuns(
      [gitRun("sprint-1"), gitRun("sprint-2", { code_churn: 5 })],
      [jiraSnapshot("sprint-1", 3), jiraSnapshot("sprint-2", 1)],
    );

    expect(totals).toEqual({ hasData: true, gitCommits: 4, codeChurn: 15, jiraTickets: 4 });
  });
});

describe("indexIngestionRuns", () => {
  it("keys runs by project and sprint", () => {
    const index = indexIngestionRuns({
      gitRuns: [gitRun("sprint-1")],
      jiraSnapshots: [jiraSnapshot("sprint-2", 1)],
    });

    expect(Object.keys(index.gitBySprint)).toEqual(["project-1:sprint-1"]);
    expect(Object.keys(index.jiraBySprint)).toEqual(["project-1:sprint-2"]);
  });

  it("returns empty maps when there is no result", () => {
    expect(indexIngestionRuns(undefined)).toEqual({ gitBySprint: {}, jiraBySprint: {} });
  });
});
