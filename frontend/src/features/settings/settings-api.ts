import { apiRequest } from "@/lib/api/client";
import type { LlmModelOption } from "@/features/settings/types";

export type ModelCatalogResponse = {
  models: LlmModelOption[];
  default_model_id: string;
};

export type ModelSelectionResponse = {
  model_id: string;
  is_custom: boolean;
  default_model_id: string;
  updated_at?: string | null;
};

export type InstructorJiraCredentialsResponse = {
  jira_email: string;
  jira_token_configured: boolean;
  is_saved: boolean;
};

export type RubricWeightsResponse = {
  course_id: string;
  /** Dimension key -> fraction of the total score (sums to 1.0). */
  weights: Record<string, number>;
  is_custom: boolean;
  updated_by?: string | null;
  updated_at?: string | null;
};

export type CourseOption = {
  id: string;
  code: string;
  name: string;
  section: string;
  term: string;
  year: number;
};

export function getCourses() {
  return apiRequest<CourseOption[]>("/courses");
}

export function getRubricWeights(courseId: string) {
  return apiRequest<RubricWeightsResponse>(`/assessments/rubric-weights?course_id=${encodeURIComponent(courseId)}`);
}

export function saveRubricWeights(courseId: string, weights: Record<string, number>) {
  return apiRequest<RubricWeightsResponse>(`/assessments/rubric-weights?course_id=${encodeURIComponent(courseId)}`, {
    method: "PUT",
    body: JSON.stringify({ weights }),
  });
}

export function getModelCatalog() {
  return apiRequest<ModelCatalogResponse>("/models");
}

export function getModelSelection() {
  return apiRequest<ModelSelectionResponse>("/models/selection");
}

export function saveModelSelection(modelId: string) {
  return apiRequest<ModelSelectionResponse>("/models/selection", {
    method: "PUT",
    body: JSON.stringify({ model_id: modelId }),
  });
}

export function getInstructorJiraCredentials() {
  return apiRequest<InstructorJiraCredentialsResponse>("/settings/jira-credentials");
}

export function saveInstructorJiraCredentials(jiraEmail: string, jiraApiToken?: string) {
  return apiRequest<InstructorJiraCredentialsResponse>("/settings/jira-credentials", {
    method: "PUT",
    body: JSON.stringify({
      jira_email: jiraEmail,
      ...(jiraApiToken ? { jira_api_token: jiraApiToken } : {}),
    }),
  });
}
