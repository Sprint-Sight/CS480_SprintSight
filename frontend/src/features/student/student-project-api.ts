import { apiRequest } from "@/features/projects/components/projects-api";

export type StudentCourse = {
  id: string;
  code: string;
  name: string;
  section: string;
  year: number;
  term: string;
};

export type StudentProject = {
  id: string;
  project_name: string;
  team_name: string;
  description: string | null;
  course_code: string;
};

export type StudentAssessmentReport = {
  project_id: string;
  sprint_id: string;
  generated_at: string;
  team_score: { score: number; rationale: string; overall_grade?: string };
  rubric_scores: Record<string, { score: number; justification?: string | null; evidence_citations?: string[] }>;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
};

export const getStudentCourses = () => apiRequest<StudentCourse[]>("/students/courses");
export const getStudentProjects = () => apiRequest<StudentProject[]>("/students/projects");
export const getStudentProjectSprints = (projectId: string) => apiRequest<string[]>(`/students/projects/${encodeURIComponent(projectId)}/sprints`);
export const getStudentProjectReports = (projectId: string) => apiRequest<StudentAssessmentReport[]>(`/students/projects/${encodeURIComponent(projectId)}/reports`);
