import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePeerEvaluation } from "@/features/peer-evaluation/hooks/use-peer-evaluation";

const apiMocks = vi.hoisted(() => ({
  submitEvaluation: vi.fn(),
  updateEvaluation: vi.fn(),
  getMyEvaluations: vi.fn(),
  getEvaluationStatus: vi.fn(),
  getCourseEvaluations: vi.fn(),
  getProjectEvaluations: vi.fn(),
  getMemberEvaluations: vi.fn(),
  getEvaluationConfig: vi.fn(),
  setEvaluationConfig: vi.fn(),
}));

vi.mock("@/features/peer-evaluation/peer-evaluation-api", () => apiMocks);

const response = {
  evaluation_id: "evaluation-1",
  course_id: "course-1",
  project_id: "project-1",
  rater_id: "rater-1",
  rated_id: "student-2",
  score: 4,
  remarks: null,
  created_at: "2026-10-27T00:00:00Z",
};

describe("usePeerEvaluation submission behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.submitEvaluation.mockResolvedValue(response);
    apiMocks.updateEvaluation.mockResolvedValue(response);
  });

  it("creates a new evaluation with POST when no existing evaluation ID is supplied", async () => {
    const { result } = renderHook(() => usePeerEvaluation());

    await act(async () => {
      await result.current.submitNewEvaluation({
        projectId: "project-1",
        ratedId: "student-2",
        score: 4,
      });
    });

    expect(apiMocks.submitEvaluation).toHaveBeenCalledWith({
      project_id: "project-1",
      rated_id: "student-2",
      score: 4,
      remarks: undefined,
    });
    expect(apiMocks.updateEvaluation).not.toHaveBeenCalled();
  });

  it("updates an existing evaluation with PATCH and keeps the response in local state", async () => {
    const { result } = renderHook(() => usePeerEvaluation());

    await act(async () => {
      await result.current.submitNewEvaluation({
        projectId: "project-1",
        ratedId: "student-2",
        evaluationId: "evaluation-1",
        score: 4,
        remarks: "Good contribution",
      });
    });

    expect(apiMocks.updateEvaluation).toHaveBeenCalledWith("evaluation-1", {
      score: 4,
      remarks: "Good contribution",
    });
    expect(apiMocks.submitEvaluation).not.toHaveBeenCalled();
    expect(result.current.myEvaluations).toEqual([response]);
  });
});
