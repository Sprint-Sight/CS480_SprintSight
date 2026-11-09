/// <reference types="vitest/globals" />
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardData } from "@/features/dashboard/hooks/use-dashboard-data";
import { apiRequest } from "@/lib/api/client";
import { readScope } from "@/features/ingestion/scope-store";
import { createTestWrapper } from "@/test-utils";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const COURSE_ID = "22222222-2222-4222-8222-222222222222";
const JIRA_SNAPSHOT = { marker: "jira-snapshot" };

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));
vi.mock("@/lib/auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/session")>()),
  useSession: vi.fn(() => ({ user: { role: "instructor", fullName: "Ada Instructor" } })),
}));
vi.mock("@/features/ingestion/scope-store", () => ({
  readScope: vi.fn(),
  subscribeScope: vi.fn(() => () => undefined),
}));
vi.mock("@/features/projects/course-projects-api", () => ({
  scopeProjectsQueryOptions: vi.fn(() => ({
    queryKey: ["scope-projects-test"],
    queryFn: () => Promise.resolve([
      { course: { id: COURSE_ID }, projects: [{ id: PROJECT_ID, team_name: "Team A", project_name: "Project A" }] },
    ]),
  })),
}));

function notFound() {
  return Object.assign(new Error("Not found"), { status: 404 });
}

function mockJiraCompleted() {
  return (path: string) => {
    if (path === `/jira-ingestion/runs/${PROJECT_ID}/Sprint%201`) {
      return Promise.resolve([{ run_id: "run-1", sprint_id: "Sprint 1", processing_status: "completed" }]);
    }
    if (path.endsWith("/cleaned")) return Promise.resolve(JIRA_SNAPSHOT);
    return Promise.reject(new Error(`Unexpected request: ${path}`));
  };
}

const router = { replace: vi.fn() };

describe("useDashboardData", () => {
  beforeEach(() => {
    vi.mocked(readScope).mockReturnValue({
      selectedProjectId: PROJECT_ID,
      selectedCourseId: COURSE_ID,
      selectedSprintId: "Sprint 1",
    } as ReturnType<typeof readScope>);
    vi.mocked(apiRequest).mockReset();
  });

  it("keeps Jira data and reports only the Git error when the Git request fails", async () => {
    vi.mocked(apiRequest).mockImplementation((path: string) => {
      if (path.startsWith("/repo-ingestion")) return Promise.reject(new Error("Git service unavailable"));
      return mockJiraCompleted()(path);
    });

    const { result } = renderHook(() => useDashboardData(router), { wrapper: createTestWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.jiraSnapshot).toEqual(JIRA_SNAPSHOT);
    expect(result.current.gitMetrics).toBeNull();
    expect(result.current.loadError).toBe("Git service unavailable");
    expect(result.current.courseCount).toBe(1);
    expect(result.current.projects).toHaveLength(1);
  });

  it("treats 404 responses as empty data rather than errors", async () => {
    vi.mocked(apiRequest).mockImplementation((path: string) => {
      if (path.startsWith("/repo-ingestion") || path.startsWith("/jira-ingestion")) return Promise.reject(notFound());
      return Promise.reject(new Error(`Unexpected request: ${path}`));
    });

    const { result } = renderHook(() => useDashboardData(router), { wrapper: createTestWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.gitMetrics).toBeNull();
    expect(result.current.jiraSnapshot).toBeNull();
    expect(result.current.loadError).toBe("");
  });

  it("reports both errors when Git and Jira both fail", async () => {
    vi.mocked(apiRequest).mockImplementation((path: string) => {
      if (path.startsWith("/repo-ingestion")) return Promise.reject(new Error("Git down"));
      return Promise.reject(new Error("Jira down"));
    });

    const { result } = renderHook(() => useDashboardData(router), { wrapper: createTestWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBe("Git down Jira down");
  });

  it("aborts in-flight dashboard requests when the page unmounts", async () => {
    const signals: AbortSignal[] = [];
    vi.mocked(apiRequest).mockImplementation((path: string, options?: { signal?: AbortSignal }) => {
      if (options?.signal) signals.push(options.signal);
      return new Promise(() => undefined);
    });

    const { unmount } = renderHook(() => useDashboardData(router), { wrapper: createTestWrapper() });

    await waitFor(() => expect(signals.length).toBeGreaterThan(0));
    expect(signals.every((signal) => !signal.aborted)).toBe(true);
    unmount();
    expect(signals.every((signal) => signal.aborted)).toBe(true);
  });
});
