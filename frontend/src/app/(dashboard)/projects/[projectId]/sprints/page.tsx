import { ProjectSprintPageContent } from "@/features/sprints/components/project-sprint-page-content";

type Props = { params: Promise<{ projectId: string }> };

// Next 15: dynamic route params are a Promise.
export default async function ProjectSprintsPage({ params }: Props) {
  const { projectId } = await params;
  return <ProjectSprintPageContent projectId={projectId} />;
}
