export type JiraIngestionRun = {
  run_id: string;
  course_id: string;
  project_id: string;
  sprint_id: string;
  jira_project_key: string;
  jql: string;
  issue_count: number;
  captured_at: string;
  processed_at: string | null;
  processing_status: "pending" | "completed" | "failed";
  normalization_version: string | null;
  processing_error: string | null;
};

type JiraIngestionRunsTableProps = {
  runs: JiraIngestionRun[];
  onLoadCleanedRun: (run: JiraIngestionRun) => void;
};

export function JiraIngestionRunsTable({ runs, onLoadCleanedRun }: JiraIngestionRunsTableProps) {
  if (runs.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Sprint</th>
            <th className="px-3 py-2">Issues</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Captured</th>
            <th className="px-3 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id} className="border-b border-slate-100 last:border-0">
              <td className="px-3 py-2 font-medium text-slate-800">{run.sprint_id}</td>
              <td className="px-3 py-2 text-slate-600">{run.issue_count}</td>
              <td className="px-3 py-2">
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${run.processing_status === "completed" ? "bg-emerald-50 text-emerald-700" : run.processing_status === "failed" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>
                  {run.processing_status}
                </span>
              </td>
              <td className="px-3 py-2 text-slate-600">{new Date(run.captured_at).toLocaleString()}</td>
              <td className="px-3 py-2 text-right">
                {run.processing_status === "completed" && (
                  <button type="button" onClick={() => onLoadCleanedRun(run)} className="text-xs font-semibold text-blue-700 hover:text-blue-900">
                    View cleaned data
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}