"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  clearActiveAssessmentJob,
  readActiveAssessmentJob,
  saveActiveAssessmentJob,
  type ActiveAssessmentJob,
} from "@/features/assessment/active-assessment-job";
import { resolveAssessmentScope } from "@/features/assessment/assessment-scope";
import {
  getSupportedDimension,
  type BackendAssessmentReport,
} from "@/features/assessment/assessment-api";
import { readScope, subscribeScope } from "@/features/ingestion/scope-store";
import { scopeProjectsQueryOptions } from "@/features/projects/course-projects-api";
import { isUuid } from "@/features/projects/components/projects-api";
import { API_BASE_URL, apiRequest, buildAuthHeaders, getErrorMessage } from "@/lib/api/client";
import type { SprintAssessmentReport } from "@/features/assessment/types";
import { useSession } from "@/lib/auth/session";

type AssessmentProjectOption = {
  id: string;
  courseId?: string;
  courseLabel?: string;
  label: string;
};
type JobEvent = { status?: string; progress?: number; message?: string; error_message?: string };

// Checked structurally (ApiError.status) so tests can mock the client module freely.
function isNotFound(error: unknown) {
  const status = (error as { status?: unknown } | null)?.status;
  return status === 404;
}

const labels: Record<string, string> = {
  requirements: "Requirements",
  code_quality: "Code Quality",
  testing: "Testing",
  documentation: "Documentation",
  collaboration: "Collaboration",
  cicd: "CI/CD",
  delivery: "Delivery",
  quality: "Quality",
};
const formatLabel = (key: string) =>
  labels[key] || key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const normalizeRubricScore = (score: number) => (score >= 0 && score <= 10 ? score * 10 : score);
const emptyReport = (projectId = "", sprintId = ""): SprintAssessmentReport => ({
  projectId,
  sprintId,
  sprintLabel: sprintId || "No sprint selected",
  teamLabel: "No project selected",
  projectLabel: "No assessment report",
  generatedAt: "",
  overallScore: 0,
  overallGrade: "",
  overallSummary: "No assessment data is available for the selected course, project, and sprint.",
  rubricScores: [],
  strengths: [],
  weaknesses: [],
  recommendations: [],
  narrativeFeedback: [],
});
export const toSprintAssessmentReport = (
  data: BackendAssessmentReport,
  teamLabel = "Project team",
  projectLabel = "Project",
): SprintAssessmentReport => ({
  reportId: data.report_id,
  projectId: data.project_id,
  sprintId: data.sprint_id,
  sprintLabel: data.sprint_id,
  teamLabel,
  projectLabel,
  generatedAt: new Date(data.generated_at).toLocaleString(),
  overallScore: Math.round(data.team_score.score),
  overallGrade:
    data.team_score.overall_grade || "—",
  overallSummary: data.team_score.rationale,
  rubricScores: Object.entries(data.rubric_scores || {}).map(([categoryKey, detail]) => {
    const dimension = getSupportedDimension(categoryKey);
    const savedScore = dimension ? data[dimension.backendScoreKey] : undefined;
    const savedJustification = dimension ? data[dimension.backendJustificationKey] : undefined;
    const shouldUseSavedValues = data.override === true;
    return {
      categoryKey,
      category: formatLabel(categoryKey),
      score: Math.round(
        shouldUseSavedValues && typeof savedScore === "number"
          ? savedScore
          : normalizeRubricScore(detail.score),
      ),
      justification:
        shouldUseSavedValues && typeof savedJustification === "string"
          ? savedJustification
          : detail.justification || "No justification provided.",
      evidenceCitations: detail.evidence_citations || [],
    };
  }),
  strengths: data.strengths || [],
  weaknesses: data.weaknesses || [],
  recommendations: data.recommendations || [],
  narrativeFeedback: [],
});

