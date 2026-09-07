import { X } from "lucide-react";

import type { Project } from "@/features/projects/types";
import type { ProjectFormValues } from "@/features/projects/components/projects-api";

type ProjectModalProps = {
  isOpen: boolean;
  editingProject: Project | null;
  projectForm: ProjectFormValues;
  onClose: () => void;
  onSave: () => void;
  setProjectForm: React.Dispatch<React.SetStateAction<ProjectFormValues>>;
};

export function ProjectModal({ isOpen, editingProject, projectForm, onClose, onSave, setProjectForm }: ProjectModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto bg-slate-950/40 p-4 sm:p-6">
      <div className="mx-auto my-4 flex w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl sm:my-8">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              {editingProject ? "Edit Project" : "Create New Project"}
            </h2>
            <p className="mt-0.5 text-sm text-slate-500">Set up the project details for the selected course.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close project form" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-5">
          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Project Name</span>
            <input
              type="text"
              value={projectForm.project_name}
              onChange={(event) => setProjectForm((current) => ({ ...current, project_name: event.target.value }))}
              required
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="e.g. SprintSight Dashboard"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Team Name</span>
            <input
              type="text"
              value={projectForm.team_name}
              onChange={(event) => setProjectForm((current) => ({ ...current, team_name: event.target.value }))}
              required
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="e.g. Group Alpha"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Description <span className="font-normal text-slate-400">(optional)</span></span>
            <textarea
              value={projectForm.description}
              onChange={(event) => setProjectForm((current) => ({ ...current, description: event.target.value }))}
              className="min-h-20 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="What is this team building?"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Jira Email</span>
            <input
              type="email"
              value={projectForm.jira_email}
              onChange={(event) => setProjectForm((current) => ({ ...current, jira_email: event.target.value }))}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="instructor@example.com"
            />
          </label>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="block min-w-0 space-y-1">
              <span className="text-sm font-medium text-slate-700">Jira Domain</span>
              <input
                type="text"
                value={projectForm.jira_domain}
                onChange={(event) => setProjectForm((current) => ({ ...current, jira_domain: event.target.value }))}
                className="h-10 min-w-0 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="https://company.atlassian.net"
              />
            </label>
            <label className="block min-w-0 space-y-1">
              <span className="text-sm font-medium text-slate-700">Jira Project Key</span>
              <input
                type="text"
                value={projectForm.jira_project_key}
                onChange={(event) => setProjectForm((current) => ({ ...current, jira_project_key: event.target.value }))}
                className="h-10 min-w-0 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="TYH"
              />
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Jira API Token <span className="font-normal text-slate-400">(optional)</span></span>
            <input
              type="password"
              value={projectForm.jira_api_token}
              onChange={(event) => setProjectForm((current) => ({ ...current, jira_api_token: event.target.value }))}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="Enter only if this project uses its own Jira credentials"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">GitHub Repository URL <span className="font-normal text-slate-400">(optional)</span></span>
            <input
              type="url"
              value={projectForm.github_repo_url}
              onChange={(event) => setProjectForm((current) => ({ ...current, github_repo_url: event.target.value }))}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="https://github.com/org/repository"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">Local Repository Path <span className="font-normal text-slate-400">(optional)</span></span>
            <input
              type="text"
              value={projectForm.local_repo_path}
              onChange={(event) => setProjectForm((current) => ({ ...current, local_repo_path: event.target.value }))}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="team-alpha/repository"
            />
          </label>

        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-slate-200 px-5 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            className="h-10 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white hover:bg-blue-800"
          >
            {editingProject ? "Update Project" : "Create Project"}
          </button>
        </div>
      </div>
    </div>
  );
}
