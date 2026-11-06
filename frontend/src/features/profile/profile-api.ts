import { apiRequest } from "@/lib/api/client";

type CourseSummary = { id: string };
type ProjectSummary = { id: string };

export type TeachingSummary = {
  activeSectionsCount: number;
  teamsMonitoredCount: number;
};

/** Courses and their projects visible to an instructor/admin (GET /courses is faculty-only). */
export async function getTeachingSummary(): Promise<TeachingSummary> {
  const courses = await apiRequest<CourseSummary[]>("/courses");
  const projectLists = await Promise.all(
    courses.map((course) =>
      apiRequest<ProjectSummary[]>(`/courses/${encodeURIComponent(course.id)}/projects`).catch(
        () => [] as ProjectSummary[],
      ),
    ),
  );
  return {
    activeSectionsCount: courses.length,
    teamsMonitoredCount: projectLists.reduce((total, projects) => total + projects.length, 0),
  };
}
