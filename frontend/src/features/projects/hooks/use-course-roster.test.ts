import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCourseRoster } from "@/features/projects/hooks/use-course-roster";
import { ApiError, apiRequest } from "@/lib/api/client";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_COURSE_ID = "22222222-2222-4222-8222-222222222222";

const rows = [
  {
    id: "s1",
    email: "here@example.com",
    full_name: "Here",
    is_active: true,
    enrollment_status: "this_section",
    enrolled_section_label: "CS111 · Section 2 (Fall 2026)",
  },
  {
    id: "s2",
    email: "sibling@example.com",
    full_name: "Sibling",
    is_active: true,
    enrollment_status: "other_section",
    enrolled_section_label: "CS111 · Section 1 (Fall 2026)",
  },
];

describe("useCourseRoster", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it("requests other sections and splits this section from sibling sections", async () => {
    vi.mocked(apiRequest).mockResolvedValue(rows);

    const { result } = renderHook(() => useCourseRoster(COURSE_ID));

    await waitFor(() => expect(result.current.isRosterReady).toBe(true));
    expect(apiRequest).toHaveBeenCalledWith(
      `/courses/${COURSE_ID}/students?include_other_sections=true`,
    );
    expect(result.current.courseStudents.map((student) => student.id)).toEqual(["s1"]);
    expect(result.current.otherSectionEnrollments).toEqual({ s2: "CS111 · Section 1 (Fall 2026)" });
    expect(result.current.rosterError).toBe("");
  });

  it("reports a failure instead of pretending nobody is enrolled", async () => {
    vi.mocked(apiRequest).mockImplementation(async () => {
      throw new ApiError("Server unavailable.", { status: 503 });
    });

    const { result } = renderHook(() => useCourseRoster(COURSE_ID));

    await waitFor(() => expect(result.current.rosterError).toBe("Server unavailable."));
    expect(result.current.isRosterReady).toBe(false);
  });

  it("reloadRoster refetches so a new sibling enrollment shows up", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce([rows[0]]).mockResolvedValueOnce(rows);

    const { result } = renderHook(() => useCourseRoster(COURSE_ID));
    await waitFor(() => expect(result.current.isRosterReady).toBe(true));
    expect(result.current.otherSectionEnrollments).toEqual({});

    await act(() => result.current.reloadRoster());

    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(result.current.otherSectionEnrollments).toEqual({ s2: "CS111 · Section 1 (Fall 2026)" });
  });

  it("ignores a slow response for a course that is no longer selected", async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    vi.mocked(apiRequest)
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce([rows[0]]);

    const { result, rerender } = renderHook(({ courseId }) => useCourseRoster(courseId), {
      initialProps: { courseId: COURSE_ID },
    });
    rerender({ courseId: OTHER_COURSE_ID });
    await waitFor(() => expect(result.current.isRosterReady).toBe(true));

    await act(async () => resolveFirst(rows));

    expect(result.current.otherSectionEnrollments).toEqual({});
    expect(result.current.courseStudents.map((student) => student.id)).toEqual(["s1"]);
  });

  it("does not call the API without a valid course", () => {
    const { result } = renderHook(() => useCourseRoster(""));

    expect(apiRequest).not.toHaveBeenCalled();
    expect(result.current.isRosterReady).toBe(false);
  });
});
