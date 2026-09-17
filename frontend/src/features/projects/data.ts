import type { StudentProject } from "@/features/projects/types";

export const PROJECTS: StudentProject[] = [
  {
    id: "ecommerce-platform",
    name: "E-Commerce Platform",
    teamName: "Team Alpha",
    module: "CS4051 - Software Engineering",
    status: "Active",
    score: 82,
    completion: 75,
    members: ["A", "B", "C", "D"],
    currentSprint: "Sprint 5",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 71, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 76, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Completed", score: 79, completion: 100, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Completed", score: 81, completion: 100, startDate: "2026-02-26", endDate: "2026-03-11" },
      { id: "s5", name: "Sprint 5", status: "On Track", score: 82, completion: 75, startDate: "2026-03-12", endDate: "2026-03-25" },
    ],
  },
  {
    id: "chat-application",
    name: "Chat Application",
    teamName: "Team Beta",
    module: "CS4051 - Software Engineering",
    status: "Active",
    score: 75,
    completion: 60,
    members: ["E", "F", "G"],
    currentSprint: "Sprint 5",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 66, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 69, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Completed", score: 72, completion: 100, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Completed", score: 74, completion: 100, startDate: "2026-02-26", endDate: "2026-03-11" },
      { id: "s5", name: "Sprint 5", status: "On Track", score: 75, completion: 60, startDate: "2026-03-12", endDate: "2026-03-25" },
    ],
  },
  {
    id: "task-manager-pro",
    name: "Task Manager Pro",
    teamName: "Team Gamma",
    module: "CS4051 - Software Engineering",
    status: "Active",
    score: 88,
    completion: 85,
    members: ["H", "I", "J", "K"],
    currentSprint: "Sprint 5",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 77, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 81, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Completed", score: 85, completion: 100, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Completed", score: 87, completion: 100, startDate: "2026-02-26", endDate: "2026-03-11" },
      { id: "s5", name: "Sprint 5", status: "On Track", score: 88, completion: 85, startDate: "2026-03-12", endDate: "2026-03-25" },
    ],
  },
  {
    id: "social-network",
    name: "Social Network",
    teamName: "Team Delta",
    module: "CS3042 - Web Development",
    status: "At Risk",
    score: 69,
    completion: 45,
    members: ["L", "M", "N"],
    currentSprint: "Sprint 4",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 65, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 67, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Needs Attention", score: 70, completion: 70, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Needs Attention", score: 69, completion: 45, startDate: "2026-02-26", endDate: "2026-03-11" },
    ],
  },
  {
    id: "weather-dashboard",
    name: "Weather Dashboard",
    teamName: "Team Epsilon",
    module: "CS3042 - Web Development",
    status: "Active",
    score: 91,
    completion: 90,
    members: ["O", "P", "Q", "R"],
    currentSprint: "Sprint 5",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 79, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 83, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Completed", score: 86, completion: 100, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Completed", score: 89, completion: 100, startDate: "2026-02-26", endDate: "2026-03-11" },
      { id: "s5", name: "Sprint 5", status: "On Track", score: 91, completion: 90, startDate: "2026-03-12", endDate: "2026-03-25" },
    ],
  },
  {
    id: "fitness-tracker",
    name: "Fitness Tracker",
    teamName: "Team Zeta",
    module: "CS3042 - Web Development",
    status: "At Risk",
    score: 64,
    completion: 40,
    members: ["S", "T", "U"],
    currentSprint: "Sprint 4",
    sprints: [
      { id: "s1", name: "Sprint 1", status: "Completed", score: 63, completion: 100, startDate: "2026-01-15", endDate: "2026-01-28" },
      { id: "s2", name: "Sprint 2", status: "Completed", score: 65, completion: 100, startDate: "2026-01-29", endDate: "2026-02-11" },
      { id: "s3", name: "Sprint 3", status: "Needs Attention", score: 66, completion: 65, startDate: "2026-02-12", endDate: "2026-02-25" },
      { id: "s4", name: "Sprint 4", status: "Needs Attention", score: 64, completion: 40, startDate: "2026-02-26", endDate: "2026-03-11" },
    ],
  },
];

export function getProjectById(projectId: string) {
  return PROJECTS.find((project) => project.id === projectId);
}

export function getSprintByProjectAndId(projectId: string, sprintId: string) {
  const project = getProjectById(projectId);
  if (!project) {
    return null;
  }

  const sprint = project.sprints.find((item) => item.id === sprintId);
  if (!sprint) {
    return null;
  }

  return { project, sprint };
}
