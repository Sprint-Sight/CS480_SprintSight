import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/types";
import {
  indexIngestionRuns,
  projectIngestionQueryOptions,
  summarizeIngestionRuns,
} from "@/features/ingestion/ingestion-query";
import { ApiError, apiRequest } from "@/lib/api/client";

function gitRun(
  sprintId: string,
  overrides: Partial<PersistedGitMetrics> = {},
): PersistedGitMetrics {
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
    expect(summarizeIngestionRuns([], [])).toEqual({
      hasData: false,
      gitCommits: 0,
      codeChurn: 0,
      jiraTickets: 0,
    });
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

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

describe("projectIngestionQueryOptions", () => {
  const PROJECT = "project-1";
  const COURSE = "course-1";
  const gitUrl = (sprintId: string) =>
    `/repo-ingestion/runs/${PROJECT}/${sprintId}?course_id=${COURSE}`;

  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it("finds a Git run after a gap by using the sprints named in Jira runs", async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path === `/jira-ingestion/runs/${PROJECT}`) {
        return [
          {
            run_id: "jira-run-4",
            project_id: PROJECT,
            sprint_id: "sprint-4",
            processing_status: "completed",
            captured_at: "2026-10-04T10:00:00Z",
          },
        ];
      }
      if (path.endsWith("/cleaned")) return jiraSnapshot("sprint-4", 2);
      if (path === gitUrl("sprint-4")) return gitRun("sprint-4");
      // Nothing was synced for sprint-1..3, so the sprint-1, sprint-2, ... probe stops immediately.
      throw new ApiError("Repo ingestion run not found.", { status: 404 });
    });

    const result = await projectIngestionQueryOptions(PROJECT, COURSE).queryFn();

    const requested = vi.mocked(apiRequest).mock.calls.map(([path]) => path);
    expect(requested).toContain(gitUrl("sprint-1"));
    expect(requested).toContain(gitUrl("sprint-4"));
    expect(result.gitRuns.map((run) => run.sprint_id)).toEqual(["sprint-4"]);
    expect(result.jiraSnapshots.map((snapshot) => snapshot.sprint_id)).toEqual(["sprint-4"]);
    expect(result.errors).toEqual([]);
  });

  it("still loads Git runs when the Jira run list fails", async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path === `/jira-ingestion/runs/${PROJECT}`) {
        throw new ApiError("Jira is unavailable.", { status: 503 });
      }
      if (path === gitUrl("sprint-1")) return gitRun("sprint-1");
      throw new ApiError("Repo ingestion run not found.", { status: 404 });
    });

    const result = await projectIngestionQueryOptions(PROJECT, COURSE).queryFn();

    expect(result.gitRuns.map((run) => run.sprint_id)).toEqual(["sprint-1"]);
    expect(result.jiraSnapshots).toEqual([]);
    expect(result.errors).toEqual(["Jira is unavailable."]);
  });
});
