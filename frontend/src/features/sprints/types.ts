import type { ProjectSprint } from "@/features/projects/types";

export type SprintActivity = {
  commits: number;
  tasks: number;
};

export type SprintOverviewRow = {
  projectId: string;
  projectName: string;
  projectTeam: string;
  sprint: ProjectSprint;
  activity: SprintActivity;
  isCompleted: boolean;
  isOngoing: boolean;
  displayStatus: "Completed" | "In Progress";
};

export type SprintOverviewSummary = {
  totalCommits: number;
  totalTasks: number;
};

export type SprintOverviewPayload = {
  project: { id: string; name: string };
  rows: SprintOverviewRow[];
  summary: SprintOverviewSummary;
};
