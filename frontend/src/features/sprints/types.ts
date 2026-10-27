import type { ProjectSprint, SprintStatus, StudentProject } from "@/features/projects/types";

export type SprintActivity = {
  commits: number;
  tasks: number;
  documents: number;
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
  totalDocuments: number;
}

export type SprintOverviewPayload = {
  project: StudentProject;
  rows: SprintOverviewRow[];
  summary: SprintOverviewSummary;
};
