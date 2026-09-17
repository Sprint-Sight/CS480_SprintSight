import { ProjectSprintPageContent } from "@/features/sprints/components/project-sprint-page-content";

export default function SprintAssessmentEntryPage({ params }: { params: { projectId: string; sprintId: string } }) {
  return <ProjectSprintPageContent projectId={params.projectId} sprintId={params.sprintId} assessment />;
}