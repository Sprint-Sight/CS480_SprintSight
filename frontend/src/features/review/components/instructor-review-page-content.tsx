"use client";

import { Check, History, PencilLine, RefreshCw, Save } from "lucide-react";
import { useMemo, useState } from "react";

import { INITIAL_AUDIT_HISTORY, INITIAL_REVIEW_CRITERIA } from "@/features/review/data";
import type { ReviewAuditEvent, ReviewAuditEvent as AuditEvent, ReviewCriterion } from "@/features/review/types";

function nowLabel() {
  return new Date().toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function eventTone(type: ReviewAuditEvent["type"]) {
  if (type === "approved") return "bg-emerald-100 text-emerald-700";
  if (type === "modified") return "bg-amber-100 text-amber-700";
  if (type === "saved") return "bg-blue-100 text-blue-700";
  return "bg-slate-100 text-slate-700";
}

export default function InstructorReviewPageContent() {
  const [criteria, setCriteria] = useState<ReviewCriterion[]>(INITIAL_REVIEW_CRITERIA);
  const [savedSnapshot, setSavedSnapshot] = useState<ReviewCriterion[]>(INITIAL_REVIEW_CRITERIA);
  const [auditHistory, setAuditHistory] = useState<AuditEvent[]>(INITIAL_AUDIT_HISTORY);

  const hasUnsavedChanges = useMemo(
    () => JSON.stringify(criteria) !== JSON.stringify(savedSnapshot),
    [criteria, savedSnapshot],
  );

  const overallScore = useMemo(() => {
    if (criteria.length === 0) return 0;
    const total = criteria.reduce((sum, item) => sum + item.score, 0);
    return Math.round(total / criteria.length);
  }, [criteria]);

  function updateCriterion(id: string, patch: Partial<ReviewCriterion>) {
    setCriteria((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function prependAudit(event: Omit<AuditEvent, "id" | "timestamp">) {
    setAuditHistory((prev) => [
      {
        id: `audit-${Date.now()}`,
        timestamp: nowLabel(),
        ...event,
      },
      ...prev,
    ]);
  }

  function handleRegenerate() {
    setCriteria(INITIAL_REVIEW_CRITERIA);
    prependAudit({
      type: "generated",
      actor: "System",
      title: "AI Assessment Regenerated",
      detail: "Rubric scores and comments were regenerated from latest sprint artifacts.",
    });
  }

  function handleSaveChanges() {
    setSavedSnapshot(criteria);
    prependAudit({
      type: "saved",
      actor: "Dr. Sarah Chen",
      title: "Instructor Override Saved",
      detail: "Manual score and feedback adjustments were saved to the review draft.",
    });
  }

  function handleApprove() {
    setSavedSnapshot(criteria);
    prependAudit({
      type: "approved",
      actor: "Dr. Sarah Chen",
      title: "Final Review Approved",
      detail: "Instructor approved the final rubric with overrides and comments.",
    });
  }

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Instructor Review and Edit</h1>
          <p className="mt-1 text-sm text-slate-500">Team Alpha - E-Commerce Platform - Sprint 5</p>
          <p className={`mt-2 text-xs font-semibold ${hasUnsavedChanges ? "text-amber-600" : "text-emerald-600"}`}>
            {hasUnsavedChanges ? "Unsaved changes present" : "All changes saved"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRegenerate}
            className="inline-flex h-10 items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <RefreshCw className="h-4 w-4" />
            Regenerate
          </button>
          <button
            type="button"
            onClick={handleSaveChanges}
            className="inline-flex h-10 items-center gap-1 rounded-xl bg-blue-900 px-3 text-sm font-semibold text-white transition hover:bg-blue-950"
          >
            <Save className="h-4 w-4" />
            Save Changes
          </button>
          <button
            type="button"
            onClick={handleApprove}
            className="inline-flex h-10 items-center gap-1 rounded-xl bg-[#2F6690] px-3 text-sm font-semibold text-white transition hover:bg-[#285777]"
          >
            <Check className="h-4 w-4" />
            Approve
          </button>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-600">Overall Score</p>
          <p className="text-4xl font-bold text-blue-950">{overallScore}/100</p>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold text-blue-950">Score and Feedback Editor</h2>
        <div className="mt-4 space-y-3">
          {criteria.map((item) => (
            <article key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-900">{item.category}</p>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={item.score}
                  onChange={(event) => {
                    const raw = Number(event.target.value);
                    const next = Number.isNaN(raw) ? 0 : Math.min(100, Math.max(0, raw));
                    updateCriterion(item.id, { score: next });
                  }}
                  className="h-8 w-16 rounded-md border border-slate-200 bg-white px-2 text-right text-sm font-semibold text-blue-900"
                />
              </div>
              <div className="relative">
                <PencilLine className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                <textarea
                  value={item.feedback}
                  onChange={(event) => updateCriterion(item.id, { feedback: event.target.value })}
                  rows={2}
                  className="w-full rounded-md border border-slate-200 bg-white py-2 pl-8 pr-3 text-sm text-slate-700 outline-none ring-blue-100 focus:border-blue-300 focus:ring-2"
                />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="inline-flex items-center gap-2 text-xl font-semibold text-blue-950">
          <History className="h-5 w-5" />
          Audit History
        </h2>

        <div className="mt-4 space-y-2">
          {auditHistory.map((event) => (
            <article key={event.id} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{event.title}</p>
                  <p className="text-xs text-slate-500">by {event.actor}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${eventTone(event.type)}`}>
                    {event.type}
                  </span>
                  <span className="text-xs text-slate-500">{event.timestamp}</span>
                </div>
              </div>
              <p className="mt-1 text-sm text-slate-600">{event.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
