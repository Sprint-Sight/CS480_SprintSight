import type { SettingsSnapshot } from "@/features/settings/types";

export const INITIAL_SETTINGS: SettingsSnapshot = {
  rubric: [
    { id: "requirements", label: "Requirements", value: 20 },
    { id: "codeQuality", label: "Code Quality", value: 25 },
    { id: "testing", label: "Testing", value: 20 },
    { id: "documentation", label: "Documentation", value: 15 },
    { id: "collaboration", label: "Collaboration", value: 20 },
  ],
  llmParams: {
    temperature: 0.2,
    maxTokens: 1800,
    topP: 0.95,
    enableChainOfThought: true,
  },
};
