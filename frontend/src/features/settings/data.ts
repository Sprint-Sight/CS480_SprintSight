import type { SettingsSnapshot } from "@/features/settings/types";

const EQUAL_WEIGHT = 100 / 6;

// Fallback shown before the course's saved weights load; mirrors the backend's
// equal-weight default across its six rubric dimensions.
export const INITIAL_SETTINGS: SettingsSnapshot = {
  rubric: [
    { id: "requirements", label: "Requirements", value: EQUAL_WEIGHT },
    { id: "code_quality", label: "Code Quality", value: EQUAL_WEIGHT },
    { id: "testing", label: "Testing", value: EQUAL_WEIGHT },
    { id: "documentation", label: "Documentation", value: EQUAL_WEIGHT },
    { id: "collaboration", label: "Collaboration", value: EQUAL_WEIGHT },
    { id: "cicd", label: "CI/CD", value: EQUAL_WEIGHT },
  ],
};
