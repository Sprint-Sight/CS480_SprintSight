export type ArtifactTab = "github" | "jira" | "documents" | "communication";

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

export type ArtifactSourceSummary = {
  source: "GitHub" | "Jira" | "Documents";
  records: number;
  lastSyncedAt: string;
  parserStatus: "Healthy" | "Warning";
  evaluationUsage: string;
};

export type ArtifactProjectDataset = {
  projectId: string;
  github: GitHubArtifact[];
  jira: JiraTaskArtifact[];
  documents: DocumentArtifact[];
  communication: CommunicationArtifact[];
  sources: ArtifactSourceSummary[];
};
