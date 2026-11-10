"use client";

import { BrainCircuit, Download, PencilLine, Play, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-layout";
import { useState } from "react";
import { AssessmentProgressBar } from "@/features/assessment/components/assessment-progress-bar";
import {
  AssessmentFeedbackSections,
  AssessmentScoreVisuals,
} from "@/features/assessment/components/assessment-report-sections";
import {
  toSprintAssessmentReport,
  useAssessmentReport,
} from "@/features/assessment/hooks/use-assessment-report";
import { useAssessmentReportEditor } from "@/features/assessment/hooks/use-assessment-report-editor";
import { useAssessmentExport } from "@/features/assessment/hooks/use-assessment-export";
import { ExportModal } from "@/features/assessment/components/export-modal";
import { InstructorAiFeedbackModal } from "@/features/instructor-feedback/components/instructor-ai-feedback-modal";
import { StudentAssessmentReport } from "@/features/assessment/components/student-assessment-report";
import { useStudentProjectContext } from "@/features/student/hooks/use-student-project-context";
import { useUnsavedChangesGuard } from "@/hooks/use-unsaved-changes-guard";

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
  useUnsavedChangesGuard(
    editor.isEditing && editor.hasChanges,
    "You have unsaved report changes. Leave this page without saving?",
  );

  if (assessment.role === "student") {
    const report = studentContext.report
      ? toSprintAssessmentReport(
          studentContext.report,
          studentContext.project?.team_name,
          studentContext.project?.project_name,
        )
      : null;
    return (
      <PageContainer>
        <StudentAssessmentReport
          report={report}
          projectLabel={
            studentContext.project
              ? `${studentContext.project.team_name} - ${studentContext.project.project_name}`
              : "My project"
          }
          isLoading={studentContext.isLoading}
          error={studentContext.error}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-blue-950 sm:text-3xl">
            AI Assessment Report
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {assessment.report.teamLabel} - {assessment.report.projectLabel} -{" "}
            {assessment.report.sprintLabel}
          </p>
          {assessment.report.generatedAt && (
            <p className="mt-1 text-xs font-medium text-slate-400">
              Generated: {assessment.report.generatedAt}
            </p>
          )}
        </div>
        <div className="flex flex-wrap justify-end gap-3">
          {instructor && (
            <>
              {canEditReport &&
                (!editor.isEditing ? (
                  <Button
                    variant="secondary"
                    onClick={editor.beginEditing}
                    disabled={
                      !assessment.report.reportId ||
                      assessment.isLoadingReport ||
                      assessment.isGenerating
                    }
                    className="self-end"
                  >
                    <PencilLine className="h-4 w-4" aria-hidden="true" />
                    Edit Report
                  </Button>
                ) : (
                  <>
                    {/* While editing, saving is the main action. */}
                    <Button
                      variant="primary"
                      onClick={() => void editor.saveChanges()}
                      disabled={!editor.canSave}
                      isPending={editor.isSaving}
                      className="self-end"
                    >
                      {!editor.isSaving && <Save className="h-4 w-4" aria-hidden="true" />}
                      {editor.isSaving ? "Saving..." : "Save Changes"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={editor.cancelEditing}
                      disabled={editor.isSaving}
                      className="self-end"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                      Cancel
                    </Button>
                  </>
                ))}
              <Button
                variant="secondary"
                onClick={() => setIsFeedbackModalOpen(true)}
                disabled={
                  !scope ||
                  assessment.isLoadingReport ||
                  assessment.isGenerating ||
                  editor.isEditing
                }
                className="self-end"
              >
                <BrainCircuit className="h-4 w-4" aria-hidden="true" />
                Instructor AI Feedback
              </Button>
              <Button
                variant="secondary"
                onClick={assessment.loadLatestReport}
                disabled={
                  !scope ||
                  assessment.isLoadingReport ||
                  assessment.isGenerating ||
                  editor.isEditing
                }
                isPending={assessment.isLoadingReport}
                className="self-end"
              >
                Load Latest
              </Button>
              {/* The page's main action, unless a report edit is in progress. */}
              <Button
                variant={editor.isEditing ? "secondary" : "primary"}
                onClick={assessment.generateAssessment}
                disabled={
                  !scope ||
                  assessment.isGenerating ||
                  assessment.isLoadingReport ||
                  editor.isEditing
                }
                isPending={assessment.isGenerating}
                className="self-end"
              >
                {!assessment.isGenerating && <Play className="h-4 w-4" aria-hidden="true" />}
                {assessment.isGenerating ? "Generating..." : "Generate Assessment"}
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            onClick={handleExportButtonClick}
            disabled={
              !assessment.report.reportId || assessment.isLoadingReport || assessment.isGenerating
            }
            className="self-end"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            Export Report
          </Button>
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
        <div>
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Course / Section
          </span>
          <span className="font-medium text-slate-900">
            {scope?.courseLabel || "No valid course selected"}
          </span>
        </div>
        <div>
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Project / Team
          </span>
          <span className="font-medium text-slate-900">
            {scope?.projectLabel || "No valid project selected"}
          </span>
        </div>
        <div>
          <span className="block text-xs font-semibold uppercase text-slate-500">Sprint</span>
          <span className="font-medium text-slate-900">
            {scope?.sprintId || "No valid sprint selected"}
          </span>
        </div>
      </section>

      {assessment.assessmentMessage &&
        (assessment.isGenerating || assessment.assessmentProgress > 0) && (
          <AssessmentProgressBar
            message={assessment.assessmentMessage}
            progress={assessment.assessmentProgress}
          />
        )}
      {assessment.assessmentError && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {assessment.assessmentError}
        </div>
      )}
      {editor.isEditing && editor.hasChanges && (
        <p className="text-sm font-medium text-amber-700" role="status">
          Unsaved report changes
        </p>
      )}
      {editor.saveError && (
        <p
          className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
          role="alert"
        >
          {editor.saveError}
        </p>
      )}
      {editor.saveMessage && (
        <p
          className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
          role="status"
        >
          {editor.saveMessage}
        </p>
      )}
      <AssessmentScoreVisuals report={editor.isEditing ? editor.draft : assessment.report} />
      <AssessmentFeedbackSections
        report={editor.isEditing ? editor.draft : assessment.report}
        editMode={instructor && editor.isEditing}
        onRubricScoreChange={editor.updateRubricScore}
        onSummaryChange={editor.updateSummary}
      />
      <InstructorAiFeedbackModal
        isOpen={isFeedbackModalOpen}
        scope={scope}
        onClose={() => setIsFeedbackModalOpen(false)}
      />
    </PageContainer>
  );
}
