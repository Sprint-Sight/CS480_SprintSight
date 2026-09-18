import type { ContributionDataset } from "@/features/contributions/types";

type Props = { dataset: ContributionDataset; };
export function ContributionsHeader({ dataset }: Props) { return <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Team Contribution Analysis</h1><p className="mt-1 text-sm text-slate-500">{dataset.teamLabel} - {dataset.projectLabel} - {dataset.sprintLabel} aggregate contribution signals</p></div></div>; }
