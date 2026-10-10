"use client";

import { useEffect, useState } from "react";

import { resolveAssessmentScope } from "@/features/assessment/assessment-scope";
import {
  getSupportedDimension,
  type BackendAssessmentReport,
} from "@/features/assessment/assessment-api";
import { readIngestionState } from "@/features/ingestion/state";
import { API_BASE_URL, apiRequest, getAuthToken, isUuid } from "@/features/projects/components/projects-api";
import type { SprintAssessmentReport } from "@/features/assessment/types";

type AssessmentProjectOption = { id: string; courseId?: string; courseLabel?: string; label: string };
type JobEvent = { status?: string; progress?: number; message?: string; error_message?: string };

const labels: Record<string, string> = { requirements: "Requirements", code_quality: "Code Quality", testing: "Testing", documentation: "Documentation", collaboration: "Collaboration", cicd: "CI/CD", delivery: "Delivery", quality: "Quality" };
const formatLabel = (key: string) => labels[key] || key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const normalizeRubricScore = (score: number) => score >= 0 && score <= 10 ? score * 10 : score;
const emptyReport = (projectId = "", sprintId = ""): SprintAssessmentReport => ({ projectId, sprintId, sprintLabel: sprintId || "No sprint selected", teamLabel: "No project selected", projectLabel: "No assessment report", generatedAt: "", overallScore: 0, overallGrade: "", overallSummary: "No assessment data is available for the selected course, project, and sprint.", rubricScores: [], strengths: [], weaknesses: [], recommendations: [], narrativeFeedback: [] });
export const toSprintAssessmentReport = (data: BackendAssessmentReport, teamLabel = "Project team", projectLabel = "Project"): SprintAssessmentReport => ({
  reportId: data.report_id,
  projectId: data.project_id,
  sprintId: data.sprint_id,
  sprintLabel: data.sprint_id,
  teamLabel,
  projectLabel,
  generatedAt: new Date(data.generated_at).toLocaleString(),
  overallScore: Math.round(data.team_score.score),
  overallGrade: data.team_score.overall_grade || (data.team_score.score >= 85 ? "A" : data.team_score.score >= 75 ? "B" : "C"),
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
  const [role, setRole] = useState<"student" | "instructor" | "admin" | null>(null);

  const clearLiveReport = (projectId: string, sprint: string) => {
    setBackendReport(null);
    setReport(emptyReport(projectId, sprint));
  };

  const resolveScope = () => resolveAssessmentScope({ selectedCourseId, selectedProjectId, selectedSprintId: sprintId, projects: projectOptions });

  async function loadLatestReport() {
    const scope = resolveScope();
    if (!scope || !isUuid(scope.projectId)) {
      setBackendReport(null);
      setReport(emptyReport(selectedProjectId, sprintId));
      setAssessmentError("The selected course, project, and sprint must refer to the same project scope.");
      return;
    }
    setIsLoadingReport(true); setAssessmentError("");
    try {
      const data = await apiRequest<BackendAssessmentReport>(`/assessments/latest?course_id=${encodeURIComponent(scope.courseId)}&project_id=${encodeURIComponent(scope.projectId)}&sprint_id=${encodeURIComponent(scope.sprintId)}`);
      setBackendReport(data);
      setReport(toSprintAssessmentReport(data, scope.projectLabel.split(" - ")[0] || "Project team", scope.projectLabel.split(" - ").slice(1).join(" - ") || scope.projectLabel));
    } catch (error) { clearLiveReport(scope.projectId, scope.sprintId); setAssessmentError(error instanceof Error ? error.message : "Failed to load the latest assessment."); }
    finally { setIsLoadingReport(false); }
  }

  function acceptSavedReport(data: BackendAssessmentReport) {
    setBackendReport(data);
    setReport(toSprintAssessmentReport(data, report.teamLabel, report.projectLabel));
  }

  async function generateAssessment() {
    const scope = resolveScope();
    if (!scope || !isUuid(scope.projectId)) { setAssessmentError("The selected course, project, and sprint must refer to the same project scope."); return; }
    setAssessmentError(""); setIsGenerating(true); setAssessmentProgress(0); setAssessmentMessage("Starting assessment...");
    try {
      const modelName = localStorage.getItem("sprintsight-selected-model") || "sprintsight-llama";
      const job = await apiRequest<{ job_id: string }>("/assessments/assess", { method: "POST", body: JSON.stringify({ course_id: scope.courseId, project_id: scope.projectId, sprint_id: scope.sprintId, model_name: modelName }) });
      const token = getAuthToken(); if (!token) throw new Error("Your session has expired. Please log in again.");
      const response = await fetch(`${API_BASE_URL}/assessments/jobs/${job.job_id}/events`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok || !response.body) throw new Error("Could not monitor assessment progress.");
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let finished = false;
      while (!finished) { const chunk = await reader.read(); if (chunk.done) break; buffer += decoder.decode(chunk.value, { stream: true }); const events = buffer.split("\n\n"); buffer = events.pop() || ""; for (const event of events) { const line = event.split("\n").find((item) => item.startsWith("data: ")); if (!line) continue; const data = JSON.parse(line.slice(6)) as JobEvent; setAssessmentProgress(data.progress ?? 0); setAssessmentMessage(data.message || data.status || "Assessment in progress..."); if (data.status === "failed") throw new Error(data.error_message || "Assessment failed."); if (data.status === "completed") finished = true; } }
      await loadLatestReport();
    } catch (error) { setAssessmentError(error instanceof Error ? error.message : "Assessment generation failed."); }
    finally { setIsGenerating(false); }
  }

  useEffect(() => setRole((sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | "admin" | null) || "student"), []);
  useEffect(() => { if (role === "student") return; const refreshScope = () => { const state = readIngestionState(); setSelectedCourseId(state.selectedCourseId || ""); setSelectedProjectId(state.selectedProjectId || ""); setSprintId(state.selectedSprintId || "sprint-1"); }; refreshScope(); window.addEventListener("sprintsight-ingestion-updated", refreshScope); return () => window.removeEventListener("sprintsight-ingestion-updated", refreshScope); }, [role]);
  useEffect(() => { if (!role || role === "student") return; async function loadProjects() { try { const courses = await apiRequest<Array<{ id: string; code: string; name: string; section: string }>>("/courses"); const groups = await Promise.all(courses.map(async (course) => ({ course, projects: await apiRequest<Array<{ id: string; team_name: string; project_name: string }>>(`/courses/${course.id}/projects`) }))); const options = groups.flatMap(({ course, projects }) => projects.map((project) => ({ id: project.id, courseId: course.id, courseLabel: `${course.code} - ${course.name} - ${course.section}`, label: `${project.team_name} - ${project.project_name}` }))); setProjectOptions(options); } catch (error) { setProjectOptions([]); setAssessmentError(error instanceof Error ? error.message : "Could not load assessment projects."); } } void loadProjects(); }, [role]);
  useEffect(() => { if (role !== "student" && selectedProjectId) void loadLatestReport(); }, [role, selectedProjectId, sprintId, projectOptions]);
  const scope = resolveScope();
  return { report, backendReport, role, isLoadingReport, isGenerating, assessmentProgress, assessmentMessage, assessmentError, scope, loadLatestReport, generateAssessment, acceptSavedReport };
}