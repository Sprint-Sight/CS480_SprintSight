import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AssessmentReportPageContent from "@/features/assessment/components/assessment-report-page-content";

const editorState = { isEditing: false };

vi.mock("@/features/assessment/hooks/use-assessment-report", () => ({
  toSprintAssessmentReport: vi.fn(),
  useAssessmentReport: () => ({
    role: "instructor",
    scope: {
      courseId: "c1",
      projectId: "p1",
      sprintId: "sprint-1",
      courseLabel: "",
      projectLabel: "",
    },
    report: {
      reportId: "r1",
      teamLabel: "Team",
      projectLabel: "Project",
      sprintLabel: "Sprint 1",
      generatedAt: "",
    },
    backendReport: null,
    isLoadingReport: false,
    isGenerating: false,
    assessmentProgress: 0,
    assessmentMessage: "",
    assessmentError: "",
    loadLatestReport: vi.fn(),
    generateAssessment: vi.fn(),
    acceptSavedReport: vi.fn(),
  }),
}));

vi.mock("@/features/assessment/hooks/use-assessment-report-editor", () => ({
  useAssessmentReportEditor: () => ({
    isEditing: editorState.isEditing,
    hasChanges: false,
    canSave: true,
    isSaving: false,
    draft: null,
    saveError: "",
    saveMessage: "",
    beginEditing: vi.fn(),
    cancelEditing: vi.fn(),
    saveChanges: vi.fn(),
    updateRubricScore: vi.fn(),
    updateSummary: vi.fn(),
  }),
}));

vi.mock("@/features/assessment/hooks/use-assessment-export", () => ({
  useAssessmentExport: () => ({
    previewData: null,
    state: "idle",
    selectedFormat: null,
    error: "",
    loadPreview: vi.fn(),
    reset: vi.fn(),
    handleExportPDF: vi.fn(),
    handleExportCSV: vi.fn(),
  }),
}));

vi.mock("@/features/student/hooks/use-student-project-context", () => ({
  useStudentProjectContext: () => ({ project: null, report: null, isLoading: false, error: "" }),
}));
vi.mock("@/hooks/use-unsaved-changes-guard", () => ({ useUnsavedChangesGuard: vi.fn() }));

// The report body, progress bar and modals are not under test here.
vi.mock("@/features/assessment/components/assessment-report-sections", () => ({
  AssessmentScoreVisuals: () => null,
  AssessmentFeedbackSections: () => null,
}));
vi.mock("@/features/assessment/components/assessment-progress-bar", () => ({
  AssessmentProgressBar: () => null,
}));
vi.mock("@/features/assessment/components/export-modal", () => ({ ExportModal: () => null }));
vi.mock("@/features/instructor-feedback/components/instructor-ai-feedback-modal", () => ({
  InstructorAiFeedbackModal: () => null,
}));

// The shared Button's primary variant is the only one with this fill.
const PRIMARY_CLASS = "bg-blue-700";
const primaryButtons = () =>
  screen.getAllByRole("button").filter((button) => button.className.includes(PRIMARY_CLASS));

describe("AssessmentReportPageContent action buttons", () => {
  beforeEach(() => {
    editorState.isEditing = false;
  });

  it("shows exactly one primary action: Generate Assessment", () => {
    render(<AssessmentReportPageContent />);

    expect(primaryButtons().map((button) => button.textContent)).toEqual(["Generate Assessment"]);
    expect(screen.getByRole("button", { name: /Export Report/ }).className).not.toContain(
      PRIMARY_CLASS,
    );
  });

  it("makes Save Changes the only primary action while editing", () => {
    editorState.isEditing = true;
    render(<AssessmentReportPageContent />);

    expect(primaryButtons().map((button) => button.textContent)).toEqual(["Save Changes"]);
    expect(screen.getByRole("button", { name: /Generate Assessment/ }).className).not.toContain(
      PRIMARY_CLASS,
    );
  });

  it("gives every header button the shared focus ring", () => {
    render(<AssessmentReportPageContent />);

    for (const button of screen.getAllByRole("button")) {
      expect(button.className).toContain("focus-visible:ring-2");
    }
  });
});
