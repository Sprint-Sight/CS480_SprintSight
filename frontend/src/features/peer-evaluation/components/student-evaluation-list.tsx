import { Star, Calendar } from "lucide-react";
import type { PeerEvaluationResponse } from "@/features/peer-evaluation/peer-evaluation-api";

type StudentEvaluationListProps = {
  evaluations: PeerEvaluationResponse[];
  isLoading: boolean;
};

export function StudentEvaluationList({
  evaluations,
  isLoading,
}: StudentEvaluationListProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <p className="text-center text-slate-600">Loading evaluations...</p>
      </div>
    );
  }

  if (evaluations.length === 0) {
    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
        <p className="text-center text-blue-900">
          No evaluations submitted yet. Start by evaluating your teammates above.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-slate-900">Your Evaluations</h3>
      {evaluations.map((evaluation) => (
            <div key={evaluation.evaluation_id} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                    <p className="font-medium text-slate-900">Teammate {evaluation.rated_id.slice(0, 8)}</p>
                <div className="flex gap-0.5">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <Star
                      key={star}
                      className={`h-4 w-4 ${
                            star <= evaluation.score
                          ? "fill-yellow-400 text-yellow-400"
                          : "text-slate-300"
                      }`}
                    />
                  ))}
                </div>
              </div>

                  {evaluation.remarks && (
                <div className="mb-2">
                  <p className="text-xs font-medium text-slate-600">Remarks:</p>
                      <p className="text-sm text-slate-700">{evaluation.remarks}</p>
                </div>
              )}

                  {evaluation.reason && (
                <div className="mb-2">
                  <p className="text-xs font-medium text-slate-600">Reason:</p>
                      <p className="text-sm text-slate-700">{evaluation.reason}</p>
                </div>
              )}

              <div className="flex items-center gap-1 text-xs text-slate-500">
                <Calendar className="h-3 w-3" />
                    {new Date(evaluation.created_at).toLocaleDateString()}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
