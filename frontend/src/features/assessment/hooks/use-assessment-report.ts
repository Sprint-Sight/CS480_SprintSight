"use client";

import { useEffect, useMemo, useState } from "react";

import { getAssessmentProjectOptions, getAssessmentReport } from "@/features/assessment/data";
import { readIngestionState } from "@/features/ingestion/state";
import { API_BASE_URL, apiRequest, getAuthToken, isUuid } from "@/features/projects/components/projects-api";

type AssessmentProjectOption = { id: string; courseId?: string; label: string };
type BackendReport = { project_id: string; sprint_id: string; generated_at: string; team_score: { score: number; rationale: string }; rubric_scores: Record<string, { score: number; justification?: string | null; evidence_citations?: string[] }>; strengths: string[]; weaknesses: string[]; recommendations: string[] };
type JobEvent = { status?: string; progress?: number; message?: string; error_message?: string };

const labels: Record<string, string> = { requirements: "Requirements", code_quality: "Code Quality", testing: "Testing", documentation: "Documentation", collaboration: "Collaboration", delivery: "Delivery", quality: "Quality" };
const formatLabel = (key: string) => labels[key] || key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const normalizeRubricScore = (score: number) => score >= 0 && score <= 10 ? score * 10 : score;

export function useAssessmentReport() {
  const fallback = useMemo(() => getAssessmentProjectOptions(), []);
  const [projectOptions, setProjectOptions] = useState<AssessmentProjectOption[]>(fallback);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || fallback[0]?.id || "");
  const [sprintId, setSprintId] = useState(() => readIngestionState().selectedSprintId || "sprint-1");
  const [report, setReport] = useState(() => getAssessmentReport(fallback[0]?.id ?? ""));
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [assessmentProgress, setAssessmentProgress] = useState(0);
  const [assessmentMessage, setAssessmentMessage] = useState("");
  const [assessmentError, setAssessmentError] = useState("");
  const [role, setRole] = useState<"student" | "instructor" | "admin" | null>(null);

  const clearLiveReport = (projectId: string, sprint: string) => setReport({ projectId, sprintId: sprint, sprintLabel: sprint, teamLabel: "Live backend project", projectLabel: "No assessment report", generatedAt: "", overallScore: 0, overallGrade: "", overallSummary: "Generate an assessment to create a report for this project and sprint.", rubricScores: [], strengths: [], weaknesses: [], recommendations: [], narrativeFeedback: [] });

  async function loadLatestReport(projectId = selectedProjectId, sprint = sprintId, courseId?: string) {
    const project = projectOptions.find((option) => option.id === projectId);
    const resolvedCourseId = courseId || project?.courseId;
    if (!isUuid(projectId) || !resolvedCourseId || !sprint.trim()) { setReport(getAssessmentReport(projectId)); return; }
    setIsLoadingReport(true); setAssessmentError("");
    try {
      const data = await apiRequest<BackendReport>(`/assessments/latest?course_id=${encodeURIComponent(resolvedCourseId)}&project_id=${encodeURIComponent(projectId)}&sprint_id=${encodeURIComponent(sprint.trim())}`);
      setReport({ projectId: data.project_id, sprintId: data.sprint_id, sprintLabel: data.sprint_id, teamLabel: project?.label.split(" - ")[0] || "Project team", projectLabel: project?.label.split(" - ").slice(1).join(" - ") || project?.label || "Project", generatedAt: new Date(data.generated_at).toLocaleString(), overallScore: Math.round(data.team_score.score), overallGrade: data.team_score.score >= 85 ? "A" : data.team_score.score >= 75 ? "B" : "C", overallSummary: data.team_score.rationale, rubricScores: Object.entries(data.rubric_scores || {}).map(([category, detail]) => ({ category: formatLabel(category), score: Math.round(normalizeRubricScore(detail.score)), justification: detail.justification || "No justification provided.", evidenceCitations: detail.evidence_citations || [] })), strengths: data.strengths || [], weaknesses: data.weaknesses || [], recommendations: data.recommendations || [], narrativeFeedback: [] });
    } catch (error) { if (isUuid(projectId)) clearLiveReport(projectId, sprint); setAssessmentError(error instanceof Error ? error.message : "Failed to load the latest assessment."); }
    finally { setIsLoadingReport(false); }
  }

  async function generateAssessment() {
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId) || !project?.courseId || !sprintId.trim()) { setAssessmentError("Select a backend project and sprint from the shared scope before generating an assessment."); return; }
    setAssessmentError(""); setIsGenerating(true); setAssessmentProgress(0); setAssessmentMessage("Starting assessment...");
    try {
      const modelName = localStorage.getItem("sprintsight-selected-model") || "sprintsight-llama";
      const job = await apiRequest<{ job_id: string }>("/assessments/assess", { method: "POST", body: JSON.stringify({ course_id: project.courseId, project_id: selectedProjectId, sprint_id: sprintId.trim(), model_name: modelName }) });
      const token = getAuthToken(); if (!token) throw new Error("Your session has expired. Please log in again.");
      const response = await fetch(`${API_BASE_URL}/assessments/jobs/${job.job_id}/events`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok || !response.body) throw new Error("Could not monitor assessment progress.");
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let finished = false;
      while (!finished) { const chunk = await reader.read(); if (chunk.done) break; buffer += decoder.decode(chunk.value, { stream: true }); const events = buffer.split("\n\n"); buffer = events.pop() || ""; for (const event of events) { const line = event.split("\n").find((item) => item.startsWith("data: ")); if (!line) continue; const data = JSON.parse(line.slice(6)) as JobEvent; setAssessmentProgress(data.progress ?? 0); setAssessmentMessage(data.message || data.status || "Assessment in progress..."); if (data.status === "failed") throw new Error(data.error_message || "Assessment failed."); if (data.status === "completed") finished = true; } }
      await loadLatestReport(selectedProjectId, sprintId);
    } catch (error) { setAssessmentError(error instanceof Error ? error.message : "Assessment generation failed."); }
    finally { setIsGenerating(false); }
  }

  useEffect(() => setRole((sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | "admin" | null) || "student"), []);
  useEffect(() => { const refreshScope = () => { const state = readIngestionState(); setSelectedProjectId(state.selectedProjectId || fallback[0]?.id || ""); setSprintId(state.selectedSprintId || "sprint-1"); }; window.addEventListener("sprintsight-ingestion-updated", refreshScope); return () => window.removeEventListener("sprintsight-ingestion-updated", refreshScope); }, [fallback]);
  useEffect(() => { async function loadProjects() { try { const courses = await apiRequest<Array<{ id: string }>>("/courses"); const groups = await Promise.all(courses.map(async (course) => ({ courseId: course.id, projects: await apiRequest<Array<{ id: string; team_name: string; project_name: string }>>(`/courses/${course.id}/projects`) }))); const options = groups.flatMap(({ courseId, projects }) => projects.map((project) => ({ id: project.id, courseId, label: `${project.team_name} - ${project.project_name}` }))); if (options.length) { setProjectOptions(options); const state = readIngestionState(); setSelectedProjectId(options.some((option) => option.id === state.selectedProjectId) ? state.selectedProjectId! : options[0].id); setSprintId(state.selectedSprintId || "sprint-1"); } } catch { /* Keep fixture options available when backend data is unavailable. */ } } loadProjects(); }, []);
  useEffect(() => { if (selectedProjectId) void loadLatestReport(); }, [selectedProjectId, sprintId, projectOptions]);
  return { report, role, isLoadingReport, isGenerating, assessmentProgress, assessmentMessage, assessmentError, loadLatestReport, generateAssessment };
}