import type { SettingsSnapshot } from "@/features/settings/types";

export const INITIAL_SETTINGS: SettingsSnapshot = {
  rubric: [
    { id: "requirements", label: "Requirements", value: 20 },
    { id: "codeQuality", label: "Code Quality", value: 25 },
    { id: "testing", label: "Testing", value: 20 },
    { id: "documentation", label: "Documentation", value: 15 },
    { id: "collaboration", label: "Collaboration", value: 20 },
  ],
  llmModels: [
    {
      id: "openai-gpt4",
      provider: "OpenAI",
      model: "GPT-4",
      description: "Best quality, cloud-based",
    },
    {
      id: "openai-gpt35",
      provider: "OpenAI",
      model: "GPT-3.5",
      description: "Faster, cost-effective",
    },
    {
      id: "ollama-llama3",
      provider: "Ollama",
      model: "Llama 3",
      description: "Local, privacy-first",
    },
    {
      id: "ollama-mistral",
      provider: "Ollama",
      model: "Mistral",
      description: "Local, lightweight",
    },
  ],
  selectedModelId: "openai-gpt4",
  llmParams: {
    temperature: 0.2,
    maxTokens: 1800,
    topP: 0.95,
    enableChainOfThought: true,
  },
  apiConnections: {
    githubToken: "ghp_xxxxxxxxxxxxxxxxx",
    jiraToken: "",
    jiraDomain: "university-cs.atlassian.net",
    githubConnected: true,
    jiraConnected: true,
  },
};
