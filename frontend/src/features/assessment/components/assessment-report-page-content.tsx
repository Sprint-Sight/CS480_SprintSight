"use client";

import { BrainCircuit, Download, Loader2, PencilLine, Play, Save, X } from "lucide-react";
import { useState } from "react";
import {
  AssessmentFeedbackSections,
  AssessmentScoreVisuals,
} from "@/features/assessment/components/assessment-report-sections";
import { toSprintAssessmentReport, useAssessmentReport } from "@/features/assessment/hooks/use-assessment-report";
import { useAssessmentReportEditor } from "@/features/assessment/hooks/use-assessment-report-editor";
import { useAssessmentExport } from "@/features/assessment/hooks/use-assessment-export";
import { ExportModal } from "@/features/assessment/components/export-modal";
import { InstructorAiFeedbackModal } from "@/features/instructor-feedback/components/instructor-ai-feedback-modal";
import { StudentAssessmentReport } from "@/features/assessment/components/student-assessment-report";
import { useStudentProjectContext } from "@/features/student/hooks/use-student-project-context";

export default function AssessmentReportPageContent() {
  const assessment = useAssessmentReport();
  const instructor = assessment.role !== "student";
  const canEditReport = assessment.role === "instructor";
  const studentContext = useStudentProjectContext(assessment.role === "student");
  const scope = assessment.scope;
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  const exportManager = useAssessmentExport();

  const handleExportButtonClick = async () => {
    setIsExportModalOpen(true);
    if (scope?.courseId && scope?.projectId && scope?.sprintId) {
      await exportManager.loadPreview({
        courseId: scope.courseId,
        projectId: scope.projectId,
        sprintId: scope.sprintId,
      });
    }
  };

  const handleCloseExportModal = () => {
    setIsExportModalOpen(false);
    exportManager.reset();
  };

  const handleExportPDF = async () => {
    if (scope?.courseId && scope?.projectId && scope?.sprintId) {
      await exportManager.handleExportPDF({
        courseId: scope.courseId,
        projectId: scope.projectId,
        sprintId: scope.sprintId,
      });
    }
  };

  const handleExportCSV = async () => {
    if (scope?.courseId && scope?.projectId && scope?.sprintId) {
      await exportManager.handleExportCSV({
        courseId: scope.courseId,
        projectId: scope.projectId,
        sprintId: scope.sprintId,
      });
    }
  };

  const editor = useAssessmentReportEditor({
    report: assessment.report,
    backendReport: assessment.backendReport,
    onSaved: assessment.acceptSavedReport,
  });

  if (assessment.role === "student") {
    const report = studentContext.report ? toSprintAssessmentReport(studentContext.report, studentContext.project?.team_name, studentContext.project?.project_name) : null;
    return <div className="space-y-5 p-8"><StudentAssessmentReport report={report} projectLabel={studentContext.project ? `${studentContext.project.team_name} - ${studentContext.project.project_name}` : "My project"} isLoading={studentContext.isLoading} error={studentContext.error} /></div>;
  }

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">AI Assessment Report</h1>
          <p className="mt-1 text-sm text-slate-500">
            {assessment.report.teamLabel} - {assessment.report.projectLabel} - {assessment.report.sprintLabel}
          </p>
          {assessment.report.generatedAt && <p className="mt-1 text-xs font-medium text-slate-400">Generated: {assessment.report.generatedAt}</p>}
        </div>
        <div className="flex flex-wrap justify-end gap-3">
          {instructor && (
            <>
              {canEditReport && (!editor.isEditing ? (
                  <button
                    type="button"
                    onClick={editor.beginEditing}
                    disabled={!assessment.report.reportId || assessment.isLoadingReport || assessment.isGenerating}
                    className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-900 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <PencilLine className="h-4 w-4" />
                    Edit Report
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => void editor.saveChanges()}
                      disabled={!editor.canSave}
                      className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {editor.isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {editor.isSaving ? "Saving..." : "Save Changes"}
                    </button>
                    <button
                      type="button"
                      onClick={editor.cancelEditing}
                      disabled={editor.isSaving}
                      className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
                    >
                      <X className="h-4 w-4" />
                      Cancel
                    </button>
                  </>
                ))}
              <button
                type="button"
                onClick={() => setIsFeedbackModalOpen(true)}
                disabled={!scope || assessment.isLoadingReport || assessment.isGenerating || editor.isEditing}
                className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-900 disabled:opacity-50"
              >
                <BrainCircuit className="h-4 w-4" />
                Instructor AI Feedback
              </button>
              <button
                type="button"
                onClick={assessment.loadLatestReport}
                disabled={!scope || assessment.isLoadingReport || assessment.isGenerating || editor.isEditing}
                className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold disabled:opacity-50"
              >
                {assessment.isLoadingReport && <Loader2 className="h-4 w-4 animate-spin" />}
                Load Latest
              </button>
              <button
                type="button"
                onClick={assessment.generateAssessment}
                disabled={!scope || assessment.isGenerating || assessment.isLoadingReport || editor.isEditing}
                className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                {assessment.isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {assessment.isGenerating ? "Generating..." : "Generate Assessment"}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={handleExportButtonClick}
            disabled={!assessment.report.reportId || assessment.isLoadingReport || assessment.isGenerating}
            className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            Export Report
          </button>
        </div>
      </div>

      <ExportModal
        isOpen={isExportModalOpen}
        onClose={handleCloseExportModal}
        previewData={exportManager.previewData}
        isLoading={exportManager.state === "loading-preview"}
        isExporting={exportManager.state === "exporting"}
        selectedFormat={exportManager.selectedFormat}
        error={exportManager.error}
        onExportPDF={handleExportPDF}
        onExportCSV={handleExportCSV}
      />

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
      {editor.isEditing && editor.hasChanges && (
        <p className="text-sm font-medium text-amber-700" role="status">Unsaved report changes</p>
      )}
      {editor.saveError && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" role="alert">{editor.saveError}</p>}
      {editor.saveMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800" role="status">{editor.saveMessage}</p>}
      <AssessmentScoreVisuals report={editor.isEditing ? editor.draft : assessment.report} />
      <AssessmentFeedbackSections
        report={editor.isEditing ? editor.draft : assessment.report}
        editMode={instructor && editor.isEditing}
        onRubricScoreChange={editor.updateRubricScore}
        onSummaryChange={editor.updateSummary}
      />
      <InstructorAiFeedbackModal isOpen={isFeedbackModalOpen} scope={scope} onClose={() => setIsFeedbackModalOpen(false)} />
    </div>
  );
}