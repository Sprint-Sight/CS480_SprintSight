import type { UnmatchedCommit } from "@/features/collaboration/types";

type Props = {
  commits: UnmatchedCommit[];
};

function formatTimestamp(timestamp: string) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
}

export function UnmatchedCommitsPanel({ commits }: Props) {
  if (commits.length === 0) return null;

  const linesChanged = commits.reduce(
    (total, commit) => total + commit.linesAdded + commit.linesDeleted,
    0,
  );

  return (
    <details className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
      <summary className="cursor-pointer list-none text-sm font-semibold text-amber-950">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span>{commits.length} unmatched {commits.length === 1 ? "commit" : "commits"}</span>
          <span className="text-xs font-medium text-amber-800">
            {linesChanged.toLocaleString()} lines changed · View details
          </span>
        </span>
      </summary>
      <p className="mt-2 text-xs text-amber-900">
        These commits could not be linked to a project member and are excluded from the member chart. They are listed individually without guessing an identity.
      </p>
      <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-amber-200 bg-white">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead className="sticky top-0 bg-amber-50 text-amber-900">
            <tr>
              <th className="px-3 py-2 font-semibold">Author label</th>
              <th className="px-3 py-2 font-semibold">Commit</th>
              <th className="px-3 py-2 font-semibold">Timestamp</th>
              <th className="px-3 py-2 text-right font-semibold">Lines changed</th>
            </tr>
          </thead>
          <tbody>
            {commits.map((commit) => (
              <tr key={commit.sha} className="border-t border-slate-100">
                <td className="px-3 py-2 text-slate-700">{commit.author}</td>
                <td className="px-3 py-2 font-mono text-slate-600">{commit.sha.slice(0, 10)}</td>
                <td className="px-3 py-2 text-slate-600">{formatTimestamp(commit.timestamp)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                  {(commit.linesAdded + commit.linesDeleted).toLocaleString()}
                  <span className="ml-1 text-slate-400">
                    (+{commit.linesAdded.toLocaleString()} / -{commit.linesDeleted.toLocaleString()})
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
