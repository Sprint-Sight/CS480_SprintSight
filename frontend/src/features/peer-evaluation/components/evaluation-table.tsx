import { Star, Calendar } from "lucide-react";
import type { PeerEvaluationInstructorView } from "@/features/peer-evaluation/peer-evaluation-api";

type EvaluationTableProps = {
  evaluations: PeerEvaluationInstructorView[];
  isLoading: boolean;
};

export function EvaluationTable({ evaluations, isLoading }: EvaluationTableProps) {
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
        <p className="text-center text-blue-900">No peer evaluations submitted yet.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Rater</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Rated</th>
            <th className="px-4 py-3 text-center font-semibold text-slate-900">Score</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Remarks</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Reason</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Date</th>
          </tr>
        </thead>
        <tbody>
          {evaluations.map((evaluation) => (
            <tr key={evaluation.evaluation_id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3">
                <div>
                  <p className="font-medium text-slate-900">{evaluation.rater_full_name}</p>
                  <p className="text-xs text-slate-600">{evaluation.rater_email}</p>
                </div>
              </td>
              <td className="px-4 py-3">
                <div>
                  <p className="font-medium text-slate-900">{evaluation.rated_full_name}</p>
                  <p className="text-xs text-slate-600">{evaluation.rated_email}</p>
                </div>
              </td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-0.5">
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
              </td>
              <td className="px-4 py-3 max-w-xs truncate text-slate-700">
                {evaluation.remarks || "—"}
              </td>
              <td className="px-4 py-3 max-w-xs truncate text-slate-700">
                {evaluation.reason || "—"}
              </td>
              <td className="px-4 py-3 text-slate-600">
                <div className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {new Date(evaluation.created_at).toLocaleDateString()}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
