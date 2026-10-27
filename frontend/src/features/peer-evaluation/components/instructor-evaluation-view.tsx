"use client";

import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { EvaluationConfigPanel } from "@/features/peer-evaluation/components/evaluation-config-panel";
import { EvaluationTable } from "@/features/peer-evaluation/components/evaluation-table";
import { MemberEvaluationPanel } from "@/features/peer-evaluation/components/member-evaluation-panel";
import { usePeerEvaluation } from "@/features/peer-evaluation/hooks/use-peer-evaluation";

type InstructorEvaluationViewProps = {
  courseId: string;
};

export function InstructorEvaluationView({ courseId }: InstructorEvaluationViewProps) {
  const {
    courseEvaluations,
    evaluationConfig,
    isLoading,
    error,
    memberEvaluations,
    loadCourseEvaluations,
    loadEvaluationConfig,
    loadMemberEvaluations,
    updateEvaluationWindow,
    clearError,
  } = usePeerEvaluation();

  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  useEffect(() => {
    loadEvaluationConfig(courseId);
    loadCourseEvaluations(courseId);
  }, [courseId, loadEvaluationConfig, loadCourseEvaluations]);

  const selectedProject = selectedProjectId
    ? courseEvaluations?.projects.find((p) => p.project_id === selectedProjectId)
    : courseEvaluations?.projects[0];

  const evaluations = selectedProject?.evaluations || [];

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

      <EvaluationConfigPanel
        config={evaluationConfig}
        isLoading={isLoading}
        onUpdateConfig={(isOpen, expiresAt) => updateEvaluationWindow(courseId, isOpen, expiresAt)}
      />

      {/* Summary Stats */}
      {courseEvaluations && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium uppercase text-slate-600">Total Projects</p>
            <p className="text-2xl font-bold text-slate-900 mt-2">
              {courseEvaluations.total_projects}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium uppercase text-slate-600">Total Evaluations</p>
            <p className="text-2xl font-bold text-slate-900 mt-2">
              {courseEvaluations.total_evaluations}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium uppercase text-slate-600">Course Status</p>
            <p className={`text-sm font-medium mt-2 ${
              courseEvaluations.is_open ? "text-green-600" : "text-red-600"
            }`}>
              {courseEvaluations.is_open ? "Open" : "Closed"}
            </p>
          </div>
        </div>
      )}

      {/* Project Selection */}
      {courseEvaluations && courseEvaluations.projects.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Filter by Project
          </label>
          <select
            value={selectedProjectId || ""}
            onChange={(e) => setSelectedProjectId(e.target.value || null)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {courseEvaluations.projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_name} ({project.total_evaluations} evaluations)
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Average Score */}
      {selectedProject && selectedProject.average_score !== null && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="h-5 w-5 text-blue-600" />
            <p className="font-medium text-blue-900">Average Score</p>
          </div>
          <p className="text-2xl font-bold text-blue-600">{selectedProject.average_score.toFixed(2)}/5</p>
        </div>
      )}

      <MemberEvaluationPanel
        projectId={selectedProject?.project_id ?? null}
        members={[
          ...evaluations.map((evaluation) => ({
            id: evaluation.rated_id,
            name: evaluation.rated_full_name,
          })),
          ...evaluations.map((evaluation) => ({
            id: evaluation.rater_id,
            name: evaluation.rater_full_name,
          })),
        ]}
        detail={memberEvaluations}
        isLoading={isLoading}
        onSelectMember={loadMemberEvaluations}
      />

      {/* Evaluations Table */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4">
          {selectedProject ? `${selectedProject.project_name} Evaluations` : "Course Evaluations"}
        </h3>
        <EvaluationTable evaluations={evaluations} isLoading={isLoading} />
      </div>
    </div>
  );
}
