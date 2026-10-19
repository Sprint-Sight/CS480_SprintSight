/// <reference types="vitest/globals" />
import { beforeEach, describe, expect, it } from "vitest";

import {
  clearActiveAssessmentJob,
  readActiveAssessmentJob,
  saveActiveAssessmentJob,
} from "@/features/assessment/active-assessment-job";

describe("active assessment job storage", () => {
  beforeEach(() => sessionStorage.clear());

  it("round-trips and clears a job", () => {
    const job = { jobId: "j1", courseId: "c1", projectId: "p1", sprintId: "sprint-1" };
    saveActiveAssessmentJob(job);
    expect(readActiveAssessmentJob()).toEqual(job);
    clearActiveAssessmentJob();
    expect(readActiveAssessmentJob()).toBeNull();
  });

  it("ignores malformed or incomplete data", () => {
    sessionStorage.setItem("sprintsight-active-assessment-job", "{bad");
    expect(readActiveAssessmentJob()).toBeNull();
    sessionStorage.setItem("sprintsight-active-assessment-job", JSON.stringify({ jobId: "j1" }));
    expect(readActiveAssessmentJob()).toBeNull();
  });
});
