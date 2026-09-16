import type { CollaborationDataset } from "@/features/collaboration/types";

type Props = { data: CollaborationDataset; };
export function CollaborationHeader({ data }: Props) {
  return <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Team Collaboration Analytics</h1><p className="mt-1 text-sm text-slate-500">{data.subtitle}</p></div></div>;
}
