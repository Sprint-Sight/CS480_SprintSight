export type SprintOption = { value: string; label: string };

function sprintNumber(sprintId: string): number | null {
  const match = /(\d+)$/.exec(sprintId);
  return match ? Number(match[1]) : null;
}

/** "sprint-3" -> "Sprint 3"; IDs without a trailing number are shown unchanged. */
export function sprintLabel(sprintId: string): string {
  const number = sprintNumber(sprintId);
  return number === null ? sprintId : `Sprint ${number}`;
}

/** Builds dropdown options from real sprint IDs, numbered sprints first and labelled "Sprint N". */
export function buildSprintOptions(sprintIds: string[]): SprintOption[] {
  return [...new Set(sprintIds)]
    .map((value) => ({ value, number: sprintNumber(value) }))
    .sort((a, b) => {
      if (a.number === null || b.number === null) {
        if (a.number === b.number) return a.value.localeCompare(b.value);
        return a.number === null ? 1 : -1;
      }
      return a.number - b.number;
    })
    .map(({ value }) => ({ value, label: sprintLabel(value) }));
}

export function semesterLabel(course: { term: string; year: number }): string {
  return `${course.term} ${course.year}`.trim();
}
