"use client";

import { Download, Loader2, Play } from "lucide-react";
import {
  AssessmentFeedbackSections,
  AssessmentScoreVisuals,
} from "@/features/assessment/components/assessment-report-sections";
import { useAssessmentReport } from "@/features/assessment/hooks/use-assessment-report";

export default function AssessmentReportPageContent() {
  const assessment = useAssessmentReport();
  const instructor = assessment.role !== "student";
  const scope = assessment.scope;

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">AI Assessment Report</h1>
          <p className="mt-1 text-sm text-slate-500">
            {assessment.report.teamLabel} - {assessment.report.projectLabel} - {assessment.report.sprintLabel}
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-3">
          {instructor && (
            <>
              <button
                type="button"
                onClick={assessment.loadLatestReport}
                disabled={!scope || assessment.isLoadingReport || assessment.isGenerating}
                className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold disabled:opacity-50"
              >
                {assessment.isLoadingReport && <Loader2 className="h-4 w-4 animate-spin" />}
                Load Latest
              </button>
              <button
                type="button"
                onClick={assessment.generateAssessment}
                disabled={!scope || assessment.isGenerating || assessment.isLoadingReport}
                className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                {assessment.isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {assessment.isGenerating ? "Generating..." : "Generate Assessment"}
              </button>
            </>
          )}
          <button type="button" className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white">
            <Download className="h-4 w-4" />
            Download PDF
          </button>
        </div>
      </div>

      <section className="grid gap-3 border-y border-slate-200 py-4 text-sm sm:grid-cols-3">
        <div><span className="block text-xs font-semibold uppercase text-slate-500">Course / Section</span><span className="font-medium text-slate-900">{scope?.courseLabel || "No valid course selected"}</span></div>
        <div><span className="block text-xs font-semibold uppercase text-slate-500">Project / Team</span><span className="font-medium text-slate-900">{scope?.projectLabel || "No valid project selected"}</span></div>
        <div><span className="block text-xs font-semibold uppercase text-slate-500">Sprint</span><span className="font-medium text-slate-900">{scope?.sprintId || "No valid sprint selected"}</span></div>
      </section>

      {assessment.assessmentMessage && (assessment.isGenerating || assessment.assessmentProgress > 0) && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">
          <div className="flex justify-between"><span>{assessment.assessmentMessage}</span><span>{assessment.assessmentProgress}%</span></div>
          <div className="mt-2 h-2 rounded-full bg-blue-100"><div className="h-full rounded-full bg-blue-800" style={{ width: `${assessment.assessmentProgress}%` }} /></div>
        </div>
      )}
      {assessment.assessmentError && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{assessment.assessmentError}</div>}
      <AssessmentScoreVisuals report={assessment.report} />
      <AssessmentFeedbackSections report={assessment.report} />
    </div>
  );
}