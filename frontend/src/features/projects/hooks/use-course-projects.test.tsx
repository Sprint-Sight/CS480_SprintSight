/// <reference types="vitest/globals" />
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/lib/query/query-client";
import { invalidateProjectCaches } from "@/features/projects/course-projects-api";

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest,
}));

import { useScopeProjects } from "@/features/projects/hooks/use-course-projects";

const course = { id: "c1", code: "CS480", name: "Capstone", section: "001", term: "Fall", year: 2025 };
const project = { id: "p1", team_name: "Team A", project_name: "SprintSight", jira_project_key: null, members: [] };

function setup() {
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe("useScopeProjects shared cache", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiRequest.mockImplementation(async (path: string) => {
      if (path === "/courses") return [course];
      if (path === "/courses/c1/projects") return [project];
      throw new Error(`unexpected path ${path}`);
    });
  });

  it("loads courses and projects once and reuses them across consumers", async () => {
    const { wrapper } = setup();

    const first = renderHook(() => useScopeProjects(), { wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    const second = renderHook(() => useScopeProjects(), { wrapper });
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));

    expect(second.result.current.data).toEqual([{ course, projects: [project] }]);
    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(apiRequest).toHaveBeenCalledWith("/courses");
    expect(apiRequest).toHaveBeenCalledWith("/courses/c1/projects");
  });

  it("refetches after invalidateProjectCaches", async () => {
    const { queryClient, wrapper } = setup();

    const { result } = renderHook(() => useScopeProjects(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiRequest).toHaveBeenCalledTimes(2);

    await invalidateProjectCaches(queryClient);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(4));
  });
});
