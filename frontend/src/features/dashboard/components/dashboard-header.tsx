import type { DashboardProject, DashboardRole } from "@/features/dashboard/types";

type DashboardHeaderProps = {
  role: DashboardRole;
  fullName: string;
  projects: DashboardProject[];
  selectedProjectId: string;
  sprintId: string;
  onProjectChange: (projectId: string) => void;
  onSprintChange: (sprintId: string) => void;
};

export function DashboardHeader({ role, fullName, projects, selectedProjectId, sprintId, onProjectChange, onSprintChange }: DashboardHeaderProps) {
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{role === "student" ? "My Dashboard" : "Dashboard"}</h1>
        <p className="mt-1 text-slate-500">{fullName || (role === "student" ? "Student" : "Instructor")} - {selectedProject?.label || "Loading project scope"}</p>
        {projects.length > 1 && (
          <select value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)} className="mt-3 h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
            {projects.map((project) => <option key={project.id} value={project.id}>{project.label}</option>)}
          </select>
        )}
      </div>
      <label className="space-y-1 text-sm text-slate-600">
        <span className="block text-xs font-semibold uppercase tracking-wider">Sprint</span>
        <input value={sprintId} onChange={(event) => onSprintChange(event.target.value)} onBlur={() => onSprintChange(sprintId.trim() || "sprint-1")} className="h-10 rounded-lg border border-slate-200 bg-white px-3" />
      </label>
    </div>
  );
}
