"use client";

import { useState, useCallback } from "react";
import {
  getExportPreview,
  exportToPDF,
  exportToCSV,
  downloadExportedFile,
  type ExportPreviewData,
  type ExportFormat,
} from "@/features/assessment/assessment-export-api";

export type ExportState = "idle" | "loading-preview" | "preview-ready" | "exporting" | "success" | "error";

type ExportFilters = {
  courseId: string;
  projectId: string;
  sprintId: string;
  includeStudentEmails?: boolean;
};

export function useAssessmentExport() {
  const [state, setState] = useState<ExportState>("idle");
  const [previewData, setPreviewData] = useState<ExportPreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat | null>(null);

  const loadPreview = useCallback(async (filters: ExportFilters) => {
    try {
      setState("loading-preview");
      setError(null);
      const data = await getExportPreview(filters.courseId, filters.projectId, filters.sprintId);
      setPreviewData(data);
      setState("preview-ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load preview";
      setError(message);
      setState("error");
    }
  }, []);

  const handleExportPDF = useCallback(async (filters: ExportFilters) => {
    try {
      setState("exporting");
      setError(null);
      setSelectedFormat("pdf");

      const response = await exportToPDF(filters);
      // Construct filename from report data
      const fileName = `assessment-report-${filters.sprintId}.pdf`;
      await downloadExportedFile(response.download_url, fileName);

      setState("success");
      setTimeout(() => {
        setState("idle");
        setPreviewData(null);
        setSelectedFormat(null);
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to export PDF";
      setError(message);
      setState("error");
    }
  }, []);

  const handleExportCSV = useCallback(async (filters: ExportFilters) => {
    try {
      setState("exporting");
      setError(null);
      setSelectedFormat("csv");

      const response = await exportToCSV(filters);
      // Construct filename from report data
      const fileName = `assessment-report-${filters.sprintId}.csv`;
      await downloadExportedFile(response.download_url, fileName);

      setState("success");
      setTimeout(() => {
        setState("idle");
        setPreviewData(null);
        setSelectedFormat(null);
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to export CSV";
      setError(message);
      setState("error");
    }
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setPreviewData(null);
    setError(null);
    setSelectedFormat(null);
  }, []);

  return {
    state,
    previewData,
    error,
    selectedFormat,
    loadPreview,
    handleExportPDF,
    handleExportCSV,
    reset,
  };
}
