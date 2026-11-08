"use client";

import { useMemo } from "react";

import type { Project } from "@/features/projects/types";

export type ProjectFilters = { teamName: string; module: string; sortBy: "name-asc" | "name-desc" };

export function useProjectFilters(projects: Project[], searchTerm: string, filters: ProjectFilters) {
  return useMemo(() => {
    const search = searchTerm.trim().toLowerCase();
    const teamQuery = filters.teamName.trim().toLowerCase();
    const matches = projects.filter((project) => {
      const searchBlob = [project.project_name, project.team_name, project.module].join(" ").toLowerCase();
      return (search === "" || searchBlob.includes(search))
        && (teamQuery === "" || project.team_name.toLowerCase().includes(teamQuery))
        && (filters.module === "All modules" || project.module === filters.module);
    });
    return [...matches].sort((left, right) => (
      filters.sortBy === "name-desc"
        ? right.project_name.localeCompare(left.project_name)
        : left.project_name.localeCompare(right.project_name)
    ));
  }, [projects, searchTerm, filters]);
}
