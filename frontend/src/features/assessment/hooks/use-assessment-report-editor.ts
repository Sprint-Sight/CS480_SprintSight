"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildManualAssessmentPatch,
  patchAssessmentReport,
  type BackendAssessmentReport,
} from "@/features/assessment/assessment-api";
import type { RubricScore, SprintAssessmentReport } from "@/features/assessment/types";

type UseAssessmentReportEditorOptions = {
  report: SprintAssessmentReport;
  backendReport: BackendAssessmentReport | null;
  onSaved: (report: BackendAssessmentReport) => void;
};

export function useAssessmentReportEditor({
  report,
  backendReport,
  onSaved,
}: UseAssessmentReportEditorOptions) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(report);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const lastReportId = useRef(report.reportId);

  useEffect(() => {
    setDraft(report);
    setIsEditing(false);
    setSaveError("");
    if (lastReportId.current !== report.reportId) setSaveMessage("");
    lastReportId.current = report.reportId;
  }, [report]);

  const hasChanges = useMemo(() => JSON.stringify(draft) !== JSON.stringify(report), [draft, report]);
  const canSave = Boolean(report.reportId && backendReport && hasChanges && !isSaving);

  function updateRubricScore(categoryKey: string, patch: Partial<RubricScore>) {
    setDraft((current) => ({
      ...current,
      rubricScores: current.rubricScores.map((item) =>
        (item.categoryKey || item.category) === categoryKey ? { ...item, ...patch } : item,
      ),
    }));
    setSaveError("");
    setSaveMessage("");
  }

  function updateSummary(
    field: "strengths" | "weaknesses" | "recommendations",
    value: string,
  ) {
    setDraft((current) => ({
      ...current,
      [field]: value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    }));
    setSaveError("");
    setSaveMessage("");
  }

  function beginEditing() {
    setDraft(report);
    setIsEditing(true);
    setSaveError("");
    setSaveMessage("");
  }

  function cancelEditing() {
    setDraft(report);
    setIsEditing(false);
    setSaveError("");
    setSaveMessage("");
  }

  async function saveChanges() {
    if (!report.reportId || !backendReport || !hasChanges) return;
    const payload = buildManualAssessmentPatch(draft, backendReport);
    if (!payload) {
      setSaveError("This report is missing one or more required fields for the existing save endpoint. No changes were saved.");
      return;
    }

    setIsSaving(true);
    setSaveError("");
    setSaveMessage("");
    try {
      const updated = await patchAssessmentReport(report.reportId, payload);
      onSaved(updated);
      setIsEditing(false);
      setSaveMessage("Assessment report changes saved.");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Could not save the assessment report.");
    } finally {
      setIsSaving(false);
    }
  }

  return {
    draft,
    isEditing,
    isSaving,
    hasChanges,
    canSave,
    saveError,
    saveMessage,
    beginEditing,
    cancelEditing,
    saveChanges,
    updateRubricScore,
    updateSummary,
  };
}