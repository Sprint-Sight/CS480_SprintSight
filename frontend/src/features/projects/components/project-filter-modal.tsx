import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { ProjectFilters } from "@/features/projects/hooks/use-project-filters";

type SortOption = { value: ProjectFilters["sortBy"]; label: string };

type ProjectFilterModalProps = {
  isOpen: boolean;
  draftFilters: ProjectFilters;
  moduleOptions: string[];
  sortOptions: ReadonlyArray<SortOption>;
  onDraftChange: <K extends keyof ProjectFilters>(key: K, value: ProjectFilters[K]) => void;
  onClearForm: () => void;
  onApply: () => void;
  onClose: () => void;
};

const selectClassName =
  "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300";

export function ProjectFilterModal({
  isOpen,
  draftFilters,
  moduleOptions,
  sortOptions,
  onDraftChange,
  onClearForm,
  onApply,
  onClose,
}: ProjectFilterModalProps) {
  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent dismissOnOutsideClick className="max-w-2xl rounded-2xl border border-slate-200">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <DialogTitle className="text-lg font-semibold text-slate-900">Filter and sort projects</DialogTitle>
            <DialogDescription className="text-sm text-slate-500">
              Adjust criteria, then apply to refresh the project list.
            </DialogDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            ×
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 px-5 py-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Team name</span>
            <input
              type="text"
              value={draftFilters.teamName}
              onChange={(event) => onDraftChange("teamName", event.target.value)}
              placeholder="e.g. Team Alpha"
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none focus:border-blue-300"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Module</span>
            <select
              value={draftFilters.module}
              onChange={(event) => onDraftChange("module", event.target.value)}
              className={selectClassName}
            >
              {moduleOptions.map((moduleOption) => (
                <option key={moduleOption} value={moduleOption}>{moduleOption}</option>
              ))}
            </select>
          </label>

          <label className="space-y-1.5 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">Sort by</span>
            <select
              value={draftFilters.sortBy}
              onChange={(event) => onDraftChange("sortBy", event.target.value as ProjectFilters["sortBy"])}
              className={selectClassName}
            >
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button
            type="button"
            onClick={onClearForm}
            className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Clear form
          </button>
          <button
            type="button"
            onClick={onApply}
            className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800"
          >
            Apply filters
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
