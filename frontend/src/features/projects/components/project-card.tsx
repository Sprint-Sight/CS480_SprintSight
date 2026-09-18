import Link from "next/link";
import { Edit, Trash2, TrendingUp, UserMinus, UserPlus, Users } from "lucide-react";

import type { Project } from "@/features/projects/types";
import { getStatusStyles } from "@/features/projects/components/projects-api";

type ProjectCardProps = {
  project: Project;
  onEdit: (project: Project, event: React.MouseEvent) => void;
  onDelete: (projectId: string, event: React.MouseEvent) => void;
  onAddMember: (projectId: string, event: React.MouseEvent) => void;
  onRemoveMember: (projectId: string, userId: string, event: React.MouseEvent) => void;
};

export function ProjectCard({ project, onEdit, onDelete, onAddMember, onRemoveMember }: ProjectCardProps) {
  return (
    <Link
      href={`/projects/${project.id}/sprints`}
      className="group relative flex flex-col justify-between rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md"
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold leading-tight text-blue-950 group-hover:text-blue-700">
              {project.project_name}
            </h2>
            <p className="mt-0.5 text-sm font-medium text-slate-500">{project.team_name}</p>
          </div>

          <div className="flex items-center gap-1.5">
            <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${getStatusStyles(project.status)}`}>
              {project.status}
            </span>

            <button
              type="button"
              onClick={(event) => onEdit(project, event)}
              title="Edit Project"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-blue-600"
            >
              <Edit className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={(event) => onDelete(project.id, event)}
              title="Delete Project"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <p className="mt-3 text-xs font-medium uppercase tracking-wider text-slate-400">{project.module}</p>

        <div className="mt-4 flex items-center justify-between text-slate-500">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-slate-400" />
            <div className="flex flex-wrap items-center gap-1.5">
              {project.members.map((member) => (
                <div
                  key={member.id}
                  className="inline-flex items-center gap-1 rounded-md border border-blue-100 bg-blue-50 py-1 pl-2 pr-1 text-xs font-medium text-blue-800"
                >
                  <span className="max-w-24 truncate" title={member.full_name}>{member.full_name}</span>
                  <button
                    type="button"
                    onClick={(event) => onRemoveMember(project.id, member.id, event)}
                    className="inline-flex h-6 w-6 items-center justify-center rounded-md text-rose-600 transition hover:bg-rose-100"
                    title="Remove member"
                    aria-label={`Remove ${member.full_name} from project`}
                  >
                    <UserMinus className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={(event) => onAddMember(project.id, event)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 text-sm font-semibold text-blue-700 transition hover:bg-blue-100"
          >
            <UserPlus className="h-4 w-4" />
            Add member
          </button>
        </div>
      </div>

      <div className="mt-6 border-t border-slate-100 pt-4">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-1.5 font-semibold text-blue-900">
            <TrendingUp className="h-4 w-4" />
            {project.score}/100
          </div>
          <div className="text-slate-500">{project.completion}% complete</div>
        </div>

        <div className="mt-2 h-2 rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-blue-700" style={{ width: `${project.completion}%` }} />
        </div>
      </div>
    </Link>
  );
}
