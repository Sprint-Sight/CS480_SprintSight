import { AlertTriangle, X } from "lucide-react";
import type { JiraContributionStudent } from "@/features/peer-evaluation/peer-evaluation-api";

type JiraContributionOutlierModalProps = {
  isOpen: boolean;
  studentName: string;
  studentDetail: JiraContributionStudent | null;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
};

const formatPoints = (value: number | null) =>
  value === null ? "—" : value.toFixed(1).replace(/\.0$/, "");

export function JiraContributionOutlierModal({
  isOpen,
  studentName,
  studentDetail,
  isLoading,
  error,
  onClose,
}: JiraContributionOutlierModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="jira-contribution-modal-title"
        className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              <h2 id="jira-contribution-modal-title" className="text-lg font-semibold text-slate-900">
                Jira contribution evidence
              </h2>
            </div>
            <p className="mt-1 text-sm text-slate-600">{studentName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Jira contribution details"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[calc(90vh-76px)] space-y-4 overflow-y-auto p-5">
          {isLoading && <p role="status" className="text-sm text-slate-600">Loading Jira evidence...</p>}
          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </p>
          )}
          {studentDetail && (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard label="Total story points" value={formatPoints(studentDetail.total_story_points)} />
                <MetricCard label="Tickets" value={studentDetail.total_tickets} />
                <MetricCard label="Average points / ticket" value={formatPoints(studentDetail.average_points_per_ticket)} />
                <MetricCard label="Course average" value={formatPoints(studentDetail.course_average_total_points)} />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
                <span className="text-slate-600">
                  Course standard deviation: {formatPoints(studentDetail.course_total_score_std_dev)}
                </span>
                <span className="font-medium text-slate-800">
                  z-score: {formatPoints(studentDetail.contribution_z_score)}
                </span>
              </div>

              {studentDetail.is_contribution_outlier && (
                <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>
                    Jira contribution is flagged as a {studentDetail.outlier_direction ?? "course"} outlier.
                  </p>
                </div>
              )}

              <div>
                <h3 className="mb-2 font-semibold text-slate-900">Ticket evidence</h3>
                {studentDetail.tickets.length === 0 ? (
                  <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    No Jira tickets are available for this student.
                  </p>
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-3 py-2 text-left font-semibold text-slate-800">Ticket</th>
                          <th className="px-3 py-2 text-left font-semibold text-slate-800">Summary</th>
                          <th className="px-3 py-2 text-right font-semibold text-slate-800">Points</th>
                          <th className="px-3 py-2 text-left font-semibold text-slate-800">Status</th>
                          <th className="px-3 py-2 text-left font-semibold text-slate-800">Sprint</th>
                        </tr>
                      </thead>
                      <tbody>
                        {studentDetail.tickets.map((ticket) => (
                          <tr
                            key={`${ticket.project_id ?? ""}-${ticket.ticket_id}`}
                            className="border-t border-slate-100"
                          >
                            <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-900">
                              {ticket.ticket_id}
                            </td>
                            <td className="min-w-40 px-3 py-2 text-slate-700">
                              {ticket.summary || "—"}
                            </td>
                            <td className="px-3 py-2 text-right text-slate-700">
                              {formatPoints(ticket.story_points)}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 text-slate-700">
                              {ticket.status || "—"}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 text-slate-700">
                              {ticket.sprint_id || "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-medium uppercase text-slate-600">{label}</p>
      <p className="mt-1 text-xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
