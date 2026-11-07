/// <reference types="vitest/globals" />
import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useProjectFilters, type ProjectFilters } from "@/features/projects/hooks/use-project-filters";
import type { Project } from "@/features/projects/types";

const projects = [
  { id: "p1", project_name: "Beta", team_name: "Team Red", module: "Core" },
  { id: "p2", project_name: "Alpha", team_name: "Team Blue", module: "Web" },
] as unknown as Project[];

const defaults: ProjectFilters = { teamName: "", module: "All modules", sortBy: "name-asc" };

describe("useProjectFilters", () => {
  it("sorts by name ascending by default and descending on request", () => {
    const { result: asc } = renderHook(() => useProjectFilters(projects, "", defaults));
    expect(asc.current.map((project) => project.project_name)).toEqual(["Alpha", "Beta"]);

    const { result: desc } = renderHook(() => useProjectFilters(projects, "", { ...defaults, sortBy: "name-desc" }));
    expect(desc.current.map((project) => project.project_name)).toEqual(["Beta", "Alpha"]);
  });

  it("filters by team name and module without any status, score or sprint criteria", () => {
    const { result } = renderHook(() => useProjectFilters(projects, "", { ...defaults, teamName: "blue" }));
    expect(result.current.map((project) => project.id)).toEqual(["p2"]);

    const { result: byModule } = renderHook(() => useProjectFilters(projects, "", { ...defaults, module: "Core" }));
    expect(byModule.current.map((project) => project.id)).toEqual(["p1"]);
  });
});
