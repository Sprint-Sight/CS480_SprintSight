import { AssessmentFeedbackSections, AssessmentScoreVisuals } from "@/features/assessment/components/assessment-report-sections";
import type { SprintAssessmentReport } from "@/features/assessment/types";

type StudentAssessmentReportProps = {
  report: SprintAssessmentReport | null;
  projectLabel: string;
  isLoading: boolean;
  error: string;
};

export function StudentAssessmentReport({ report, projectLabel, isLoading, error }: StudentAssessmentReportProps) {
  if (isLoading) return <p className="text-sm text-slate-500">Loading your assessment reports...</p>;
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!report) return <section className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="text-lg font-semibold text-slate-900">No assessment report available</h2><p className="mt-2 text-sm text-slate-500">An instructor must publish an assessment before it appears here.</p></section>;
  return <><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">AI Assessment Report</h1><p className="mt-1 text-sm text-slate-500">{projectLabel} - {report.sprintLabel}</p>{report.generatedAt && <p className="mt-1 text-xs font-medium text-slate-400">Generated: {report.generatedAt}</p>}</div><AssessmentScoreVisuals report={report} /><AssessmentFeedbackSections report={report} /></>;
}
