import { describe, expect, it } from "vitest";

import { parseJobEvent } from "@/features/assessment/hooks/use-assessment-report";

describe("parseJobEvent", () => {
  it("parses a valid job event object", () => {
    expect(parseJobEvent('{"status":"running","progress":42,"message":"Scoring"}')).toEqual({
      status: "running",
      progress: 42,
      message: "Scoring",
    });
  });

  it("returns null for malformed JSON instead of throwing", () => {
    expect(parseJobEvent("{not json")).toBeNull();
    expect(parseJobEvent("")).toBeNull();
  });

  it("returns null for JSON that is not an object", () => {
    expect(parseJobEvent("null")).toBeNull();
    expect(parseJobEvent("42")).toBeNull();
    expect(parseJobEvent('"done"')).toBeNull();
    expect(parseJobEvent("[1,2]")).toBeNull();
  });
});
