export type GitIngestionRun = {
  sprintId: string;
  recordCount: number;
  capturedAt: string;
};

type GitIngestionRunsTableProps = {
  runs: GitIngestionRun[];
};

export function GitIngestionRunsTable({ runs }: GitIngestionRunsTableProps) {
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
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.sprintId} className="border-b border-slate-100 last:border-0">
              <td className="px-3 py-2 font-medium text-slate-800">{run.sprintId}</td>
              <td className="px-3 py-2 text-slate-600">{run.recordCount}</td>
              <td className="px-3 py-2">
                <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                  completed
                </span>
              </td>
              <td className="px-3 py-2 text-slate-600">{new Date(run.capturedAt).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}