"use client";

import { Check, History, PencilLine, RefreshCw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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
  const [role, setRole] = useState<"student" | "instructor">("instructor");
  const [criteria, setCriteria] = useState<ReviewCriterion[]>(INITIAL_REVIEW_CRITERIA);
  const [savedSnapshot, setSavedSnapshot] = useState<ReviewCriterion[]>(INITIAL_REVIEW_CRITERIA);
  const [auditHistory, setAuditHistory] = useState<AuditEvent[]>(INITIAL_AUDIT_HISTORY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { score: number; feedback: string }>>({});
  const [scoringEnabled, setScoringEnabled] = useState(true);
  const [criterionScoring, setCriterionScoring] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(INITIAL_REVIEW_CRITERIA.map((item) => [item.id, true])),
  );

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    if (savedRole === "student" || savedRole === "instructor") {
      setRole(savedRole);
    }
  }, []);

  const isInstructor = role === "instructor";

  const hasUnsavedChanges = useMemo(
    () => JSON.stringify(criteria) !== JSON.stringify(savedSnapshot),
    [criteria, savedSnapshot],
  );

  const aiOverallScore = useMemo(() => {
    if (INITIAL_REVIEW_CRITERIA.length === 0) return 0;
    const total = INITIAL_REVIEW_CRITERIA.reduce((sum, item) => sum + item.score, 0);
    return Math.round(total / INITIAL_REVIEW_CRITERIA.length);
  }, []);

  const overallScore = useMemo(() => {
    if (!scoringEnabled) return aiOverallScore;
    const scoredCriteria = scoringEnabled ? criteria.filter((item) => criterionScoring[item.id]) : [];
    if (scoredCriteria.length === 0) return 0;
    const total = scoredCriteria.reduce((sum, item) => sum + item.score, 0);
    return Math.round(total / scoredCriteria.length);
  }, [aiOverallScore, criteria, criterionScoring, scoringEnabled]);

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

  function beginEditing(item: ReviewCriterion) {
    setEditingId(item.id);
    setDrafts((prev) => ({
      ...prev,
      [item.id]: {
        score: item.score,
        feedback: item.feedback,
      },
    }));
  }

  function toggleAllScoring(enabled: boolean) {
    setScoringEnabled(enabled);
    setCriterionScoring(
      Object.fromEntries(criteria.map((item) => [item.id, enabled])),
    );
  }

  function toggleCriterionScoring(id: string) {
    setCriterionScoring((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function saveEditedItem(item: ReviewCriterion) {
    const draft = drafts[item.id];
    if (!draft) return;

    const next = {
      ...item,
      score: draft.score,
      feedback: draft.feedback,
    };

    setCriteria((prev) => prev.map((criterion) => (criterion.id === item.id ? next : criterion)));
    setSavedSnapshot((prev) => prev.map((criterion) => (criterion.id === item.id ? next : criterion)));
    setEditingId(null);
    prependAudit({
      type: "saved",
      actor: "Dr. Sarah Chen",
      title: "Instructor Override Saved",
      detail: `${item.category} score and feedback were saved to the review draft.`,
    });
  }

  function handleRegenerate() {
    setCriteria(INITIAL_REVIEW_CRITERIA);
    setSavedSnapshot(INITIAL_REVIEW_CRITERIA);
    setEditingId(null);
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

  if (!isInstructor) {
    return (
      <div className="space-y-5 p-8">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-xl font-semibold text-blue-950">Score and Feedback</h2>
          <div className="mt-4 space-y-3">
            {criteria.map((item) => (
              <article key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="mb-2 text-sm font-semibold text-slate-900">{item.category}</p>
                <p className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">{item.feedback}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    );
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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold text-blue-950">Score and Feedback Editor</h2>
          <button
            type="button"
            role="switch"
            aria-checked={scoringEnabled}
            onClick={() => toggleAllScoring(!scoringEnabled)}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-700"
          >
            <span
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
                scoringEnabled ? "bg-blue-900" : "bg-slate-300"
              }`}
            >
              <span
                className={`h-4 w-4 rounded-full bg-white transition ${scoringEnabled ? "translate-x-6" : "translate-x-1"}`}
              />
            </span>
            Score all components
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {criteria.map((item) => {
            const isEditing = editingId === item.id;
            const draft = drafts[item.id];

            return (
              <article key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{item.category}</p>

                  {!isEditing ? (
                    <button
                      type="button"
                      onClick={() => beginEditing(item)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                    >
                      <PencilLine className="h-3.5 w-3.5" />
                      Edit
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => saveEditedItem(item)}
                      className="inline-flex items-center gap-1 rounded-lg bg-blue-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-950"
                    >
                      <Save className="h-3.5 w-3.5" />
                      Save
                    </button>
                  )}
                </div>

                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={scoringEnabled && criterionScoring[item.id]}
                    onClick={() => toggleCriterionScoring(item.id)}
                    className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500"
                  >
                    <span
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${
                        scoringEnabled && criterionScoring[item.id] ? "bg-blue-900" : "bg-slate-300"
                      }`}
                    >
                      <span
                        className={`h-3.5 w-3.5 rounded-full bg-white transition ${
                          scoringEnabled && criterionScoring[item.id] ? "translate-x-4" : "translate-x-0.5"
                        }`}
                      />
                    </span>
                    Score
                  </button>
                  {isEditing && scoringEnabled && criterionScoring[item.id] ? (
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={draft?.score ?? item.score}
                      onChange={(event) => {
                        const raw = Number(event.target.value);
                        const next = Number.isNaN(raw) ? 0 : Math.min(100, Math.max(0, raw));
                        setDrafts((prev) => ({
                          ...prev,
                          [item.id]: {
                            score: next,
                            feedback: draft?.feedback ?? item.feedback,
                          },
                        }));
                      }}
                      className="h-8 w-16 rounded-md border border-slate-200 bg-white px-2 text-right text-sm font-semibold text-blue-900"
                    />
                  ) : (
                    <span
                      className={`h-8 min-w-16 rounded-md border px-2 text-right text-sm font-semibold leading-8 ${
                        scoringEnabled && criterionScoring[item.id]
                          ? "border-slate-200 bg-white text-blue-900"
                          : "border-slate-200 bg-slate-200 text-slate-400"
                      }`}
                    >
                      {scoringEnabled && criterionScoring[item.id] ? item.score : "--"}
                    </span>
                  )}
                </div>

                <div className="relative">
                  <PencilLine className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                  {isEditing ? (
                    <textarea
                      value={draft?.feedback ?? item.feedback}
                      onChange={(event) => {
                        setDrafts((prev) => ({
                          ...prev,
                          [item.id]: {
                            score: draft?.score ?? item.score,
                            feedback: event.target.value,
                          },
                        }));
                      }}
                      rows={2}
                      className="w-full rounded-md border border-slate-200 bg-white py-2 pl-8 pr-3 text-sm text-slate-700 outline-none ring-blue-100 focus:border-blue-300 focus:ring-2"
                    />
                  ) : (
                    <div className="min-h-[52px] rounded-md border border-slate-200 bg-white px-3 py-2 pl-8 text-sm text-slate-700">
                      {item.feedback}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
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