export function useAssessmentReport() {
  const [projectOptions, setProjectOptions] = useState<AssessmentProjectOption[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [sprintId, setSprintId] = useState("sprint-1");
  const [report, setReport] = useState(() => emptyReport());
  const [backendReport, setBackendReport] = useState<BackendAssessmentReport | null>(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [assessmentProgress, setAssessmentProgress] = useState(0);
  const [assessmentMessage, setAssessmentMessage] = useState("");
  const [assessmentError, setAssessmentError] = useState("");
  const session = useSession();
  const queryClient = useQueryClient();
  const role: "student" | "instructor" | "admin" | null = session ? (session.user?.role ?? "student") : null;

  const clearLiveReport = (projectId: string, sprint: string) => {
    setBackendReport(null);
    setReport(emptyReport(projectId, sprint));
  };

  const resolveScope = () =>
    resolveAssessmentScope({
      selectedCourseId,
      selectedProjectId,
      selectedSprintId: sprintId,
      projects: projectOptions,
    });

  const loadLatestReport = useCallback(async () => {
    const scope = resolveAssessmentScope({
      selectedCourseId,
      selectedProjectId,
      selectedSprintId: sprintId,
      projects: projectOptions,
    });
    if (!scope || !isUuid(scope.projectId)) {
      setBackendReport(null);
      setReport(emptyReport(selectedProjectId, sprintId));
      setAssessmentError(
        "The selected course, project, and sprint must refer to the same project scope.",
      );
      return;
    }
    setIsLoadingReport(true);
    setAssessmentError("");
    try {
      const data = await apiRequest<BackendAssessmentReport>(
        `/assessments/latest?course_id=${encodeURIComponent(scope.courseId)}&project_id=${encodeURIComponent(scope.projectId)}&sprint_id=${encodeURIComponent(scope.sprintId)}`,
      );
      setBackendReport(data);
      setReport(
        toSprintAssessmentReport(
          data,
          scope.projectLabel.split(" - ")[0] || "Project team",
          scope.projectLabel.split(" - ").slice(1).join(" - ") || scope.projectLabel,
        ),
      );
    } catch (error) {
      clearLiveReport(scope.projectId, scope.sprintId);
      if (!isNotFound(error)) {
        setAssessmentError(
          getErrorMessage(error, "Failed to load the latest assessment."),
        );
      }
    } finally {
      setIsLoadingReport(false);
    }
  }, [selectedCourseId, selectedProjectId, sprintId, projectOptions]);

  function acceptSavedReport(data: BackendAssessmentReport) {
    setBackendReport(data);
    setReport(toSprintAssessmentReport(data, report.teamLabel, report.projectLabel));
  }

  async function generateAssessment() {
    const scope = resolveScope();
    if (!scope || !isUuid(scope.projectId)) {
      setAssessmentError(
        "The selected course, project, and sprint must refer to the same project scope.",
      );
      return;
    }
    setAssessmentError("");
    setIsGenerating(true);
    setAssessmentProgress(0);
    setAssessmentMessage("Starting assessment...");
    try {
      const job = await apiRequest<{ job_id: string }>("/assessments/assess", {
        method: "POST",
        body: JSON.stringify({
          course_id: scope.courseId,
          project_id: scope.projectId,
          sprint_id: scope.sprintId,
        }),
      });
      saveActiveAssessmentJob({
        jobId: job.job_id,
        courseId: scope.courseId,
        projectId: scope.projectId,
        sprintId: scope.sprintId,
      });
      await monitorJob(job);
    } catch (error) {
      setAssessmentError(getErrorMessage(error, "Assessment generation failed."));
    } finally {
      clearActiveAssessmentJob();
      setIsGenerating(false);
    }
  }

  async function monitorJob(job: { job_id: string }) {
    // Streamed (SSE) response, so it is read directly instead of through apiRequest.
    const response = await fetch(`${API_BASE_URL}/assessments/jobs/${job.job_id}/events`, {
      headers: buildAuthHeaders(),
    });
    if (!response.ok || !response.body) throw new Error("Could not monitor assessment progress.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    while (!finished) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const event of events) {
        const line = event.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const data = JSON.parse(line.slice(6)) as JobEvent;
        setAssessmentProgress(data.progress ?? 0);
        setAssessmentMessage(data.message || data.status || "Assessment in progress...");
        if (data.status === "failed") throw new Error(data.error_message || "Assessment failed.");
        if (data.status === "completed") finished = true;
      }
    }
    await loadLatestReport();
  }

  async function resumeActiveJob(stored: ActiveAssessmentJob) {
    setAssessmentError("");
    setIsGenerating(true);
    setAssessmentMessage("Resuming assessment...");
    try {
      await monitorJob({ job_id: stored.jobId });
    } catch (error) {
      const message = getErrorMessage(error, "Assessment generation failed.");
      if (!/Could not monitor/.test(message)) setAssessmentError(message);
    } finally {
      clearActiveAssessmentJob();
      setIsGenerating(false);
    }
  }

  const resumedJobRef = useRef(false);
  useEffect(() => {
    if (
      !role ||
      role === "student" ||
      resumedJobRef.current ||
      !selectedProjectId ||
      projectOptions.length === 0
    )
      return;
    const scope = resolveScope();
    const stored = readActiveAssessmentJob();
    if (
      !stored ||
      !scope ||
      stored.projectId !== scope.projectId ||
      stored.sprintId !== scope.sprintId
    )
      return;
    resumedJobRef.current = true;
    void resumeActiveJob(stored);
  }, [role, selectedProjectId, sprintId, projectOptions]);

  useEffect(() => {
    if (role === "student") return;
    const refreshScope = () => {
      const scope = readScope();
      setSelectedCourseId(scope.selectedCourseId);
      setSelectedProjectId(scope.selectedProjectId);
      setSprintId(scope.selectedSprintId);
    };
    refreshScope();
    return subscribeScope(refreshScope);
  }, [role]);
  useEffect(() => {
    if (!role || role === "student") return;
    async function loadProjects() {
      try {
        const groups = await queryClient.fetchQuery(scopeProjectsQueryOptions(queryClient));
        const options = groups.flatMap(({ course, projects }) =>
          projects.map((project) => ({
            id: project.id,
            courseId: course.id,
            courseLabel: `${course.code} - ${course.name} - ${course.section}`,
            label: `${project.team_name} - ${project.project_name}`,
          })),
        );
        setProjectOptions(options);
      } catch (error) {
        setProjectOptions([]);
        setAssessmentError(
          getErrorMessage(error, "Could not load assessment projects."),
        );
      }
    }
    void loadProjects();
  }, [role, queryClient]);
  useEffect(() => {
    if (role !== "student" && selectedProjectId) void loadLatestReport();
  }, [role, selectedProjectId, sprintId, projectOptions, loadLatestReport]);
  const scope = resolveScope();
  return {
    report,
    backendReport,
    role,
    isLoadingReport,
    isGenerating,
    assessmentProgress,
    assessmentMessage,
    assessmentError,
    scope,
    loadLatestReport,
    generateAssessment,
    acceptSavedReport,
  };
}
