export type RubricWeight = {
  id: "requirements" | "codeQuality" | "testing" | "documentation" | "collaboration";
  label: string;
  value: number;
};

export type LlmModelOption = {
  id: string;
  provider: "OpenAI" | "Ollama";
  model: string;
  description: string;
};

export type LlmEvaluationParameters = {
  temperature: number;
  maxTokens: number;
  topP: number;
  enableChainOfThought: boolean;
};

export type SettingsSnapshot = {
  rubric: RubricWeight[];
  llmParams: LlmEvaluationParameters;
};
