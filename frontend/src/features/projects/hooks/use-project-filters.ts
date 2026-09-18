"use client";

import { useMemo } from "react";

import type { Project, ProjectStatus } from "@/features/projects/types";

export type ProjectFilters = { teamName: string; status: "All statuses" | ProjectStatus; sprint: string; module: string; minScore: string; maxScore: string; minCompletion: string; maxCompletion: string; sortBy: "name-asc" | "name-desc" | "score-desc" | "score-asc" | "completion-desc" | "completion-asc" | "status-priority" };

export function useProjectFilters(projects: Project[], searchTerm: string, filters: ProjectFilters) {
  return useMemo(() => {
    const range = (value: string) => value.trim() === "" || Number.isNaN(Number(value)) ? null : Number(value);
    const minScore = range(filters.minScore); const maxScore = range(filters.maxScore); const minCompletion = range(filters.minCompletion); const maxCompletion = range(filters.maxCompletion);
    const matches = projects.filter((project) => {
      const searchBlob = [project.project_name, project.team_name, project.module, ...project.sprints.map((sprint) => sprint.name)].join(" ").toLowerCase();
      return (searchTerm.trim() === "" || searchBlob.includes(searchTerm.trim().toLowerCase())) && (filters.teamName.trim() === "" || project.team_name.toLowerCase().includes(filters.teamName.trim().toLowerCase())) && (filters.status === "All statuses" || project.status === filters.status) && (filters.sprint === "All sprints" || project.sprints.some((sprint) => sprint.name === filters.sprint)) && (filters.module === "All modules" || project.module === filters.module) && (minScore === null || project.score >= minScore) && (maxScore === null || project.score <= maxScore) && (minCompletion === null || project.completion >= minCompletion) && (maxCompletion === null || project.completion <= maxCompletion);
    });
    return [...matches].sort((left, right) => {
      if (filters.sortBy === "name-desc") return right.project_name.localeCompare(left.project_name); if (filters.sortBy === "score-desc") return right.score - left.score; if (filters.sortBy === "score-asc") return left.score - right.score; if (filters.sortBy === "completion-desc") return right.completion - left.completion; if (filters.sortBy === "completion-asc") return left.completion - right.completion;
      if (filters.sortBy === "status-priority") { const rank: Record<ProjectStatus, number> = { "At Risk": 0, Active: 1, Completed: 2 }; return rank[left.status] - rank[right.status] || right.score - left.score; }
      return left.project_name.localeCompare(right.project_name);
    });
  }, [projects, searchTerm, filters]);
}
