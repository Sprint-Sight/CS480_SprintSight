import type { ActionAuditRecord } from "@/features/audit/audit-api";

type ActionAuditTableProps = {
  records: ActionAuditRecord[];
  error: string;
  isLoading: boolean;
};

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

export function ActionAuditTable({ records, error, isLoading }: ActionAuditTableProps) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-4">
        <h2 className="text-lg font-semibold text-slate-900">Action History</h2>
        <p className="mt-1 text-sm text-slate-500">Recorded actions only; this may not include every activity in the system.</p>
      </div>
      {error ? (
        <p role="alert" className="p-5 text-sm text-rose-700">{error}</p>
      ) : isLoading ? (
        <p className="p-5 text-sm text-slate-500">Loading action history...</p>
      ) : records.length === 0 ? (
        <p className="p-5 text-sm text-slate-500">No action records are available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[850px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Time</th>
                <th className="px-4 py-3 font-semibold">Actor</th>
                <th className="px-4 py-3 font-semibold">Action</th>
                <th className="px-4 py-3 font-semibold">Target</th>
                <th className="px-4 py-3 font-semibold">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {records.map((record) => (
                <tr key={record.audit_id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-3">{formatTimestamp(record.created_at)}</td>
                  <td className="px-4 py-3"><span className="font-medium text-slate-900">{record.actor_role}</span><span className="block break-all text-xs text-slate-500">ID: {record.actor_id}</span></td>
                  <td className="px-4 py-3 font-medium text-slate-900">{record.action}</td>
                  <td className="px-4 py-3"><span>{record.target_type}</span><span className="block break-all text-xs text-slate-500">{record.target_id}</span></td>
                  <td className="max-w-sm px-4 py-3"><pre className="whitespace-pre-wrap break-words font-sans text-xs text-slate-600">{JSON.stringify(record.details, null, 2)}</pre></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
