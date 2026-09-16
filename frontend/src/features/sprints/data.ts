import { PROJECTS } from "@/features/projects/data";
import type { ProjectSprint, StudentProject } from "@/features/projects/types";

import type { SprintActivity, SprintOverviewPayload, SprintOverviewRow } from "@/features/sprints/types";

const ACTIVITY_BY_PROJECT: Record<string, Record<string, SprintActivity>> = {
  "ecommerce-platform": {
    s1: { commits: 142, tasks: 28, documents: 8 },
    s2: { commits: 168, tasks: 32, documents: 12 },
    s3: { commits: 195, tasks: 35, documents: 10 },
    s4: { commits: 210, tasks: 38, documents: 14 },
    s5: { commits: 87, tasks: 15, documents: 5 },
  },
  "chat-application": {
    s1: { commits: 98, tasks: 21, documents: 6 },
    s2: { commits: 132, tasks: 27, documents: 9 },
    s3: { commits: 151, tasks: 30, documents: 8 },
    s4: { commits: 146, tasks: 31, documents: 10 },
    s5: { commits: 76, tasks: 14, documents: 4 },
  },
  "task-manager-pro": {
    s1: { commits: 121, tasks: 25, documents: 9 },
    s2: { commits: 144, tasks: 29, documents: 10 },
    s3: { commits: 176, tasks: 34, documents: 12 },
    s4: { commits: 203, tasks: 37, documents: 13 },
    s5: { commits: 109, tasks: 19, documents: 7 },
  },
  "social-network": {
    s1: { commits: 88, tasks: 19, documents: 5 },
    s2: { commits: 105, tasks: 23, documents: 6 },
    s3: { commits: 94, tasks: 20, documents: 4 },
    s4: { commits: 73, tasks: 13, documents: 3 },
  },
  "weather-dashboard": {
    s1: { commits: 136, tasks: 26, documents: 9 },
    s2: { commits: 158, tasks: 30, documents: 11 },
    s3: { commits: 172, tasks: 33, documents: 12 },
    s4: { commits: 181, tasks: 35, documents: 13 },
    s5: { commits: 118, tasks: 22, documents: 8 },
  },
  "fitness-tracker": {
    s1: { commits: 74, tasks: 16, documents: 4 },
    s2: { commits: 83, tasks: 18, documents: 5 },
    s3: { commits: 79, tasks: 17, documents: 4 },
    s4: { commits: 68, tasks: 12, documents: 2 },
  },
};

function fallbackActivity(sprint: ProjectSprint, index: number): SprintActivity {
  const base = 60 + index * 15;
  return {
    commits: base + Math.round(sprint.completion * 0.6),
    tasks: Math.max(6, Math.round(base / 5)),
    documents: Math.max(1, Math.round(base / 18)),
  };
}

function getActivity(projectId: string, sprint: ProjectSprint, index: number): SprintActivity {
  const byProject = ACTIVITY_BY_PROJECT[projectId];
  if (!byProject) {
    return fallbackActivity(sprint, index);
  }

  return byProject[sprint.id] ?? fallbackActivity(sprint, index);
}

function toOverviewRows(project: StudentProject): SprintOverviewRow[] {
  return project.sprints
    .filter((sprint) => sprint.status === "Completed" || sprint.status === "On Track" || sprint.status === "Needs Attention")
    .map((sprint, index) => {
      const isCompleted = sprint.status === "Completed";
      return {
        projectId: project.id,
        projectName: project.name,
        projectTeam: project.teamName,
        sprint,
        activity: getActivity(project.id, sprint, index),
        isCompleted,
        isOngoing: !isCompleted,
        displayStatus: isCompleted ? "Completed" : "In Progress",
      };
    });
}

function summarize(rows: SprintOverviewRow[]) {
  const totalCommits = rows.reduce((sum, row) => sum + row.activity.commits, 0);
  const totalTasks = rows.reduce((sum, row) => sum + row.activity.tasks, 0);
  const totalDocuments = rows.reduce((sum, row) => sum + row.activity.documents, 0);
  const averageScore = rows.length === 0 ? 0 : Number((rows.reduce((sum, row) => sum + row.sprint.score, 0) / rows.length).toFixed(1));

  return { totalCommits, totalTasks, totalDocuments, averageScore };
}

export function getProjectsForSprintOverview() {
  return PROJECTS.map((project) => ({
    id: project.id,
    label: `${project.name} (${project.teamName})`,
  }));
}

export function getSprintOverviewPayload(projectId: string): SprintOverviewPayload | null {
  const project = PROJECTS.find((item) => item.id === projectId);
  if (!project) {
    return null;
  }

  const rows = toOverviewRows(project);
  return {
    project,
    rows,
    summary: summarize(rows),
  };
}
