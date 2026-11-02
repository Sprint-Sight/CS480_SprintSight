import { AlertCircle, CheckCircle, Clock } from "lucide-react";
import type { EvaluationStatusResponse } from "@/features/peer-evaluation/peer-evaluation-api";

type EvaluationStatusBannerProps = {
  status: EvaluationStatusResponse | null;
  isLoading: boolean;
};

export function EvaluationStatusBanner({ status, isLoading }: EvaluationStatusBannerProps) {
  if (isLoading || !status) return null;

  const { can_evaluate, is_open, expires_at, message } = status;

  if (!can_evaluate) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 flex-shrink-0 text-amber-600 mt-0.5" />
          <div>
            <p className="font-medium text-amber-900">{message}</p>
            {expires_at && (
              <p className="text-sm text-amber-800 mt-1">
                Expires: {new Date(expires_at).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-green-200 bg-green-50 p-4">
      <div className="flex items-start gap-3">
        <CheckCircle className="h-5 w-5 flex-shrink-0 text-green-600 mt-0.5" />
        <div>
          <p className="font-medium text-green-900">Evaluation Window Open</p>
          {expires_at && (
            <p className="text-sm text-green-800 mt-1 flex items-center gap-1">
              <Clock className="h-4 w-4" />
              Expires: {new Date(expires_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
