"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { isUuid } from "@/features/projects/components/projects-api";

export type RosterStudent = { id: string; email: string; full_name: string; is_active: boolean };

type CourseStudentRow = RosterStudent & {
  enrollment_status?: "this_section" | "other_section";
  enrolled_section_label?: string | null;
};

/**
 * Who is enrolled in the selected course section, and who is already enrolled in another
 * section of the same course code (a student can be in only one section per code).
 *
 * `isRosterReady` is false while loading or after a failure, so callers can avoid offering
 * an Enroll action based on unknown enrollment data.
 */
export function useCourseRoster(courseId: string) {
  const [courseStudents, setCourseStudents] = useState<RosterStudent[]>([]);
  // Student id -> label of the other section they are enrolled in.
  const [otherSectionEnrollments, setOtherSectionEnrollments] = useState<Record<string, string>>(
    {},
  );
  const [rosterError, setRosterError] = useState("");
  const [isRosterReady, setIsRosterReady] = useState(false);
  // Ignore responses that arrive after a newer request (e.g. a quick course switch).
  const latestRequest = useRef(0);

  const reloadRoster = useCallback(async () => {
    const requestId = ++latestRequest.current;
    if (!courseId || !isUuid(courseId)) {
      setCourseStudents([]);
      setOtherSectionEnrollments({});
      setRosterError("");
      setIsRosterReady(false);
      return;
    }

    setIsRosterReady(false);
    setRosterError("");
    try {
      const rows = await apiRequest<CourseStudentRow[]>(
        `/courses/${courseId}/students?include_other_sections=true`,
      );
      if (requestId !== latestRequest.current) return;
      setCourseStudents(
        rows
          .filter((row) => row.enrollment_status !== "other_section")
          .map(({ id, email, full_name, is_active }) => ({ id, email, full_name, is_active })),
      );
      setOtherSectionEnrollments(
        Object.fromEntries(
          rows
            .filter((row) => row.enrollment_status === "other_section")
            .map((row) => [row.id, row.enrolled_section_label || "another section"]),
        ),
      );
      setIsRosterReady(true);
    } catch (error) {
      if (requestId !== latestRequest.current) return;
      setCourseStudents([]);
      setOtherSectionEnrollments({});
      setRosterError(getErrorMessage(error, "Could not load this course's enrollments."));
    }
  }, [courseId]);

  useEffect(() => {
    void reloadRoster();
  }, [reloadRoster]);

  return {
    courseStudents,
    setCourseStudents,
    otherSectionEnrollments,
    rosterError,
    isRosterReady,
    reloadRoster,
  };
}
