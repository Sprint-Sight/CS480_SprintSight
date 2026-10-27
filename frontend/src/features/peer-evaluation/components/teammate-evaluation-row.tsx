"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, Send } from "lucide-react";
import { ScoreScale } from "@/features/peer-evaluation/components/score-scale";
import type { PeerEvaluationResponse, PeerTeammate } from "@/features/peer-evaluation/peer-evaluation-api";

type TeammateEvaluationRowProps = {
  teammate: PeerTeammate;
  existing: PeerEvaluationResponse | null;
  onSubmit: (data: {
    evaluationId?: string;
    ratedId: string;
    score: number;
    remarks?: string;
  }) => Promise<void>;
};

export function TeammateEvaluationRow({ teammate, existing, onSubmit }: TeammateEvaluationRowProps) {
  const [score, setScore] = useState(existing?.score ?? 3);
  const [remarks, setRemarks] = useState(existing?.remarks ?? "");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!existing) return;
    setScore(existing.score);
    setRemarks(existing.remarks ?? "");
  }, [existing]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit({
        evaluationId: existing?.evaluation_id,
        ratedId: teammate.id,
        score,
        remarks: remarks.trim() || undefined,
      });
    } catch {
      // The error is surfaced by the page-level banner.
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">{teammate.name}</h3>
        {existing && (
          <span className="flex items-center gap-1 text-xs font-medium text-green-700">
            <CheckCircle2 className="h-4 w-4" />
            Submitted {new Date(existing.created_at).toLocaleDateString()}
          </span>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-2 block text-sm font-medium text-slate-700">
            Score: <span className="font-semibold text-blue-700">{score}</span> / 5
          </label>
          <ScoreScale value={score} onChange={setScore} disabled={isSubmitting} />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-slate-700">Remarks (optional)</label>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value.slice(0, 1000))}
            placeholder="Any additional observations..."
            rows={3}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting...
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              {existing ? "Update Evaluation" : "Submit Evaluation"}
            </>
          )}
        </button>
      </div>
    </form>
  );
}
