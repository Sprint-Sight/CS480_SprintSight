import { PageHeader } from "@/components/ui/page-layout";
import type { CollaborationDataset } from "@/features/collaboration/types";

type Props = { data: CollaborationDataset; };
export function CollaborationHeader({ data }: Props) {
  return <PageHeader title="Team Collaboration Analytics" description={data.subtitle} />;
}
