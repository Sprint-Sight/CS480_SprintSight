import { apiRequest } from "@/features/projects/components/projects-api";

type ManualTextScope = {
  courseId: string;
  projectId: string;
  sprintId: string;
};

export async function getInstructorGuidance(scope: ManualTextScope) {
  const query = new URLSearchParams({
    course_id: scope.courseId,
    project_id: scope.projectId,
    sprint_id: scope.sprintId,
  });
  return apiRequest<{ expectations_text: string | null }>(`/manual-text?${query.toString()}`);
}

export async function saveInstructorGuidance(scope: ManualTextScope, expectationsText: string) {
  return apiRequest<{ status: "saved" }>("/manual-text", {
    method: "POST",
    body: JSON.stringify({
      course_id: scope.courseId,
      project_id: scope.projectId,
      sprint_id: scope.sprintId,
      expectations_text: expectationsText,
    }),
  });
}