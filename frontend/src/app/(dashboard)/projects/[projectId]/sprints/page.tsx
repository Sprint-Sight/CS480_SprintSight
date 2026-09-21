import { ProjectSprintPageContent } from "@/features/sprints/components/project-sprint-page-content";

export default function ProjectSprintsPage({ params }: { params: { projectId: string } }) {
  return <ProjectSprintPageContent projectId={params.projectId} />;
}
