"use client";

import { useEffect, useMemo, useState } from "react";

import {
  getStudentCourses,
  getStudentProjectReports,
  getStudentProjects,
  getStudentProjectSprints,
  type StudentAssessmentReport,
  type StudentCourse,
  type StudentProject,
} from "@/features/student/student-project-api";

type StudentProjectContext = {
  courses: StudentCourse[];
  project: StudentProject | null;
  sprints: string[];
  selectedSprintId: string;
  report: StudentAssessmentReport | null;
  isLoading: boolean;
  error: string;
};

export function useStudentProjectContext(enabled: boolean): StudentProjectContext {
  const [courses, setCourses] = useState<StudentCourse[]>([]);
  const [project, setProject] = useState<StudentProject | null>(null);
  const [sprints, setSprints] = useState<string[]>([]);
  const [reports, setReports] = useState<StudentAssessmentReport[]>([]);
  const [isLoading, setIsLoading] = useState(enabled);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function loadContext() {
      setIsLoading(true);
      setError("");
      try {
        const [loadedCourses, projects] = await Promise.all([getStudentCourses(), getStudentProjects()]);
        const selectedProject = projects[0] || null;
        if (!selectedProject) {
          if (!cancelled) {
            setCourses(loadedCourses);
            setProject(null);
            setSprints([]);
            setReports([]);
          }
          return;
        }
        const [loadedSprints, loadedReports] = await Promise.all([
          getStudentProjectSprints(selectedProject.id),
          getStudentProjectReports(selectedProject.id),
        ]);
        if (!cancelled) {
          setCourses(loadedCourses);
          setProject(selectedProject);
          setSprints(loadedSprints);
          setReports(loadedReports);
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load your project context.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadContext();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const selectedSprintId = sprints.at(-1) || reports.at(-1)?.sprint_id || "";
  const report = useMemo(
    () => reports.find((item) => item.sprint_id === selectedSprintId) || reports.at(-1) || null,
    [reports, selectedSprintId],
  );

  return { courses, project, sprints, selectedSprintId, report, isLoading, error };
}
