"use client";

import { useEffect, useState } from "react";
import { EvaluationStatusBanner } from "@/features/peer-evaluation/components/evaluation-status-banner";
import { StudentEvaluationForm } from "@/features/peer-evaluation/components/student-evaluation-form";
import { StudentEvaluationList } from "@/features/peer-evaluation/components/student-evaluation-list";
import { usePeerEvaluation } from "@/features/peer-evaluation/hooks/use-peer-evaluation";

type StudentEvaluationViewProps = {
  courseId: string;
  projectId: string;
  currentUserId: string;
  teammates: Array<{ id: string; name: string }>;
};

export function StudentEvaluationView({
  courseId,
  projectId,
  teammates,
}: StudentEvaluationViewProps) {
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

  const [selectedTeammateIndex, setSelectedTeammateIndex] = useState(0);

  useEffect(() => {
    checkEvaluationStatus(courseId);
    loadMyEvaluations(projectId);
  }, [courseId, projectId, checkEvaluationStatus, loadMyEvaluations]);

  const currentTeammate = teammates && teammates.length > 0 ? teammates[selectedTeammateIndex] : null;

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

      {evaluationStatus?.can_evaluate && teammates && teammates.length > 0 && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Select Teammate to Evaluate
            </label>
            <select
              value={selectedTeammateIndex}
              onChange={(e) => setSelectedTeammateIndex(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              {teammates.map((teammate, idx) => (
                <option key={teammate.id} value={idx}>
                  {teammate.name}
                </option>
              ))}
            </select>
          </div>

          {currentTeammate && (
            <StudentEvaluationForm
              teammateName={currentTeammate.name}
              teammateId={currentTeammate.id}
              projectId={projectId}
              isLoading={isLoading}
              onSubmit={submitNewEvaluation}
            />
          )}
        </div>
      )}

      <StudentEvaluationList evaluations={myEvaluations} isLoading={isLoading} />
    </div>
  );
}
