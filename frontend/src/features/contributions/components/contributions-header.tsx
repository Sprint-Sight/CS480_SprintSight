import { PageHeader } from "@/components/ui/page-layout";
import type { ContributionDataset } from "@/features/contributions/types";

type Props = { dataset: ContributionDataset; };
export function ContributionsHeader({ dataset }: Props) { return <PageHeader title="Team Contribution Analysis" description={`${dataset.teamLabel} - ${dataset.projectLabel} - ${dataset.sprintLabel} aggregate contribution signals`} />; }
