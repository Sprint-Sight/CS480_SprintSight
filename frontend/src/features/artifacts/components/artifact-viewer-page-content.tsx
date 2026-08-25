"use client";

import { 
  CheckSquare, 
  FileText, 
  FolderGit2, 
  MessageSquare, 
  Users,
  Upload
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { getArtifactDataset, getArtifactProjectOptions } from "@/features/artifacts/data";
import type { ArtifactTab, DocumentArtifact } from "@/features/artifacts/types";

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

export default function ArtifactViewerPageContent() {
  const projectOptions = useMemo(() => getArtifactProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(projectOptions[0]?.id ?? "");
  const [activeTab, setActiveTab] = useState<ArtifactTab>("github");
  
  // Track user role for anonymity and tab access
  const [role, setRole] = useState<"student" | "instructor" | null>(null);

  const dataset = useMemo(() => getArtifactDataset(selectedProjectId), [selectedProjectId]);
  
  // Local state for documents to allow instant UI updates upon upload
  const [localDocuments, setLocalDocuments] = useState<DocumentArtifact[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize role and local documents on mount/dataset change
  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    setRole(savedRole ?? "student"); // Default to student if not found to enforce privacy
  }, []);

  useEffect(() => {
    setLocalDocuments(dataset.documents);
  }, [dataset]);

  // Filter tabs dynamically based on user role
  const visibleTabs = useMemo(() => {
    if (role === "student") {
      return tabs.filter((tab) => tab.id !== "peer-evaluation");
    }
    return tabs;
  }, [role]);

  // Handle local file upload
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Determine file type badge based on extension
    const extension = file.name.split('.').pop()?.toUpperCase() || "FILE";
    const validTypes = ["PDF", "DOCX", "MD"];
    const fileType = validTypes.includes(extension) ? extension : "FILE";

    const newDoc: DocumentArtifact = {
      id: `d-local-${Date.now()}`,
      fileName: file.name,
      fileType: fileType as any,
      uploadedBy: role === "student" ? "Alex Rivera" : "Dr. Sarah Chen",
      uploadedAt: new Date().toISOString().split("T")[0],
      size: formatBytes(file.size),
    };

    setLocalDocuments((prev) => [newDoc, ...prev]);
    
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
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

      <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-2">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${
              activeTab === tab.id ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {activeTab === "github" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">GitHub Activity</h2>
            {dataset.github.map((entry) => (
              <article key={entry.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">{entry.title}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {entry.author} - {entry.date} - {entry.ref}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${entry.type === "pr" ? "bg-violet-50 text-violet-700" : "bg-blue-50 text-blue-700"}`}>
                    {entry.type === "pr" ? "PR" : "Commit"}
                  </span>
                </div>
              </article>
            ))}
          </>
        )}

        {activeTab === "jira" && (
          <>
            <h2 className="text-3xl font-semibold text-blue-950">Jira Backlog and Tasks</h2>
            {dataset.jira.map((task) => (
              <article key={task.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">{task.key}: {task.title}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {task.assignee} - {task.sprint} - {task.points} pts
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getStatusPill(task.status)}`}>{task.status}</span>
                </div>
              </article>
            ))}
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
                accept=".pdf,.doc,.docx,.md,.txt"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                <Upload className="h-4 w-4" />
                Upload Document
              </button>
            </div>

            {localDocuments.map((doc) => (
              <article key={doc.id} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">{doc.fileName}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {doc.uploadedBy} - {doc.uploadedAt} - {doc.size}
                    </p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">{doc.fileType}</span>
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
              {dataset.sources.map((source) => (
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