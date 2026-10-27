import { describe, expect, it } from "vitest";
import type { IngestionState } from "@/features/ingestion/state";
import { aggregateProjectSprints } from "@/features/collaboration/aggregate-project-sprints";

const state: IngestionState = {
  selectedProjectId: "project-1",
  gitBySprint: {
    "project-1:sprint-1": {
      course_id: "course-1",
      project_id: "project-1",
      sprint_id: "sprint-1",
      head_sha: "head-1",
      captured_at: "2026-10-01T10:00:00Z",
      commit_frequency: 2,
      code_churn: 15,
      pr_turnaround_hours: 3,
      assigned_story_points: 5,
      completion_percent: 50,
      commits: [
        {
          sha: "shared-sha",
          author: "Student One",
          message: "Earlier version",
          timestamp: "2026-10-01T09:00:00Z",
          lines_added: 5,
          lines_deleted: 1,
          files_changed: [],
        },
        {
          sha: "sprint-1-sha",
          author: "Student Two",
          message: "First sprint work",
          timestamp: "2026-10-01T10:00:00Z",
          lines_added: 2,
          lines_deleted: 0,
          files_changed: [],
        },
      ],
      pagination: { limit: null, offset: null, total: 2, has_more: false },
    },
    "project-1:sprint-2": {
      course_id: "course-1",
      project_id: "project-1",
      sprint_id: "sprint-2",
      head_sha: "head-2",
      captured_at: "2026-10-08T10:00:00Z",
      commit_frequency: 2,
      code_churn: 20,
      pr_turnaround_hours: 4,
      assigned_story_points: 8,
      completion_percent: 80,
      commits: [
        {
          sha: "shared-sha",
          author: "Student One",
          message: "Latest version",
          timestamp: "2026-10-08T09:00:00Z",
          lines_added: 8,
          lines_deleted: 2,
          files_changed: [],
        },
        {
          sha: "sprint-2-sha",
          author: "Student Two",
          message: "Second sprint work",
          timestamp: "2026-10-08T10:00:00Z",
          lines_added: 3,
          lines_deleted: 1,
          files_changed: [],
        },
      ],
      pagination: { limit: null, offset: null, total: 2, has_more: false },
    },
  },
  jiraBySprint: {
    "project-1:sprint-1": {
      normalization_version: "v1",
      source: "jira",
      jira_project_key: "DEMO",
      course_id: "course-1",
      project_id: "project-1",
      sprint_id: "sprint-1",
      captured_at: "2026-10-01T10:00:00Z",
      tickets: [
        {
          ticket_id: "DEMO-1",
          summary: "Earlier summary",
          assignee: "Student One",
          status: "In Progress",
          issue_type: "Story",
          story_points: 3,
          sprint_id: "sprint-1",
        },
      ],
    },
    "project-1:sprint-2": {
      normalization_version: "v1",
      source: "jira",
      jira_project_key: "DEMO",
      course_id: "course-1",
      project_id: "project-1",
      sprint_id: "sprint-2",
      captured_at: "2026-10-08T10:00:00Z",
      tickets: [
        {
          ticket_id: "DEMO-1",
          summary: "Latest summary",
          assignee: "Student One",
          status: "Done",
          issue_type: "Story",
          story_points: 3,
          sprint_id: "sprint-2",
        },
        {
          ticket_id: "DEMO-2",
          summary: "Another ticket",
          assignee: "Student Two",
          status: "To Do",
          issue_type: "Task",
          story_points: 2,
          sprint_id: "sprint-2",
        },
      ],
    },
  },
  documentCounts: { "project-1": 4 },
};

describe("aggregateProjectSprints", () => {
  it("combines a project's sprint data and de-duplicates repeated commits and Jira tickets", () => {
    const result = aggregateProjectSprints(state, "project-1");

    expect(result.git?.sprint_id).toBe("sprint-2");
    expect(result.git?.commits.map((commit) => commit.sha)).toEqual([
      "sprint-1-sha",
      "shared-sha",
      "sprint-2-sha",
    ]);
    expect(result.git?.commits[1].message).toBe("Latest version");
    expect(result.git?.code_churn).toBe(35);
    expect(result.git?.pagination?.total).toBe(4);
    expect(result.jira?.tickets.map((ticket) => ticket.ticket_id)).toEqual([
      "DEMO-1",
      "DEMO-2",
    ]);
    expect(result.jira?.tickets[0].summary).toBe("Latest summary");
    expect(result.documents).toBe(4);
  });

  it("returns empty data when the project has no captured sprint data", () => {
    expect(aggregateProjectSprints(state, "other-project")).toEqual({
      git: undefined,
      jira: undefined,
      documents: 0,
    });
  });
});
