"use client";

import { useState } from "react";
import { Send, Loader2 } from "lucide-react";

type StudentEvaluationFormProps = {
  teammateName: string;
  teammateId: string;
  projectId: string;
  isLoading: boolean;
  onSubmit: (data: {
    projectId: string;
    ratedId: string;
    score: number;
    remarks?: string;
    reason?: string;
  }) => Promise<void>;
};

export function StudentEvaluationForm({
  teammateName,
  teammateId,
  projectId,
  isLoading,
  onSubmit,
}: StudentEvaluationFormProps) {
  const [score, setScore] = useState<number>(3);
  const [remarks, setRemarks] = useState("");
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit({
        projectId,
        ratedId: teammateId,
        score,
        remarks: remarks || undefined,
        reason: reason || undefined,
      });
      setRemarks("");
      setReason("");
      setScore(3);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Evaluate {teammateName}</h3>

      <div className="space-y-4">
        {/* Score */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Rating (1-5 stars)
          </label>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                type="button"
                onClick={() => setScore(star)}
                className={`text-3xl transition-all ${
                  star <= score ? "text-yellow-400" : "text-slate-300"
                }`}
              >
                ★
              </button>
            ))}
          </div>
          <p className="text-sm text-slate-600 mt-1">You rated: {score}/5</p>
        </div>

        {/* Remarks */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Remarks (optional)
          </label>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value.slice(0, 1000))}
            placeholder="Share specific observations..."
            maxLength={1000}
            rows={3}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <p className="text-xs text-slate-500 mt-1">{remarks.length}/1000 characters</p>
        </div>

        {/* Reason */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Reason for this score (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 1000))}
            placeholder="Explain why you gave this rating..."
            maxLength={1000}
            rows={3}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <p className="text-xs text-slate-500 mt-1">{reason.length}/1000 characters</p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isSubmitting || isLoading}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isSubmitting || isLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting...
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              Submit Evaluation
            </>
          )}
        </button>
      </div>
    </form>
  );
}
