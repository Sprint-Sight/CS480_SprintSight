import { apiRequest } from "@/features/projects/components/projects-api";

type GitRunLike = {
  sprint_id: string;
  commits: unknown[];
  pagination?: { limit: number | null; offset: number | null; total: number; has_more: boolean } | null;
};

const MAX_PROBED_SPRINTS = 30;

function isNotFound(error: unknown) {
  return error instanceof Error && /not found/i.test(error.message);
}

function sprintNumber(sprintId: string) {
  const match = sprintId.match(/(\d+)/);
  return match ? Number(match[1]) : null;
}

export function normalizeGitRun<T extends GitRunLike>(run: T, sprintId: string): T & { pagination: NonNullable<GitRunLike["pagination"]> } {
  return {
    ...run,
    sprint_id: sprintId,
    pagination: run.pagination ?? { limit: null, offset: null, total: run.commits?.length ?? 0, has_more: false },
  };
}

// The backend only exposes Git runs per sprint, so probe sprint-1, sprint-2, ... until the first gap,
// and also fetch any sprint IDs already known locally.
export async function fetchProjectGitRuns<T extends GitRunLike>(
  projectId: string,
  courseId: string,
  knownSprintIds: string[] = [],
): Promise<T[]> {
  const fetchSprint = async (sprintId: string) => {
    try {
      const run = await apiRequest<T>(
        `/repo-ingestion/runs/${projectId}/${encodeURIComponent(sprintId)}?course_id=${encodeURIComponent(courseId)}`,
      );
      return normalizeGitRun(run, sprintId);
    } catch (error) {
      if (isNotFound(error)) return null;
      throw error;
    }
  };

  const runs = new Map<string, T>();
  for (let index = 1; index <= MAX_PROBED_SPRINTS; index += 1) {
    const sprintId = `sprint-${index}`;
    const run = await fetchSprint(sprintId);
    if (!run) break;
    runs.set(sprintId, run);
  }

  for (const sprintId of knownSprintIds) {
    if (runs.has(sprintId)) continue;
    const run = await fetchSprint(sprintId);
    if (run) runs.set(sprintId, run);
  }

  return [...runs.values()].sort((a, b) => (sprintNumber(a.sprint_id) ?? 0) - (sprintNumber(b.sprint_id) ?? 0));
}
