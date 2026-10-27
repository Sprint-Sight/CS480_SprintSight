import { apiRequest } from "@/features/projects/components/projects-api";
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
