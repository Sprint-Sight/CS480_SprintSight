export type ProjectStatus = "Active" | "At Risk" | "Completed";

export type SprintStatus = "On Track" | "Needs Attention" | "Completed";

export type ProjectSprint = {
  id: string;
  name: string;
  status: SprintStatus;
  score: number;
  completion: number;
  startDate: string;
  endDate: string;
};

export type StudentProject = {
  id: string;
  name: string;
  teamName: string;
  module: string;
  status: ProjectStatus;
  score: number;
  completion: number;
  members: string[];
  currentSprint: string;
  sprints: ProjectSprint[];
};
