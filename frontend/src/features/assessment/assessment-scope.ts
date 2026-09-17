export type AssessmentScopeProject = {
  id: string;
  courseId?: string;
  courseLabel?: string;
  label: string;
};

type AssessmentScopeInput = {
  selectedCourseId: string;
  selectedProjectId: string;
  selectedSprintId: string;
  projects: AssessmentScopeProject[];
};

export type ResolvedAssessmentScope = {
  courseId: string;
  courseLabel: string;
  projectId: string;
  sprintId: string;
  projectLabel: string;
};

export function resolveAssessmentScope(input: AssessmentScopeInput): ResolvedAssessmentScope | null {
  const project = input.projects.find((option) => option.id === input.selectedProjectId);
  if (!project?.courseId || !project.courseLabel || !input.selectedSprintId.trim()) return null;
  if (input.selectedCourseId && input.selectedCourseId !== project.courseId) return null;
  return {
    courseId: project.courseId,
    courseLabel: project.courseLabel,
    projectId: project.id,
    sprintId: input.selectedSprintId.trim(),
    projectLabel: project.label,
  };
}