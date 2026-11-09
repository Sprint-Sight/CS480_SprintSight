"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { useProjectSprintData } from "@/features/sprints/hooks/use-project-sprint-data";

type Props = { projectId: string; sprintId?: string; assessment?: boolean };

export function ProjectSprintPageContent({ projectId, sprintId, assessment = false }: Props) {
  const { project, sprints, error, isSyncing, syncError } = useProjectSprintData(projectId);
  if (error) return <div className="p-4 sm:p-6 lg:p-8 text-sm text-rose-600">{error}</div>;
  if (!project) return <div className="p-4 sm:p-6 lg:p-8 text-sm text-slate-500">Loading project...</div>;
  const sprint = sprints.find((item) => item.id === sprintId);

  if (sprintId && !sprint && isSyncing) return <div className="p-4 sm:p-6 lg:p-8 text-sm text-slate-500" role="status">Loading sprint data...</div>;
  if (sprintId && !sprint) return <div className="space-y-3 p-4 sm:p-6 lg:p-8"><Link href={`/projects/${projectId}/sprints`} className="text-sm font-medium text-blue-700">Back to project sprints</Link><p className="text-sm text-slate-500">No captured data is available for this sprint.</p></div>;
  if (sprint) return <div className="space-y-5 p-4 sm:p-6 lg:p-8"><Link href={`/projects/${projectId}/sprints`} className="inline-flex items-center gap-1 text-sm font-medium text-slate-500"><ArrowLeft className="h-4 w-4" />Back to project sprints</Link><div><h1 className="text-2xl font-bold text-blue-950 sm:text-3xl">{project.project_name} - {sprint.name}{assessment ? " Assessment" : ""}</h1><p className="mt-1 text-sm text-slate-500">{project.team_name} - {project.course_code}</p></div><section className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Captured Git commits</p><p className="mt-2 text-3xl font-semibold text-blue-900">{sprint.commits}</p><p className="mt-2 text-sm text-slate-500">Captured {new Date(sprint.capturedAt).toLocaleString()}</p>{assessment && <Link href="/assessment-report" className="mt-4 inline-flex text-sm font-semibold text-blue-700">Open Assessment Report</Link>}</section></div>;
  return <div className="space-y-5 p-4 sm:p-6 lg:p-8"><Link href="/projects" className="inline-flex items-center gap-1 text-sm font-medium text-slate-500"><ArrowLeft className="h-4 w-4" />Back to projects</Link><div><h1 className="text-2xl font-bold text-blue-950 sm:text-3xl">{project.project_name}</h1><p className="mt-1 text-sm text-slate-500">{project.team_name} - {project.course_code}</p></div><section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold text-slate-900">Captured sprints</h2>{syncError && <p role="alert" className="mt-3 text-sm text-rose-600">{syncError}</p>}{sprints.length === 0 ? <p className="mt-3 text-sm text-slate-500" role={isSyncing ? "status" : undefined}>{isSyncing ? "Loading captured sprints..." : "No sprint data has been captured for this project."}</p> : <div className="mt-3 space-y-2">{sprints.map((item) => <Link key={item.id} href={`/projects/${projectId}/sprints/${item.id}`} className="block rounded-lg border border-slate-200 p-3 text-sm text-blue-800">{item.name}: {item.commits} commits</Link>)}</div>}</section></div>;
}