"use client";

import { useEffect } from "react";
import { EvaluationStatusBanner } from "@/features/peer-evaluation/components/evaluation-status-banner";
import { TeammateEvaluationRow } from "@/features/peer-evaluation/components/teammate-evaluation-row";
import { usePeerEvaluation } from "@/features/peer-evaluation/hooks/use-peer-evaluation";
import type { PeerTeammate } from "@/features/peer-evaluation/peer-evaluation-api";

type StudentEvaluationViewProps = {
  courseId: string;
  projectId: string;
  teammates: PeerTeammate[];
};

export function StudentEvaluationView({ courseId, projectId, teammates }: StudentEvaluationViewProps) {
  const {
    myEvaluations,
    evaluationStatus,
    isLoading,
    error,
    loadMyEvaluations,
    checkEvaluationStatus,
    submitNewEvaluation,
    clearError,
  } = usePeerEvaluation();

  useEffect(() => {
    checkEvaluationStatus(courseId);
    loadMyEvaluations(projectId);
  }, [courseId, projectId, checkEvaluationStatus, loadMyEvaluations]);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={clearError}
            className="mt-2 text-sm font-medium text-red-600 hover:text-red-700"
          >
            Dismiss
          </button>
        </div>
      )}

      <EvaluationStatusBanner status={evaluationStatus} isLoading={isLoading} />

      {evaluationStatus?.can_evaluate && teammates.length === 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
          <p className="text-center text-blue-900">You have no teammates to evaluate in this project.</p>
        </div>
      )}

      {evaluationStatus?.can_evaluate &&
        teammates.map((teammate) => (
          <TeammateEvaluationRow
            key={teammate.id}
            teammate={teammate}
            existing={myEvaluations.find((e) => e.rated_id === teammate.id) ?? null}
            onSubmit={(data) => submitNewEvaluation({ projectId, ...data })}
          />
        ))}
    </div>
  );
}
