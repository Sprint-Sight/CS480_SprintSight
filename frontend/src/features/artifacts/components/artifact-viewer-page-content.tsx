"use client";

import { 
  CheckSquare, 
  FileText, 
  FolderGit2, 
  MessageSquare, 
  Users,
  Upload,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { getArtifactDataset, getArtifactProjectOptions } from "@/features/artifacts/data";
import { API_BASE_URL, apiRequest, getAuthToken } from "@/features/projects/components/projects-api";
import { getProjectIngestion, readIngestionState, saveDocumentCount, saveGitMetrics, saveJiraSnapshot } from "@/features/ingestion/state";
import type { ArtifactTab, DocumentArtifact } from "@/features/artifacts/types";
import { ArtifactTabs } from "@/features/artifacts/components/artifact-tabs";

const tabs: Array<{ id: ArtifactTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "github", label: "GitHub", icon: FolderGit2 },
  { id: "jira", label: "Jira", icon: CheckSquare },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "communication", label: "Communication", icon: MessageSquare },
  { id: "peer-evaluation", label: "Peer Evaluation", icon: Users },
];

function getStatusPill(status?: string) {
  if (!status) return "";
  if (status === "merged" || status === "Done") return "bg-emerald-50 text-emerald-700";
  if (status === "open" || status === "In Progress") return "bg-blue-50 text-blue-700";
  return "bg-slate-100 text-slate-600";
}

