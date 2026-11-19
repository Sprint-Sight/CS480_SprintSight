export type ArtifactTab = "github" | "jira" | "documents" | "communication" | "peer-evaluation";

export type GitHubArtifact = {
  id: string;
  title: string;
  author: string;
  date: string;
  ref: string;
  type: "commit" | "pr";
  status?: "merged" | "open" | "closed";
};

export type JiraTaskArtifact = {
  id: string;
  key: string;
  title: string;
  assignee: string;
  sprint: string;
  status: "Done" | "In Progress" | "To Do";
  points: number;
};

export type DocumentArtifact = {
  id: string;
  fileName: string;
  fileType: "PDF" | "DOCX" | "PPTX" | "DOC" | "TXT" | "MD" | "Document";
  uploadedBy: string;
  uploadedAt: string;
  size: string;
};

export type CommunicationArtifact = {
  id: string;
  channel: string;
  summary: string;
  capturedAt: string;
};

export type PeerEvaluationArtifact = {
  id: string;
  reviewer: string;
  target: string;
  score: number;
  sprint: string;
};

export type ArtifactSourceSummary = {
  source: "GitHub" | "Jira" | "Documents";
  records: number;
  lastSyncedAt: string;
  evaluationUsage: string;
};

export type ArtifactProjectDataset = {
  projectId: string;
  github: GitHubArtifact[];
  jira: JiraTaskArtifact[];
  documents: DocumentArtifact[];
  communication: CommunicationArtifact[];
  peerEvaluation: PeerEvaluationArtifact[];
  sources: ArtifactSourceSummary[];
};

/** One Jira ingestion snapshot for a project sprint, as returned by /jira-ingestion/runs. */
export type JiraIngestionRun = {
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
