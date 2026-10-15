import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchProjectGitRuns } from "@/features/artifacts/git-runs-api";
import { apiRequest } from "@/features/projects/components/projects-api";

vi.mock("@/features/projects/components/projects-api", () => ({ apiRequest: vi.fn() }));

const run = (sprint: string) => ({ sprint_id: sprint, commits: [{}, {}] });

describe("fetchProjectGitRuns", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it("loads consecutive sprints from the backend until the first missing one", async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path.includes("/sprint-1?") || path.includes("/sprint-2?")) return run(path.includes("sprint-1") ? "sprint-1" : "sprint-2");
      throw new Error("Ingestion data not found.");
    });
    const runs = await fetchProjectGitRuns("p", "c");
    expect(runs.map((item) => item.sprint_id)).toEqual(["sprint-1", "sprint-2"]);
    expect(runs[1]?.pagination?.total).toBe(2);
  });

  it("includes non-consecutive known sprints and surfaces other errors", async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path.includes("/sprint-1?")) return run("sprint-1");
      if (path.includes("/sprint-4?")) return run("sprint-4");
      throw new Error("Ingestion data not found.");
    });
    expect((await fetchProjectGitRuns("p", "c", ["sprint-4"])).map((item) => item.sprint_id)).toEqual(["sprint-1", "sprint-4"]);

    vi.mocked(apiRequest).mockRejectedValue(new Error("Boom"));
    await expect(fetchProjectGitRuns("p", "c")).rejects.toThrow("Boom");
  });
});
