import { apiRequest } from "@/features/projects/components/projects-api";

export type PeerEvaluationResponse = {
  evaluation_id: string;
  course_id: string;
  project_id: string;
  rater_id: string;
  rated_id: string;
  score: number;
  remarks: string | null;
  reason: string | null;
  created_at: string;
};

export type PeerEvaluationInstructorView = {
  evaluation_id: string;
  course_id: string;
  project_id: string;
  rater_id: string;
  rater_email: string;
  rater_full_name: string;
  rated_id: string;
  rated_email: string;
  rated_full_name: string;
  score: number;
  remarks: string | null;
  reason: string | null;
  created_at: string;
};

export type PeerEvaluationSummary = {
  project_id: string;
  project_name: string;
  total_evaluations: number;
  average_score: number | null;
  evaluations: PeerEvaluationInstructorView[];
};

export type CoursePeerEvaluationSummary = {
  course_id: string;
  course_code: string;
  is_open: boolean;
  expires_at: string | null;
  total_projects: number;
  total_evaluations: number;
  projects: PeerEvaluationSummary[];
};

export type EvaluationStatusResponse = {
  can_evaluate: boolean;
  is_open: boolean;
  expires_at: string | null;
  message: string;
};

export type PeerEvaluationConfigResponse = {
  course_id: string;
  is_open: boolean;
  expires_at: string | null;
  updated_by: string;
  updated_at: string;
};

export type PeerTeammate = {
  id: string;
  name: string;
};

export const getCurrentUserId = async (): Promise<string> => {
  const user = await apiRequest<{ id: string }>("/auth/me", { method: "GET" });
  return user.id;
};

type SubmitEvaluationPayload = {
  project_id: string;
  rated_id: string;
  score: number;
  remarks?: string;
  reason?: string;
};

type SetConfigPayload = {
  is_open: boolean;
  expires_at?: string;
};

export const submitEvaluation = (
  payload: SubmitEvaluationPayload,
): Promise<PeerEvaluationResponse> => {
  return apiRequest<PeerEvaluationResponse>("/peer-evaluation/evaluations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
};

export const getMyEvaluations = (
  projectId?: string,
): Promise<PeerEvaluationResponse[]> => {
  const queryParams = new URLSearchParams();
  if (projectId) queryParams.append("project_id", projectId);

  return apiRequest<PeerEvaluationResponse[]>(
    `/peer-evaluation/evaluations/mine${queryParams.toString() ? `?${queryParams}` : ""}`,
    {
      method: "GET",
    },
  );
};

export const getEvaluationStatus = (
  courseId: string,
): Promise<EvaluationStatusResponse> => {
  return apiRequest<EvaluationStatusResponse>(
    `/peer-evaluation/courses/${courseId}/status`,
    {
      method: "GET",
    },
  );
};

export const getCourseEvaluations = (
  courseId: string,
): Promise<CoursePeerEvaluationSummary> => {
  return apiRequest<CoursePeerEvaluationSummary>(
    `/peer-evaluation/courses/${courseId}/evaluations`,
    {
      method: "GET",
    },
  );
};

export const getProjectEvaluations = (
  projectId: string,
): Promise<PeerEvaluationSummary> => {
  return apiRequest<PeerEvaluationSummary>(
    `/peer-evaluation/projects/${projectId}/evaluations`,
    {
      method: "GET",
    },
  );
};

export const getEvaluationConfig = (
  courseId: string,
): Promise<PeerEvaluationConfigResponse | null> => {
  return apiRequest<PeerEvaluationConfigResponse | null>(
    `/peer-evaluation/courses/${courseId}/config`,
    {
      method: "GET",
    },
  );
};

export const setEvaluationConfig = (
  courseId: string,
  payload: SetConfigPayload,
): Promise<PeerEvaluationConfigResponse> => {
  return apiRequest<PeerEvaluationConfigResponse>(
    `/peer-evaluation/courses/${courseId}/config`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
};
