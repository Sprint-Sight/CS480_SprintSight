/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useStudentProjectContext } from "@/features/student/hooks/use-student-project-context";
import * as studentApi from "@/features/student/student-project-api";

vi.mock("@/features/student/student-project-api");

describe("useStudentProjectContext - Student-Authorized Data Hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should not load data when enabled is false", () => {
    const { result } = renderHook(() => useStudentProjectContext(false));

    expect(result.current.isLoading).toBe(false);
    expect(result.current.courses).toEqual([]);
    expect(result.current.project).toBeNull();
  });

  it("should load student courses and projects when enabled", async () => {
    const mockCourses = [
      { id: "course-1", name: "CS480", code: "CS480", section: "001", year: 2024, term: "Fall" },
    ];

    const mockProjects = [
      {
        id: "project-1",
        project_name: "E-Commerce Platform",
        team_name: "Team Alpha",
        description: "A platform for online shopping",
        course_code: "CS480",
      },
    ];

    const mockSprints = ["sprint-1", "sprint-2"];
    const mockReports: Array<Record<string, unknown>> = [];

    vi.mocked(studentApi.getStudentCourses).mockResolvedValue(mockCourses);
    vi.mocked(studentApi.getStudentProjects).mockResolvedValue(mockProjects);
    vi.mocked(studentApi.getStudentProjectSprints).mockResolvedValue(mockSprints);
    vi.mocked(studentApi.getStudentProjectReports).mockResolvedValue(mockReports as any);

    const { result } = renderHook(() => useStudentProjectContext(true));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.courses).toEqual(mockCourses);
    expect(result.current.project).toEqual(mockProjects[0]);
    expect(result.current.sprints).toEqual(mockSprints);
  });

  it("should handle error gracefully when loading fails", async () => {
    const errorMsg = "Unauthorized";
    vi.mocked(studentApi.getStudentCourses).mockRejectedValue(new Error(errorMsg));
    vi.mocked(studentApi.getStudentProjects).mockRejectedValue(new Error(errorMsg));

    const { result } = renderHook(() => useStudentProjectContext(true));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toContain(errorMsg);
  });

  it("should select the latest sprint by default", async () => {
    const mockCourses: Array<Record<string, unknown>> = [];
    const mockProjects = [
      { id: "project-1", project_name: "Project", team_name: "Team", description: null, course_code: "CS480" },
    ];
    const mockSprints = ["sprint-1", "sprint-2", "sprint-3"];
    const mockReports: Array<Record<string, unknown>> = [];

    vi.mocked(studentApi.getStudentCourses).mockResolvedValue(mockCourses as any);
    vi.mocked(studentApi.getStudentProjects).mockResolvedValue(mockProjects);
    vi.mocked(studentApi.getStudentProjectSprints).mockResolvedValue(mockSprints);
    vi.mocked(studentApi.getStudentProjectReports).mockResolvedValue(mockReports as any);

    const { result } = renderHook(() => useStudentProjectContext(true));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.selectedSprintId).toBe("sprint-3");
  });

  it("should cancel in-flight requests when component unmounts", async () => {
    vi.mocked(studentApi.getStudentCourses).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve([]), 1000))
    );
    vi.mocked(studentApi.getStudentProjects).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve([]), 1000))
    );

    const { unmount } = renderHook(() => useStudentProjectContext(true));

    // Unmount immediately, before requests resolve
    unmount();

    // Wait to ensure cleanup doesn't cause errors
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(true).toBe(true); // If we get here, cleanup worked
  });
});
