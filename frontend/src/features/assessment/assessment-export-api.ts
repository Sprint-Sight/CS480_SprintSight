import { apiRequest, getAuthToken } from "@/features/projects/components/projects-api";

export type ExportPreviewData = {
  recordCount: number;
  estimatedSize: string;
  estimatedDuration: string;
  canExport: boolean;
};

export type ExportFormat = "pdf" | "csv";

// Backend response schema (uses snake_case)
export type ExportResponse = {
  download_url: string;
  expires_at: string;
  format: ExportFormat;
  report_id: string;
  include_student_emails: boolean;
  file_size_bytes: number;
};

type ExportFilters = {
  courseId: string;
  projectId: string;
  sprintId: string;
  includeStudentEmails?: boolean;
};

export const getExportPreview = (
  courseId: string,
  projectId: string,
  sprintId: string,
): Promise<ExportPreviewData> => {
  const queryParams = new URLSearchParams();
  queryParams.append("course_id", courseId);
  queryParams.append("project_id", projectId);
  queryParams.append("sprint_id", sprintId);

  return apiRequest<ExportPreviewData>(`/export/preview?${queryParams.toString()}`, {
    method: "GET",
  });
};

export const exportToPDF = (filters: ExportFilters): Promise<ExportResponse> => {
  return apiRequest<ExportResponse>(`/export/pdf`, {
    method: "POST",
    body: JSON.stringify({
      course_id: filters.courseId,
      project_id: filters.projectId,
      sprint_id: filters.sprintId,
      format: "pdf",
      include_student_emails: filters.includeStudentEmails ?? false,
    }),
  });
};

export const exportToCSV = (filters: ExportFilters): Promise<ExportResponse> => {
  return apiRequest<ExportResponse>(`/export/csv`, {
    method: "POST",
    body: JSON.stringify({
      course_id: filters.courseId,
      project_id: filters.projectId,
      sprint_id: filters.sprintId,
      format: "csv",
      include_student_emails: filters.includeStudentEmails ?? false,
    }),
  });
};

export const downloadExportedFile = async (
  downloadUrl: string,
  fileName: string,
): Promise<void> => {
  const authToken = getAuthToken();
  if (!authToken) {
    throw new Error("You are not signed in. Please log in again.");
  }

  // Convert relative path to full backend URL
  const backendApiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
  const baseUrl = backendApiBase.replace(/\/api\/v1$/, ""); // Remove /api/v1 suffix
  const fullUrl = downloadUrl.startsWith("http")
    ? downloadUrl
    : `${baseUrl}${downloadUrl}`;

  const response = await fetch(fullUrl, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${authToken}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to download file. The download link may have expired.");
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};
