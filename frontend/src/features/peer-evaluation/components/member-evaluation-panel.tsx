import { AlertTriangle, Star } from "lucide-react";
import type { MemberPeerEvaluationDetail } from "@/features/peer-evaluation/peer-evaluation-api";

type MemberEvaluationPanelProps = {
  members: MemberPeerEvaluationDetail[];
  jiraOutlierStudentIds: ReadonlySet<string>;
  isLoading: boolean;
  error: string | null;
  jiraReportError: string | null;
  onViewJiraContribution: (studentId: string) => void;
};

export function MemberEvaluationPanel({
  members,
  jiraOutlierStudentIds,
  isLoading,
  error,
  jiraReportError,
  onViewJiraContribution,
}: MemberEvaluationPanelProps) {
  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">Member evaluations</h3>
        <p className="mt-1 text-sm text-slate-600">
          Evaluations are grouped by the member who received them. Peer-score and Jira
          contribution outliers are shown separately.
        </p>
      </div>

      {jiraReportError && (
        <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Jira contribution alerts could not be loaded: {jiraReportError}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {isLoading && <p className="text-sm text-slate-600">Loading member evaluations...</p>}
      {!isLoading && !error && members.length === 0 && (
        <p className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          No peer evaluations have been submitted for this project yet.
        </p>
      )}

      {!isLoading && members.length > 0 && (
        <div className="space-y-4">
          {members.map((member) => (
            <article
              key={member.member_id}
              className="overflow-hidden rounded-lg border border-slate-200"
            >
              <header className="flex flex-wrap items-start justify-between gap-3 bg-slate-50 p-4">
                <div>
                  <h4 className="font-semibold text-slate-900">{member.member_full_name}</h4>
                  <p className="text-xs text-slate-600">{member.member_email}</p>
                  <p className="mt-1 text-xs text-slate-600">
                    Total {member.total_score} · Average {member.average_score ?? "—"} ·{" "}
                    {member.evaluation_count} received
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {member.is_total_outlier && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2.5 py-1 text-xs font-medium text-purple-800">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      Peer-score outlier ({member.outlier_direction})
                    </span>
                  )}
                  {jiraOutlierStudentIds.has(member.member_id) && (
                    <button
                      type="button"
                      onClick={() => onViewJiraContribution(member.member_id)}
                      className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-200"
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      Jira contribution outlier · View evidence
                    </button>
                  )}
                </div>
              </header>

              <div className="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Course average total</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {member.course_average_total ?? "—"}
                  </p>
                  <p className="text-xs text-slate-500">
                    SD {member.course_total_score_std_dev ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Peer-score z-score</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {member.total_z_score ?? "—"}
                  </p>
                  <p className="text-xs text-slate-500">
                    {member.students_below_course_average} of {member.enrolled_student_count} enrolled
                    below average
                  </p>
                </div>
              </div>

              <ul className="divide-y divide-slate-100">
                {member.evaluations.map((evaluation) => (
                  <li
                    key={evaluation.evaluation_id}
                    className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900">{evaluation.rater_full_name}</p>
                      <p className="text-xs text-slate-500">{evaluation.rater_email}</p>
                      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                        {evaluation.remarks || "No remarks."}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {new Date(evaluation.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <div className="flex gap-0.5" aria-label={`Score ${evaluation.score} out of 5`}>
                        {[1, 2, 3, 4, 5].map((star) => (
                          <Star
                            key={star}
                            aria-hidden="true"
                            className={`h-4 w-4 ${
                              star <= evaluation.score
                                ? "fill-yellow-400 text-yellow-400"
                                : "text-slate-300"
                            }`}
                          />
                        ))}
                      </div>
                      <span className="text-sm font-semibold text-slate-700">
                        {evaluation.score}/5
                      </span>
                      {evaluation.is_score_outlier && (
                        <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-800">
                          Score outlier
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