function formatBytes(bytes: number, decimals = 1) {
  if (!+bytes) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

type BackendDocument = {
  id: string;
  filename: string;
  byte_size: number;
  uploaded_by: string;
  created_at: string;
};

type DocumentUploadResponse = { documents: BackendDocument[] };

type ProjectOption = {
  id: string;
  courseId?: string;
  jiraProjectKey?: string | null;
  label: string;
};

type FileDiff = {
  filename: string;
  change_type: "added" | "modified" | "deleted" | "renamed";
  lines_added: number;
  lines_deleted: number;
};

type CommitInfo = {
  sha: string;
  author: string;
  message: string;
  timestamp: string;
  lines_added: number;
  lines_deleted: number;
  files_changed: FileDiff[];
};

type RepoIngestionData = {
  course_id: string;
  project_id: string;
  sprint_id: string;
  head_sha: string | null;
  captured_at: string;
  commit_frequency: number;
  code_churn: number;
  pr_turnaround_hours: number | null;
  assigned_story_points: number | null;
  completion_percent: number | null;
  commits: CommitInfo[];
  pagination: {
    limit: number | null;
    offset: number | null;
    total: number;
    has_more: boolean;
  };
};

type RepoSyncResponse = {
  github_metrics: RepoIngestionData;
  jira_metrics: unknown;
  document_signals: {
    documentation_quality: number;
    demo_completeness: number;
  };
};

type JiraIngestionRun = {
  run_id: string;
  course_id: string;
  project_id: string;
  sprint_id: string;
  jira_project_key: string;
  jql: string;
  issue_count: number;
  captured_at: string;
  processed_at: string | null;
  processing_status: "pending" | "completed" | "failed";
  normalization_version: string | null;
  processing_error: string | null;
};

type JiraTicket = {
  ticket_id: string;
  summary: string;
  assignee: string | null;
  status: string | null;
  issue_type: string | null;
  story_points: number | null;
  sprint_id: string | null;
};

type JiraCleanedSnapshot = {
  normalization_version: string;
  source: string;
  jira_project_key: string;
  course_id: string;
  project_id: string;
  sprint_id: string;
  captured_at: string;
  tickets: JiraTicket[];
};

function toDocumentArtifact(document: BackendDocument): DocumentArtifact {
  return {
    id: document.id,
    fileName: document.filename,
    fileType: "PDF",
    uploadedBy: document.uploaded_by,
    uploadedAt: new Date(document.created_at).toLocaleDateString(),
    size: formatBytes(document.byte_size),
  };
}

export default function ArtifactViewerPageContent() {
  const fallbackProjectOptions = useMemo(() => getArtifactProjectOptions(), []);
  const [projectOptions, setProjectOptions] = useState<ProjectOption[]>(fallbackProjectOptions);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || fallbackProjectOptions[0]?.id || "");
  const [activeTab, setActiveTab] = useState<ArtifactTab>("github");
  
  // Track user role and full name for anonymity, tab access, and upload attribution
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [fullName, setFullName] = useState<string>("");
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [projectLoadError, setProjectLoadError] = useState("");

  const dataset = useMemo(() => getArtifactDataset(selectedProjectId), [selectedProjectId]);
  
  // Local state for documents to allow instant UI updates upon upload
  const [localDocuments, setLocalDocuments] = useState<DocumentArtifact[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documentError, setDocumentError] = useState("");
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [sprintId, setSprintId] = useState("");
  const [jiraRuns, setJiraRuns] = useState<JiraIngestionRun[]>([]);
  const [jiraSnapshot, setJiraSnapshot] = useState<JiraCleanedSnapshot | null>(null);
  const [jiraError, setJiraError] = useState("");
  const [isLoadingJira, setIsLoadingJira] = useState(false);
  const [isSyncingJira, setIsSyncingJira] = useState(false);
  const [gitSprintId, setGitSprintId] = useState("");
  const [gitMetrics, setGitMetrics] = useState<RepoIngestionData | null>(null);
  const [gitError, setGitError] = useState("");
  const [isLoadingGit, setIsLoadingGit] = useState(false);
  const [isSyncingGit, setIsSyncingGit] = useState(false);

  const sourceRows = useMemo(() => {
    const sources = [...dataset.sources];
    const replace = (source: "GitHub" | "Jira" | "Documents", records: number, lastSyncedAt: string, parserStatus: "Healthy" | "Warning") => {
      const index = sources.findIndex((item) => item.source === source);
      if (index >= 0) sources[index] = { ...sources[index], records, lastSyncedAt, parserStatus };
    };

    if (gitMetrics) replace("GitHub", gitMetrics.pagination?.total ?? gitMetrics.commits.length, new Date(gitMetrics.captured_at).toLocaleString(), "Healthy");
    if (jiraSnapshot) replace("Jira", jiraSnapshot.tickets.length, new Date(jiraSnapshot.captured_at).toLocaleString(), "Healthy");
    if (isUuid(selectedProjectId)) replace("Documents", localDocuments.length, new Date().toLocaleString(), "Healthy");
    return sources;
  }, [dataset.sources, gitMetrics, jiraSnapshot, localDocuments.length, selectedProjectId]);

  // Initialize role, name, and local documents on mount/dataset change
  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    const savedName = sessionStorage.getItem("sprintsight-auth-name");

    setRole(savedRole ?? "student"); // Default to student if not found to enforce privacy
    if (savedName) {
      setFullName(savedName);
    }
  }, []);

  useEffect(() => {
    if (role !== "instructor") return;

    async function loadBackendProjects() {
      setIsLoadingProjects(true);
      setProjectLoadError("");
      try {
        const courses = await apiRequest<Array<{ id: string }>>("/courses");
        const projectGroups = await Promise.all(
          courses.map(async (course) => ({
            courseId: course.id,
            projects: await apiRequest<Array<{ id: string; team_name: string; project_name: string; jira_project_key: string | null }>>(`/courses/${course.id}/projects`),
          }))
        );
        const options = projectGroups.flatMap(({ courseId, projects }) => projects.map((project) => ({
          id: project.id,
          courseId,
          jiraProjectKey: project.jira_project_key,
          label: `${project.team_name} - ${project.project_name}`,
        })));
        if (options.length > 0) {
          setProjectOptions(options);
          const persistedProjectId = readIngestionState().selectedProjectId;
          setSelectedProjectId(
            persistedProjectId && options.some((option) => option.id === persistedProjectId)
              ? persistedProjectId
              : options[0].id,
          );
        } else {
          setProjectLoadError("No backend projects are available for this instructor.");
        }
      } catch (error) {
        console.error("Failed to load artifact projects:", error);
        setProjectLoadError("Could not load backend projects. Check the instructor session and API connection.");
      } finally {
        setIsLoadingProjects(false);
      }
    }

    loadBackendProjects();
  }, [role]);

  const selectedBackendProject = projectOptions.find(
    (project) => project.id === selectedProjectId && isUuid(project.id) && Boolean(project.courseId),
  );
  const ingestionDisabledReason = role !== "instructor"
    ? "Git and Jira ingestion requires an instructor account."
    : isLoadingProjects
      ? "Loading backend projects..."
      : projectLoadError
        ? projectLoadError
        : !selectedBackendProject
          ? "Select a real backend project before starting ingestion."
          : "";

  useEffect(() => {
    const persisted = getProjectIngestion(selectedProjectId);
    if (persisted.git) {
      setGitMetrics(persisted.git as RepoIngestionData);
      setGitSprintId(persisted.git.sprint_id);
    }
    if (persisted.jira) {
      setJiraSnapshot(persisted.jira);
      setSprintId(persisted.jira.sprint_id);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    async function loadDocuments() {
      setDocumentError("");
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)) {
        setLocalDocuments(dataset.documents);
        return;
      }

      setIsLoadingDocuments(true);
      try {
        const documents = await apiRequest<BackendDocument[]>(`/projects/${selectedProjectId}/documents`);
        setLocalDocuments(documents.map(toDocumentArtifact));
        saveDocumentCount(selectedProjectId, documents.length);
      } catch (error) {
        setDocumentError(error instanceof Error ? error.message : "Failed to load documents.");
        setLocalDocuments([]);
      } finally {
        setIsLoadingDocuments(false);
      }
    }

    loadDocuments();
  }, [dataset, selectedProjectId]);

  useEffect(() => {
    if (!isUuid(selectedProjectId)) {
      setJiraRuns([]);
      setJiraSnapshot(null);
      return;
    }

    async function loadProjectRuns() {
      setJiraError("");
      setIsLoadingJira(true);
      try {
        const runs = await apiRequest<JiraIngestionRun[]>(`/jira-ingestion/runs/${selectedProjectId}`);
        setJiraRuns(runs);
        const latestCompleted = runs.find((run) => run.processing_status === "completed");
        if (latestCompleted) {
          setSprintId(latestCompleted.sprint_id);
          await loadCleanedRun(latestCompleted);
        }
      } catch (error) {
        setJiraError(error instanceof Error ? error.message : "Failed to load Jira ingestion runs.");
      } finally {
        setIsLoadingJira(false);
      }
    }

    loadProjectRuns();
  }, [selectedProjectId]);

  async function loadGitMetrics() {
    const sprint = gitSprintId.trim();
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId) || !project?.courseId) {
      setGitError("Select a real backend project with a course before loading Git data.");
      return;
    }
    if (!sprint) {
      setGitError("Enter a sprint ID before loading Git data.");
      return;
    }

    setGitError("");
    setIsLoadingGit(true);
    try {
      const metrics = await apiRequest<RepoIngestionData>(
        `/repo-ingestion/runs/${selectedProjectId}/${encodeURIComponent(sprint)}?course_id=${encodeURIComponent(project.courseId)}`
      );
      setGitMetrics(metrics);
      saveGitMetrics(metrics);
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "Failed to load Git ingestion data.");
    } finally {
      setIsLoadingGit(false);
    }
  }

  async function loadCleanedRun(run: JiraIngestionRun) {
    const snapshot = await apiRequest<JiraCleanedSnapshot>(
      `/jira-ingestion/runs/${run.project_id}/${run.sprint_id}/${run.run_id}/cleaned`
    );
    setJiraSnapshot(snapshot);
    saveJiraSnapshot(snapshot);
  }

  async function loadSprintRuns(sprint: string) {
    if (!isUuid(selectedProjectId) || !sprint.trim()) return;
    const runs = await apiRequest<JiraIngestionRun[]>(
      `/jira-ingestion/runs/${selectedProjectId}/${encodeURIComponent(sprint.trim())}`
    );
    setJiraRuns((previous) => {
      const otherRuns = previous.filter((run) => run.sprint_id !== sprint.trim());
      return [...runs, ...otherRuns];
    });
  }

  async function syncJira() {
    const sprint = sprintId.trim();
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId)) {
      setJiraError("Select a real backend project before syncing Jira.");
      return;
    }
    if (!project?.jiraProjectKey) {
      setJiraError("The selected project has no saved Jira project key. Configure it in Projects first.");
      return;
    }
    if (!sprint) {
      setJiraError("Enter a sprint ID before syncing Jira.");
      return;
    }

    setJiraError("");
    setIsSyncingJira(true);
    setJiraSnapshot(null);
    try {
      const rawRun = await apiRequest<JiraIngestionRun>(`/jira-ingestion/raw/${selectedProjectId}`, {
        method: "POST",
        body: JSON.stringify({
          sprint_id: sprint,
        }),
      });

      const processedRun = await apiRequest<JiraIngestionRun>(
        `/jira-ingestion/runs/${selectedProjectId}/${encodeURIComponent(sprint)}/${rawRun.run_id}/process`,
        { method: "POST" }
      );
      await loadCleanedRun(processedRun);
      await loadSprintRuns(sprint);
    } catch (error) {
      setJiraError(error instanceof Error ? error.message : "Jira ingestion failed.");
    } finally {
      setIsSyncingJira(false);
    }
  }

  async function syncGit() {
    const sprint = gitSprintId.trim();
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId) || !project?.courseId) {
      setGitError("Select a real backend project with a course before syncing Git.");
      return;
    }
    if (!sprint) {
      setGitError("Enter a sprint ID before syncing Git.");
      return;
    }

    setGitError("");
    setIsSyncingGit(true);
    try {
      const response = await apiRequest<RepoSyncResponse>("/repo-ingestion/sync", {
        method: "POST",
        body: JSON.stringify({
          course_id: project.courseId,
          project_id: selectedProjectId,
          sprint_id: sprint,
        }),
      });
      setGitMetrics({
        ...response.github_metrics,
        pagination: response.github_metrics.pagination ?? {
          limit: null,
          offset: null,
          total: response.github_metrics.commits?.length ?? 0,
          has_more: false,
        },
      });
      saveGitMetrics({
        ...response.github_metrics,
        pagination: response.github_metrics.pagination ?? {
          limit: null,
          offset: null,
          total: response.github_metrics.commits?.length ?? 0,
          has_more: false,
        },
      });
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "Git ingestion failed.");
    } finally {
      setIsSyncingGit(false);
    }
  }

  function isUuid(value: string) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
  }

  // Filter tabs dynamically based on user role
  const visibleTabs = useMemo(() => {
    if (role === "student") {
      return tabs.filter((tab) => tab.id !== "peer-evaluation");
    }
    return tabs;
  }, [role]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;

    try {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)) {
        throw new Error("Select a backend project before uploading documents.");
      }
      if (files.some((file) => !file.name.toLowerCase().endsWith(".pdf") || file.type !== "application/pdf")) {
        throw new Error("Only PDF files with application/pdf MIME type are allowed.");
      }
      if (files.some((file) => file.size > 25 * 1024 * 1024)) {
        throw new Error("Each PDF must be 25 MB or smaller.");
      }
      if (files.reduce((total, file) => total + file.size, 0) > 100 * 1024 * 1024) {
        throw new Error("The total upload size must be 100 MB or smaller.");
      }

      for (const file of files) {
        const header = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
        if (header !== "%PDF-") throw new Error(`${file.name} is not a valid PDF file.`);
      }

      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));
      setIsUploading(true);
      const response = await apiRequest<DocumentUploadResponse>(`/projects/${selectedProjectId}/documents`, {
        method: "POST",
        body: formData,
      });
      setLocalDocuments((previous) => [...response.documents.map(toDocumentArtifact), ...previous]);
    } catch (error) {
      setDocumentError(error instanceof Error ? error.message : "Failed to upload documents.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDownloadDocument = async (documentId: string, fileName: string) => {
    const token = getAuthToken();
    if (!token) return;

    try {
      const response = await fetch(`${API_BASE_URL}/projects/${selectedProjectId}/documents/${documentId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Failed to download document.");
      const objectUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = fileName;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setDocumentError(error instanceof Error ? error.message : "Failed to download document.");
    }
  };

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Artifact Viewer</h1>
          <p className="mt-1 text-base text-slate-500">{projectOptions.find((option) => option.id === selectedProjectId)?.label} - Raw evidence used for AI assessment</p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Project context</label>
          <select
            value={selectedProjectId}
            onChange={(event) => setSelectedProjectId(event.target.value)}
            className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
          >
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ArtifactTabs tabs={tabs} visibleTabs={visibleTabs} activeTab={activeTab} onChange={setActiveTab} />

      <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {activeTab === "github" && (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-3xl font-semibold text-blue-950">Git Repository Activity</h2>
                <p className="mt-1 text-sm text-slate-500">Sync commits and inspect repository metrics for a sprint.</p>
              </div>
              <button
                type="button"
                onClick={syncGit}
                disabled={isSyncingGit || !selectedBackendProject}
                title={ingestionDisabledReason || "Sync the selected Git repository"}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSyncingGit ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {isSyncingGit ? "Syncing Git..." : "Sync Git Repository"}
              </button>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[220px] flex-1 space-y-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sprint ID</span>
                <input
                  value={gitSprintId}
                  onChange={(event) => setGitSprintId(event.target.value)}
                  placeholder="e.g. sprint-1"
                  className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </label>
              <button
                type="button"
                onClick={loadGitMetrics}
                disabled={isLoadingGit || !gitSprintId.trim() || !selectedBackendProject}
                title={ingestionDisabledReason || "Load saved Git metrics"}
                className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Refresh Git Data
              </button>
            </div>

            {gitError && <p className="text-sm text-rose-600">{gitError}</p>}
            {ingestionDisabledReason && <p className="text-sm text-amber-700">{ingestionDisabledReason}</p>}
            {isLoadingGit && <p className="text-sm text-slate-500">Loading Git ingestion data...</p>}

            {gitMetrics ? (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs text-slate-500">Commits</p>
                    <p className="mt-1 text-xl font-semibold text-slate-900">{gitMetrics.pagination.total}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs text-slate-500">Commit frequency</p>
                    <p className="mt-1 text-xl font-semibold text-slate-900">{gitMetrics.commit_frequency}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs text-slate-500">Code churn</p>
                    <p className="mt-1 text-xl font-semibold text-slate-900">{gitMetrics.code_churn}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs text-slate-500">Captured</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900">{new Date(gitMetrics.captured_at).toLocaleString()}</p>
                  </div>
                </div>

                <p className="text-xs text-slate-500">Head SHA: {gitMetrics.head_sha || "Unavailable"}</p>
                {gitMetrics.commits.map((commit) => (
                  <article key={commit.sha} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-lg font-semibold text-slate-900">{commit.message}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {commit.author} - {new Date(commit.timestamp).toLocaleString()} - {commit.sha.slice(0, 10)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">+{commit.lines_added} / -{commit.lines_deleted} lines</p>
                  </article>
                ))}
              </>
            ) : (
              dataset.github.map((entry) => (
                <article key={entry.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-slate-900">{entry.title}</p>
                      <p className="mt-1 text-sm text-slate-500">{entry.author} - {entry.date} - {entry.ref}</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${entry.type === "pr" ? "bg-violet-50 text-violet-700" : "bg-blue-50 text-blue-700"}`}>
                      {entry.type === "pr" ? "PR" : "Commit"}
                    </span>
                  </div>
                </article>
              ))
            )}
          </>
        )}

        {activeTab === "jira" && (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-3xl font-semibold text-blue-950">Jira Backlog and Tasks</h2>
                <p className="mt-1 text-sm text-slate-500">Sync, normalize, and inspect Jira data for a sprint.</p>
              </div>
              <button
                type="button"
                onClick={syncJira}
                disabled={isSyncingJira || !selectedBackendProject}
                title={ingestionDisabledReason || "Sync Jira for the selected project"}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSyncingJira ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {isSyncingJira ? "Syncing Jira..." : "Sync Jira"}
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto]">
              <label className="space-y-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sprint ID</span>
                <input
                  value={sprintId}
                  onChange={(event) => setSprintId(event.target.value)}
                  placeholder="e.g. sprint-1"
                  className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </label>
              <button
                type="button"
                onClick={() => loadSprintRuns(sprintId)}
                disabled={isLoadingJira || !selectedBackendProject || !sprintId.trim()}
                title={ingestionDisabledReason || "Refresh Jira runs"}
                className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Refresh runs
              </button>
            </div>

            {jiraError && <p className="text-sm text-rose-600">{jiraError}</p>}

            {jiraRuns.length > 0 && (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[620px] text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Sprint</th>
                      <th className="px-3 py-2">Issues</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Captured</th>
                      <th className="px-3 py-2 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jiraRuns.map((run) => (
                      <tr key={run.run_id} className="border-b border-slate-100 last:border-0">
                        <td className="px-3 py-2 font-medium text-slate-800">{run.sprint_id}</td>
                        <td className="px-3 py-2 text-slate-600">{run.issue_count}</td>
                        <td className="px-3 py-2">
                          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${run.processing_status === "completed" ? "bg-emerald-50 text-emerald-700" : run.processing_status === "failed" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>
                            {run.processing_status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-600">{new Date(run.captured_at).toLocaleString()}</td>
                        <td className="px-3 py-2 text-right">
                          {run.processing_status === "completed" && (
                            <button type="button" onClick={() => loadCleanedRun(run)} className="text-xs font-semibold text-blue-700 hover:text-blue-900">
                              View cleaned data
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {jiraSnapshot ? (
              jiraSnapshot.tickets.map((ticket) => (
                <article key={ticket.ticket_id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-slate-900">{ticket.ticket_id}: {ticket.summary}</p>
                      <p className="mt-1 text-sm text-slate-500">
                        {ticket.assignee || "Unassigned"} - {ticket.issue_type || "Issue"} - {ticket.story_points ?? 0} pts
                      </p>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getStatusPill(ticket.status || undefined)}`}>{ticket.status || "Unknown"}</span>
                  </div>
                </article>
              ))
            ) : (
              dataset.jira.map((task) => (
                <article key={task.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-slate-900">{task.key}: {task.title}</p>
                      <p className="mt-1 text-sm text-slate-500">{task.assignee} - {task.sprint} - {task.points} pts</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getStatusPill(task.status)}`}>{task.status}</span>
                  </div>
                </article>
              ))
            )}
          </>
        )}

        {activeTab === "documents" && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-3xl font-semibold text-blue-950">Uploaded Documents</h2>
              
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload}
                className="hidden" 
                accept="application/pdf,.pdf"
                multiple
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                <Upload className="h-4 w-4" />
                {isUploading ? "Uploading..." : "Upload PDF"}
              </button>
            </div>

            {documentError && <p className="text-sm text-rose-600">{documentError}</p>}
            {isLoadingDocuments && <p className="text-sm text-slate-500">Loading documents...</p>}

            {localDocuments.map((doc) => (
              <article key={doc.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">{doc.fileName}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {doc.uploadedBy} - {doc.uploadedAt} - {doc.size}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDownloadDocument(doc.id, doc.fileName)}
                    className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                  >
                    Download {doc.fileType}
                  </button>
                </div>
              </article>
            ))}
            
            {localDocuments.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 py-12 text-center">
                <p className="text-sm text-slate-500">No documents uploaded yet. Click the upload button to add evidence.</p>
              </div>
            )}
          </>
        )}

        {activeTab === "communication" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">Communication Artifacts</h2>
            {dataset.communication.map((entry) => (
              <article key={entry.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-base font-semibold text-slate-900">{entry.channel}</p>
                <p className="mt-1 text-sm text-slate-600">{entry.summary}</p>
                <p className="mt-1 text-xs text-slate-500">Captured {entry.capturedAt}</p>
              </article>
            ))}
          </>
        )}

        {activeTab === "peer-evaluation" && role !== "student" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">Peer Evaluation Inputs</h2>
            {dataset.peerEvaluation.map((entry) => (
              <article key={entry.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-base font-semibold text-slate-900">
                    {entry.reviewer} reviewed {entry.target}
                  </p>
                  <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">{entry.score}/100</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{entry.sprint}</p>
              </article>
            ))}
          </>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Structured raw inputs for AI evaluation</h2>
        <p className="mt-1 text-sm text-slate-500">Normalized ingestion metadata used by scoring and feedback pipelines.</p>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4">Source</th>
                <th className="py-2 pr-4">Records</th>
                <th className="py-2 pr-4">Last Sync</th>
                <th className="py-2 pr-4">Parser Status</th>
                <th className="py-2">Evaluation Usage</th>
              </tr>
            </thead>
            <tbody>
              {sourceRows.map((source) => (
                <tr key={source.source} className="border-b border-slate-100 text-sm text-slate-700 last:border-b-0">
                  <td className="py-3 pr-4 font-semibold text-slate-900">{source.source}</td>
                  <td className="py-3 pr-4">{source.records}</td>
                  <td className="py-3 pr-4">{source.lastSyncedAt}</td>
                  <td className="py-3 pr-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${source.parserStatus === "Healthy" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {source.parserStatus}
                    </span>
                  </td>
                  <td className="py-3">{source.evaluationUsage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}