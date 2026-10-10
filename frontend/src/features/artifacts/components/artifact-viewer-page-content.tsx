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
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL, apiRequest, getAuthToken, isUuid } from "@/features/projects/components/projects-api";
import { getProjectGitMetrics, getProjectIngestion, saveDocumentCount, saveGitMetrics, saveJiraSnapshot } from "@/features/ingestion/state";
import type { ArtifactTab, DocumentArtifact } from "@/features/artifacts/types";
import { ArtifactTabs } from "@/features/artifacts/components/artifact-tabs";
import { GitIngestionRunsTable } from "@/features/artifacts/components/git-ingestion-runs-table";
import { JiraIngestionRunsTable, type JiraIngestionRun } from "@/features/artifacts/components/jira-ingestion-runs-table";
import { getDocumentFileType, validateDocumentFiles } from "@/features/artifacts/document-upload";
import { useDocumentDeletion } from "@/features/artifacts/hooks/use-document-deletion";
import { useArtifactProjectScope } from "@/features/artifacts/hooks/use-artifact-project-scope";

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

function normalizeSprintLabel(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = value.match(/(\d+)/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildNextSprintLabel(existingValues: Array<string | null | undefined>) {
  const maxSprintNumber = existingValues.reduce((max, value) => {
    const parsed = normalizeSprintLabel(value);
    return parsed !== null && parsed > max ? parsed : max;
  }, 0);
  return `Sprint ${maxSprintNumber + 1}`;
}

function buildSprintApiId(value: string) {
  const normalized = value.trim();
  const match = normalized.match(/(\d+)/);
  if (!match) return `sprint-${normalized.toLowerCase().replace(/\s+/g, "-")}`;
  return `sprint-${match[1]}`;
}

function buildNextSprintId(existingValues: Array<string | null | undefined>) {
  return buildSprintApiId(buildNextSprintLabel(existingValues));
}

function toDocumentArtifact(document: BackendDocument): DocumentArtifact {
  return {
    id: document.id,
    fileName: document.filename,
    fileType: getDocumentFileType(document.filename),
    uploadedBy: document.uploaded_by,
    uploadedAt: new Date(document.created_at).toLocaleDateString(),
    size: formatBytes(document.byte_size),
  };
}

export default function ArtifactViewerPageContent() {
  const [activeTab, setActiveTab] = useState<ArtifactTab>("github");
  
  // Track user role and full name for anonymity, tab access, and upload attribution
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [fullName, setFullName] = useState<string>("");
  const { projectOptions, selectedProjectId, selectedSprintId, isLoadingProjects, projectLoadError } = useArtifactProjectScope(role);

  
  // Local state for documents to allow instant UI updates upon upload
  const [localDocuments, setLocalDocuments] = useState<DocumentArtifact[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documentError, setDocumentError] = useState("");
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const documentDeletion = useDocumentDeletion((projectId, documentId) => {
    setLocalDocuments((previous) => {
      const updated = previous.filter((document) => document.id !== documentId);
      if (projectId === selectedProjectId) saveDocumentCount(projectId, updated.length);
      return updated;
    });
  });
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
  const [gitRuns, setGitRuns] = useState<RepoIngestionData[]>([]);

  const sourceRows = useMemo(() => {
    const sources = [];
    if (gitMetrics) sources.push({ source: "GitHub", records: gitMetrics.pagination?.total ?? gitMetrics.commits.length, lastSyncedAt: new Date(gitMetrics.captured_at).toLocaleString(), parserStatus: "Healthy", evaluationUsage: "Code quality, ownership, delivery cadence" });
    if (jiraSnapshot) sources.push({ source: "Jira", records: jiraSnapshot.tickets.length, lastSyncedAt: new Date(jiraSnapshot.captured_at).toLocaleString(), parserStatus: "Healthy", evaluationUsage: "Task completion, planning reliability" });
    if (isUuid(selectedProjectId) && localDocuments.length > 0) sources.push({ source: "Documents", records: localDocuments.length, lastSyncedAt: "Available", parserStatus: "Healthy", evaluationUsage: "Evidence quality, documentation completeness" });
    return sources;
  }, [gitMetrics, jiraSnapshot, localDocuments.length, selectedProjectId]);

  // Initialize role, name, and local documents on mount/dataset change
  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    const savedName = sessionStorage.getItem("sprintsight-auth-name");

    setRole(savedRole ?? "student"); // Default to student if not found to enforce privacy
    if (savedName) {
      setFullName(savedName);
    }
  }, []);

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
  const displayedTab = role === "student" ? "documents" : activeTab;

  useEffect(() => {
    const persisted = getProjectIngestion(selectedProjectId, selectedSprintId);
    const persistedGitRuns = getProjectGitMetrics(selectedProjectId) as RepoIngestionData[];
    setGitRuns(persistedGitRuns);
    const selectedGitRun = persistedGitRuns.find((run) => run.sprint_id === selectedSprintId) || null;
    if (selectedGitRun) {
      setGitMetrics(selectedGitRun);
      setGitSprintId(buildNextSprintId(persistedGitRuns.map((run) => run.sprint_id)));
    } else {
      setGitMetrics(null);
      setGitSprintId(buildNextSprintId([]));
    }
    if (persisted.jira) {
      setJiraSnapshot(persisted.jira);
    } else {
      setJiraSnapshot(null);
    }
  }, [selectedProjectId, selectedSprintId]);

  useEffect(() => {
    async function loadDocuments() {
      setDocumentError("");
      if (!role || (role === "student" && isLoadingProjects)) {
        setLocalDocuments([]);
        return;
      }
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)) {
        setLocalDocuments([]);
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
  }, [role, selectedProjectId, isLoadingProjects]);

  useEffect(() => {
    if (role !== "instructor") {
      setJiraRuns([]);
      setJiraSnapshot(null);
      return;
    }
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
        const selectedCompleted = runs.find((run) => run.sprint_id === selectedSprintId && run.processing_status === "completed");
        if (selectedCompleted) {
          await loadCleanedRun(selectedCompleted);
        } else {
          setJiraSnapshot(null);
        }
        setSprintId(buildNextSprintId(runs.map((run) => run.sprint_id)));
      } catch (error) {
        setJiraError(error instanceof Error ? error.message : "Failed to load Jira ingestion runs.");
      } finally {
        setIsLoadingJira(false);
      }
    }

    loadProjectRuns();
  }, [role, selectedProjectId, selectedSprintId]);

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
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId)) {
      setJiraError("Select a real backend project before syncing Jira.");
      return;
    }
    if (!project?.jiraProjectKey) {
      setJiraError("The selected project has no saved Jira project key. Configure it in Projects first.");
      return;
    }

    const sprint = sprintId || buildNextSprintId(jiraRuns.map((run) => run.sprint_id));
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
      setSprintId(buildNextSprintId([...jiraRuns.map((run) => run.sprint_id), sprint]));
    } catch (error) {
      setJiraError(error instanceof Error ? error.message : "Jira ingestion failed.");
    } finally {
      setIsSyncingJira(false);
    }
  }

  async function syncGit() {
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId) || !project?.courseId) {
      setGitError("Select a real backend project with a course before syncing Git.");
      return;
    }

    const sprint = gitSprintId || buildNextSprintId(gitRuns.map((run) => run.sprint_id));
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
      const metrics = {
        ...response.github_metrics,
        sprint_id: sprint,
        pagination: response.github_metrics.pagination ?? {
          limit: null,
          offset: null,
          total: response.github_metrics.commits?.length ?? 0,
          has_more: false,
        },
      };
      setGitMetrics(metrics);
      saveGitMetrics(metrics);
      const updatedRuns = [...gitRuns.filter((run) => run.sprint_id !== sprint), metrics];
      setGitRuns(updatedRuns);
      setGitSprintId(buildNextSprintId(updatedRuns.map((run) => run.sprint_id)));
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
  const visibleTabs = tabs;

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;

    try {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)) {
        throw new Error("Select a backend project before uploading documents.");
      }
      await validateDocumentFiles(files);

      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));
      setIsUploading(true);
      const response = await apiRequest<DocumentUploadResponse>(`/projects/${selectedProjectId}/documents`, {
        method: "POST",
        body: formData,
      });
      setLocalDocuments((previous) => {
        const updated = [...response.documents.map(toDocumentArtifact), ...previous];
        saveDocumentCount(selectedProjectId, updated.length);
        return updated;
      });
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
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">
            {role === "student" ? "My Project Documents" : "Artifact Viewer"}
          </h1>
          <p className="mt-1 text-base text-slate-500">
            {role === "student"
              ? "Upload and review documents for your project."
              : `${projectOptions.find((option) => option.id === selectedProjectId)?.label || "Select a project"} - Raw evidence used for AI assessment`}
          </p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Project context</label>
          <div className="flex h-11 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
            {isLoadingProjects ? "Loading selected project..." : projectOptions.find((option) => option.id === selectedProjectId)?.label || "No project selected"}
          </div>
          {role === "student" && projectLoadError && (
            <p className="mt-1 text-sm text-rose-600">{projectLoadError}</p>
          )}
        </div>
      </div>

      {role === "instructor" && (
        <ArtifactTabs tabs={tabs} visibleTabs={visibleTabs} activeTab={activeTab} onChange={setActiveTab} />
      )}

      <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {role === "instructor" && displayedTab === "github" && (
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
              <div className="min-w-[220px] flex-1 space-y-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sprint</span>
                <div className="flex h-10 w-full items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700">
                  {gitSprintId || "sprint-1"}
                </div>
              </div>
            </div>

            {gitError && <p className="text-sm text-rose-600">{gitError}</p>}
            {ingestionDisabledReason && <p className="text-sm text-amber-700">{ingestionDisabledReason}</p>}
            {isLoadingGit && <p className="text-sm text-slate-500">Loading Git ingestion data...</p>}

            <GitIngestionRunsTable
              runs={gitRuns.map((run) => ({
                sprintId: run.sprint_id,
                recordCount: run.pagination?.total ?? run.commits.length,
                capturedAt: run.captured_at,
              }))}
            />

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
            ) : <p className="text-sm text-slate-500">No Git data is available for the selected project and sprint.</p>}
          </>
        )}

        {role === "instructor" && displayedTab === "jira" && (
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

            <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
              <div className="space-y-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sprint</span>
                <div className="flex h-10 w-full items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700">
                  {sprintId || "sprint-1"}
                </div>
              </div>
            </div>

            {jiraError && <p className="text-sm text-rose-600">{jiraError}</p>}

            <JiraIngestionRunsTable runs={jiraRuns} onLoadCleanedRun={loadCleanedRun} />

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
            ) : <p className="text-sm text-slate-500">No Jira data is available for the selected project and sprint.</p>}
          </>
        )}

        {displayedTab === "documents" && (role === "student" || role === "instructor") && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-3xl font-semibold text-blue-950">
                {role === "student" ? "Your Uploaded Documents" : "Uploaded Documents"} ({localDocuments.length})
              </h2>
              
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload}
                className="hidden" 
                accept=".pdf,.docx,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                multiple
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selectedProjectId)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                <Upload className="h-4 w-4" />
                {isUploading ? "Uploading..." : "Upload Document"}
              </button>
            </div>
            <p className="text-sm text-slate-500">Accepted formats: PDF, DOCX, and PPTX.</p>

            {documentError && <p className="text-sm text-rose-600">{documentError}</p>}
            {isLoadingDocuments && <p className="text-sm text-slate-500">Loading documents...</p>}

            {localDocuments.map((doc) => {
              const isDeleting = documentDeletion.deletingDocumentIds.has(doc.id);
              return (
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
                    <button
                      type="button"
                      onClick={() => void documentDeletion.deleteDocument(selectedProjectId, doc.id, doc.fileName)}
                      disabled={isDeleting}
                      aria-label={`Delete ${doc.fileName}`}
                      className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      {isDeleting ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                  {documentDeletion.deleteErrors[doc.id] && (
                    <p className="mt-2 text-sm text-rose-700" role="alert">{documentDeletion.deleteErrors[doc.id]}</p>
                  )}
                </article>
              );
            })}
            
            {localDocuments.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 py-12 text-center">
                <p className="text-sm text-slate-500">No documents uploaded yet. Click the upload button to add evidence.</p>
              </div>
            )}
          </>
        )}

        {role === "instructor" && displayedTab === "communication" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">Communication Artifacts</h2>
            <p className="text-sm text-slate-500">No communication artifacts are available for the selected project.</p>
          </>
        )}

        {role === "instructor" && displayedTab === "peer-evaluation" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">Peer Evaluation Inputs</h2>
            <p className="text-sm text-slate-500">No peer evaluation data is available for the selected project and sprint.</p>
          </>
        )}
      </section>

      {role === "instructor" && <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
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
              {sourceRows.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-sm text-slate-500">No structured ingestion inputs are available for the selected project and sprint.</td></tr>}
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
      </section>}
    </div>
  );
}