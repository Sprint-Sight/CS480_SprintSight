import type { StudentAssessmentReport, StudentProject } from "@/features/student/student-project-api";

type StudentDashboardSummaryProps = {
  project: StudentProject | null;
  report: StudentAssessmentReport | null;
  isLoading: boolean;
  error: string;
};

export function StudentDashboardSummary({ project, report, isLoading, error }: StudentDashboardSummaryProps) {
  if (isLoading) return <p className="text-sm text-slate-500">Loading your project and assessment status...</p>;
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!project) return <section className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">You are not assigned to a project yet.</section>;
  return <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-sm font-semibold text-slate-500">My Project</p><h2 className="mt-1 text-2xl font-bold text-blue-950">{project.team_name} - {project.project_name}</h2>{report ? <div className="mt-5 grid gap-4 sm:grid-cols-2"><div><p className="text-sm text-slate-500">Latest assessment sprint</p><p className="text-lg font-semibold text-slate-900">{report.sprint_id}</p></div><div><p className="text-sm text-slate-500">Team assessment score</p><p className="text-lg font-semibold text-slate-900">{Math.round(report.team_score.score)}%</p></div></div> : <p className="mt-4 text-sm text-slate-500">No assessment report has been published for your project yet.</p>}</section>;
}
