import type { OverrideAuditRecord } from "@/features/audit/audit-api";

type OverrideAuditTableProps = {
  records: OverrideAuditRecord[];
  error: string;
  isLoading: boolean;
};

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

export function OverrideAuditTable({ records, error, isLoading }: OverrideAuditTableProps) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-4">
        <h2 className="text-lg font-semibold text-slate-900">Score Overrides</h2>
        <p className="mt-1 text-sm text-slate-500">Recorded manual score changes, including the reason provided.</p>
      </div>
      {error ? (
        <p role="alert" className="p-5 text-sm text-rose-700">{error}</p>
      ) : isLoading ? (
        <p className="p-5 text-sm text-slate-500">Loading score overrides...</p>
      ) : records.length === 0 ? (
        <p className="p-5 text-sm text-slate-500">No score overrides are available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Time</th>
                <th className="px-4 py-3 font-semibold">Instructor ID</th>
                <th className="px-4 py-3 font-semibold">Student ID</th>
                <th className="px-4 py-3 font-semibold">Report</th>
                <th className="px-4 py-3 font-semibold">Score Change</th>
                <th className="px-4 py-3 font-semibold">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {records.map((record) => (
                <tr key={record.override_id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-3">{formatTimestamp(record.timestamp)}</td>
                  <td className="break-all px-4 py-3">{record.instructor_id}</td>
                  <td className="break-all px-4 py-3">{record.student_id}</td>
                  <td className="break-all px-4 py-3">{record.report_id}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{record.original_score}% <span className="text-slate-400">to</span> {record.new_score}%</td>
                  <td className="max-w-sm px-4 py-3">{record.reason_comment}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
