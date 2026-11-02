"use client";

import { useEffect, useMemo } from "react";
import { BarChart3 } from "lucide-react";
import { EvaluationConfigPanel } from "@/features/peer-evaluation/components/evaluation-config-panel";
import { JiraContributionOutlierModal } from "@/features/peer-evaluation/components/jira-contribution-outlier-modal";
import { MemberEvaluationPanel } from "@/features/peer-evaluation/components/member-evaluation-panel";
import { useJiraContributionOutliers } from "@/features/peer-evaluation/hooks/use-jira-contribution-outliers";
import { useProjectMemberEvaluations } from "@/features/peer-evaluation/hooks/use-project-member-evaluations";
import { usePeerEvaluation } from "@/features/peer-evaluation/hooks/use-peer-evaluation";

type InstructorEvaluationViewProps = {
  courseId: string;
  projectId: string;
};

export function InstructorEvaluationView({ courseId, projectId }: InstructorEvaluationViewProps) {
  const {
    courseEvaluations,
    projectEvaluations,
    evaluationConfig,
    isLoading,
    error,
    loadCourseEvaluations,
    loadProjectEvaluations,
    loadEvaluationConfig,
    updateEvaluationWindow,
    clearError,
  } = usePeerEvaluation();

  const jiraOutliers = useJiraContributionOutliers();

  useEffect(() => {
    loadEvaluationConfig(courseId);
    loadCourseEvaluations(courseId);
    jiraOutliers.loadReport(courseId);
  }, [courseId, loadEvaluationConfig, loadCourseEvaluations, jiraOutliers.loadReport]);

  useEffect(() => {
    loadProjectEvaluations(projectId);
  }, [projectId, loadProjectEvaluations]);

  const ratedMemberIds = useMemo(
    () => Array.from(
      new Set(
        projectEvaluations?.project_id === projectId
          ? projectEvaluations.evaluations.map((evaluation) => evaluation.rated_id)
          : [],
      ),
    ),
    [projectEvaluations, projectId],
  );
  const selectedProjectEvaluations =
    projectEvaluations?.project_id === projectId ? projectEvaluations : null;
  const memberDetails = useProjectMemberEvaluations(projectId, ratedMemberIds);
  const jiraOutlierStudentIds = useMemo(
    () => new Set(
      jiraOutliers.report?.students
        .filter((student) => student.is_contribution_outlier)
        .map((student) => student.student_id) ?? [],
    ),
    [jiraOutliers.report],
  );
  const selectedJiraStudentName =
    jiraOutliers.report?.students.find(
      (student) => student.student_id === jiraOutliers.selectedStudentId,
    )?.student_full_name ?? "Student";

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
        onUpdateConfig={(payload) => updateEvaluationWindow(courseId, payload)}
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

      {/* Average Score */}
      {selectedProjectEvaluations && selectedProjectEvaluations.average_score !== null && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="h-5 w-5 text-blue-600" />
            <p className="font-medium text-blue-900">Average Score</p>
          </div>
          <p className="text-2xl font-bold text-blue-600">{selectedProjectEvaluations.average_score.toFixed(2)}/5</p>
        </div>
      )}

      <MemberEvaluationPanel
        members={memberDetails.members}
        jiraOutlierStudentIds={jiraOutlierStudentIds}
        isLoading={memberDetails.isLoading}
        error={memberDetails.error}
        jiraReportError={jiraOutliers.selectedStudentId ? null : jiraOutliers.error}
        onViewJiraContribution={(studentId) => jiraOutliers.selectStudent(courseId, studentId)}
      />

      <JiraContributionOutlierModal
        isOpen={Boolean(jiraOutliers.selectedStudentId)}
        studentName={selectedJiraStudentName}
        studentDetail={jiraOutliers.studentDetail}
        isLoading={jiraOutliers.isDetailLoading}
        error={jiraOutliers.selectedStudentId ? jiraOutliers.error : null}
        onClose={jiraOutliers.closeStudentDetail}
      />
    </div>
  );
}
