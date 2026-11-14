import type { Evidence } from "@/features/insights/types";

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <details
      className="rounded-lg border border-slate-200 bg-white p-3"
      open={count > 0 && count <= 15}
    >
      <summary className="cursor-pointer text-sm font-semibold text-slate-800">
        {title} <span className="font-normal text-slate-500">({count})</span>
      </summary>
      <div className="mt-2 max-h-80 overflow-y-auto text-sm">
        {count === 0 ? <p className="text-slate-500">None recorded for this sprint.</p> : children}
      </div>
    </details>
  );
}

export function EvidencePanel({ evidence }: { evidence: Evidence }) {
  const m = evidence.metrics;
  return (
    <section className="space-y-3" aria-label="Sprint evidence">
      <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <p className="font-semibold text-slate-800">Where to look</p>
        <ul className="mt-1 grid gap-1 sm:grid-cols-2">
          {evidence.dimensions.map((d) => (
            <li key={d.dimension}>
              <span className="font-medium">{d.label}:</span> {d.sources.join(", ")}
            </li>
          ))}
        </ul>
        {m && (
          <p className="mt-2 text-slate-600">
            Commit frequency {m.commitFrequency.toFixed(2)}/day · churn {m.codeChurn} lines
            {m.prTurnaroundHours != null && ` · PR turnaround ${m.prTurnaroundHours.toFixed(1)} h`}
            {m.completionPercent != null &&
              ` · ${m.completionPercent.toFixed(0)}% story points done`}
          </p>
        )}
      </div>
      <Section title="Commits" count={evidence.commitsTotal}>
        <ul className="divide-y divide-slate-100">
          {evidence.commits.map((c) => (
            <li key={c.sha} className="py-1.5">
              <span className="font-mono text-xs text-slate-500">{c.sha}</span>{" "}
              <span className="font-medium">{c.author}</span>: {c.message}
              <span className="ml-1 text-xs text-slate-500">
                (+{c.linesAdded}/−{c.linesDeleted}, {c.filesChanged} files)
              </span>
            </li>
          ))}
        </ul>
        {evidence.commitsTotal > evidence.commits.length && (
          <p className="mt-1 text-xs text-slate-500">
            Showing first {evidence.commits.length} of {evidence.commitsTotal}.
          </p>
        )}
      </Section>
      <Section title="Jira tickets" count={evidence.jira.length}>
        <ul className="divide-y divide-slate-100">
          {evidence.jira.map((t) => (
            <li key={t.key} className="py-1.5">
              <span className="font-mono text-xs">{t.key}</span> {t.summary}
              <span className="ml-1 text-xs text-slate-500">
                {[t.status, t.assignee, t.storyPoints != null ? `${t.storyPoints} pts` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Documents" count={evidence.documents.length}>
        <ul>
          {evidence.documents.map((d) => (
            <li key={d.filename + d.uploadedAt}>{d.filename}</li>
          ))}
        </ul>
      </Section>
      <Section title="Peer evaluations" count={evidence.peer.length}>
        <ul className="divide-y divide-slate-100">
          {evidence.peer.map((p, i) => (
            <li key={`${p.rater}-${p.rated}-${i}`} className="py-1.5">
              {p.rater} → {p.rated}: <span className="font-medium">{p.score}/5</span>
              {p.remarks && ` · ${p.remarks}`}
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}
