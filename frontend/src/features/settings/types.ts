/** Keys match the backend rubric dimensions (`RUBRIC_WEIGHTS` in the assessment service). */
export type RubricDimensionId = "requirements" | "code_quality" | "testing" | "documentation" | "collaboration" | "cicd";

export type RubricWeight = {
  id: RubricDimensionId;
  label: string;
  /** Percentage (0-100). The API stores fractions (0-1). */
  value: number;
};

export type LlmModelOption = {
  id: string;
  provider: "OpenAI" | "Ollama";
  model: string;
  description: string;
};

export type SettingsSnapshot = {
  rubric: RubricWeight[];
};
