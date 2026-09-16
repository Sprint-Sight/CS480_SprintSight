import type { CollaborationDataset } from "@/features/collaboration/types";

type Props = { data: CollaborationDataset; projectOptions: Array<{ id: string; label: string }>; selectedProjectId: string; onProjectChange: (id: string) => void; };
export function CollaborationHeader({ data, projectOptions, selectedProjectId, onProjectChange }: Props) {
  return <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Team Collaboration Analytics</h1><p className="mt-1 text-sm text-slate-500">{data.subtitle}</p></div><div className="w-full max-w-sm"><label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Project Context</label><select value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)} className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100">{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.label}</option>)}</select></div></div>;
}
