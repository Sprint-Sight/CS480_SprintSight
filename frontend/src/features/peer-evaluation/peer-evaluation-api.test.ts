import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getJiraContributionOutliers,
  getStudentJiraContribution,
  setEvaluationConfig,
  updateEvaluation,
} from "@/features/peer-evaluation/peer-evaluation-api";
import { apiRequest } from "@/features/projects/components/projects-api";

vi.mock("@/features/projects/components/projects-api", () => ({
  apiRequest: vi.fn(),
}));

describe("peer evaluation and Jira contribution APIs", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it("requests course Jira outliers with the optional filter", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ students: [] });

    await getJiraContributionOutliers("course-1", true);

    expect(apiRequest).toHaveBeenCalledWith(
      "/jira/contribution-outliers/courses/course-1?only_outliers=true",
      { method: "GET" },
    );
  });

  it("requests selected-student ticket evidence", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ tickets: [] });

    await getStudentJiraContribution("course-1", "student-1");

    expect(apiRequest).toHaveBeenCalledWith(
      "/jira/contribution-outliers/courses/course-1/students/student-1",
      { method: "GET" },
    );
  });

  it("uses PATCH for edits to an existing peer evaluation", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ evaluation_id: "evaluation-1" });

    await updateEvaluation("evaluation-1", { score: 4, remarks: null });

    expect(apiRequest).toHaveBeenCalledWith(
      "/peer-evaluation/evaluations/evaluation-1",
      { method: "PATCH", body: JSON.stringify({ score: 4, remarks: null }) },
    );
  });

  it("saves the complete evaluation window schedule", async () => {
    const payload = {
      is_open: true,
      opens_at: "2026-10-28T08:00:00Z",
      expires_at: "2026-11-01T08:00:00Z",
    };
    vi.mocked(apiRequest).mockResolvedValue(payload);

    await setEvaluationConfig("course-1", payload);

    expect(apiRequest).toHaveBeenCalledWith(
      "/peer-evaluation/courses/course-1/config",
      { method: "POST", body: JSON.stringify(payload) },
    );
  });
});
