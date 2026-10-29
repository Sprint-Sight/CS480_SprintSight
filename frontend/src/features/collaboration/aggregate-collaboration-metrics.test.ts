import { describe, expect, it } from "vitest";

import { aggregateCollaborationMetrics } from "@/features/collaboration/aggregate-collaboration-metrics";
import type { PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/state";

const git: PersistedGitMetrics = {
  course_id: "course-1",
  project_id: "project-1",
  sprint_id: "sprint-1",
  head_sha: null,
  captured_at: "2026-10-01T10:00:00Z",
  commit_frequency: 2,
  code_churn: 7,
  pr_turnaround_hours: null,
  assigned_story_points: null,
  completion_percent: null,
  commits: [
    {
      sha: "sha-1",
      author: "Git Display Name",
      student_id: "student-1",
      message: "",
      timestamp: "2026-10-01T09:00:00Z",
      lines_added: 4,
      lines_deleted: 1,
      files_changed: [],
    },
    {
      sha: "sha-2",
      author: "Different Git Name",
      student_id: "student-1",
      message: "",
      timestamp: "2026-10-02T09:00:00Z",
      lines_added: 2,
      lines_deleted: 0,
      files_changed: [],
    },
  ],
};

const jira: PersistedJiraSnapshot = {
  normalization_version: "jira-ticket-v1",
  source: "jira",
  jira_project_key: "DEMO",
  course_id: "course-1",
  project_id: "project-1",
  sprint_id: "sprint-1",
  captured_at: "2026-10-01T10:00:00Z",
  tickets: [
    {
      ticket_id: "DEMO-1",
      summary: "First ticket",
      assignee: "Jira Display Name",
      student_id: "student-1",
      status: "Done",
      issue_type: "Story",
      story_points: 3,
      sprint_id: "sprint-1",
    },
  ],
};

describe("aggregateCollaborationMetrics", () => {
  it("joins Git and Jira contributors by student ID, not display name", () => {
    const result = aggregateCollaborationMetrics(
      { git, jira },
      new Map([["student-1", "SprintSight Student"]]),
    );

    expect(result?.commitsByMember).toEqual([
      {
        id: "student:student-1",
        student_id: "student-1",
        member: "SprintSight Student",
        commits: 2,
        linesChanged: 7,
      },
    ]);
    expect(result?.workloadDistribution[0]).toMatchObject({
      id: "student:student-1",
      student_id: "student-1",
      name: "SprintSight Student",
      value: 100,
    });
  });

  it("keeps unmatched Git commits and Jira tickets visible as distinct entries", () => {
    const unmatchedGit: PersistedGitMetrics = {
      ...git,
      commits: git.commits.map((commit) => ({ ...commit, student_id: null })),
    };
    const unmatchedJira: PersistedJiraSnapshot = {
      ...jira,
      tickets: [
        { ...jira.tickets[0], student_id: null },
        { ...jira.tickets[0], ticket_id: "DEMO-2", student_id: null },
      ],
    };
    const result = aggregateCollaborationMetrics(
      { git: unmatchedGit, jira: unmatchedJira },
      new Map(),
    );

    expect(result?.commitsByMember).toHaveLength(2);
    expect(result?.commitsByMember.every((metric) => metric.student_id === null)).toBe(true);
    expect(result?.commitsByMember.every((metric) => metric.member.startsWith("Unmatched Git:"))).toBe(true);
    expect(result?.workloadDistribution).toHaveLength(2);
    expect(result?.workloadDistribution.every((slice) => slice.student_id === null)).toBe(true);
    expect(result?.workloadDistribution.every((slice) => slice.name.startsWith("Unmatched Jira:"))).toBe(true);
  });

  it("keeps contributors with identical display names separate when their IDs differ", () => {
    const twoMembers: PersistedGitMetrics = {
      ...git,
      commits: git.commits.map((commit, index) => ({
        ...commit,
        student_id: index === 0 ? "student-1" : "student-2",
      })),
    };
    const result = aggregateCollaborationMetrics(
      { git: twoMembers, jira: undefined },
      new Map([
        ["student-1", "Same Name"],
        ["student-2", "Same Name"],
      ]),
    );

    expect(result?.commitsByMember.map((metric) => metric.id)).toEqual([
      "student:student-1",
      "student:student-2",
    ]);
  });
});
