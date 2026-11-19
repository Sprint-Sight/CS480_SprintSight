import type { JiraSprint } from "@/features/artifacts/jira-api";

type JiraSprintFieldProps = {
  sprintId: string;
  sprints: JiraSprint[];
  onSprintIdChange: (sprintId: string) => void;
};

export function JiraSprintField({ sprintId, sprints, onSprintIdChange }: JiraSprintFieldProps) {
  const hasSprints = sprints.length > 0;

  return (
    <div className="space-y-1">
      <label
        htmlFor="jira-sprint-id"
        className="block text-xs font-semibold uppercase tracking-wide text-slate-500"
      >
        Sprint
      </label>
      {hasSprints ? (
        <select
          id="jira-sprint-id"
          className="h-10 w-full rounded-lg border border-slate-200 bg-slate-100 px-3 text-sm font-medium text-slate-700"
          value={sprintId}
          onChange={(event) => onSprintIdChange(event.target.value)}
        >
          {sprints.map((sprint) => (
            <option key={String(sprint.id)} value={String(sprint.name || "")}>
              {sprint.name}{" "}
              {sprint.state
                ? `(${sprint.state.toLowerCase() === "closed" ? "Completed" : sprint.state})`
                : ""}
            </option>
          ))}
        </select>
      ) : (
        <input
          id="jira-sprint-id"
          type="text"
          value={sprintId}
          onChange={(event) => onSprintIdChange(event.target.value)}
          placeholder="Sprint 2"
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
        />
      )}
      <p className="text-xs text-slate-500">
        {hasSprints
          ? "Sprints from your Jira board"
          : "Enter the Jira sprint name, for example “Sprint 2”."}
      </p>
    </div>
  );
}
