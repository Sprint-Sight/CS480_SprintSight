import type {
  InsightsMode,
  LabelStatusFilter,
  RunFilters,
  RunsPage,
} from "@/features/insights/types";

type Props = {
  filters: RunFilters;
  facets?: RunsPage["facets"];
  onChange: (next: RunFilters) => void;
  mode?: InsightsMode;
};
const select = "rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm";

export function RunFiltersBar({ filters, facets, onChange, mode = "blind_label" }: Props) {
  const override = mode === "override_gate";
  const set = (patch: Partial<RunFilters>) => onChange({ ...filters, ...patch, page: 1 });
  return (
    <div className="flex flex-wrap gap-2">
      <select
        aria-label="Course"
        className={select}
        value={filters.courseId ?? ""}
        onChange={(e) => set({ courseId: e.target.value || undefined })}
      >
        <option value="">All courses</option>
        {facets?.courses.map((c) => (
          <option key={c.courseId} value={c.courseId}>
            {c.courseCode} {c.section}
          </option>
        ))}
      </select>
      <select
        aria-label="Sprint"
        className={select}
        value={filters.sprintId ?? ""}
        onChange={(e) => set({ sprintId: e.target.value || undefined })}
      >
        <option value="">All sprints</option>
        {facets?.sprints.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select
        aria-label="Model"
        className={select}
        value={filters.model ?? ""}
        onChange={(e) => set({ model: e.target.value || undefined })}
      >
        <option value="">All models</option>
        {facets?.models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <select
        aria-label={override ? "Override status" : "Label status"}
        className={select}
        value={filters.labelStatus}
        onChange={(e) => set({ labelStatus: e.target.value as LabelStatusFilter })}
      >
        <option value="all">{override ? "All override states" : "All label states"}</option>
        <option value="unlabelled">{override ? "Not overridden" : "Not yet labelled"}</option>
        <option value="labelled">{override ? "Overridden" : "Labelled by you"}</option>
      </select>
    </div>
  );
}
