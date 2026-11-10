import { ProjectSprintPageContent } from "@/features/sprints/components/project-sprint-page-content";

type Props = { params: Promise<{ projectId: string; sprintId: string }> };

// Next 15: dynamic route params are a Promise.
export default async function SprintDetailsPage({ params }: Props) {
  const { projectId, sprintId } = await params;
  return <ProjectSprintPageContent projectId={projectId} sprintId={sprintId} />;
}
