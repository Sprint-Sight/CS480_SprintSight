import Link from "next/link";

type ReportHeaderProps = {
  title: string;
  subtitle: string;
  /** Optional progress line, e.g. "Step 1 of 2: …" in the blind labelling flow. */
  step?: string;
};

/** Back link to all runs, the team name and the course/sprint line for one report. */
export function ReportHeader({ title, subtitle, step }: ReportHeaderProps) {
  return (
    <header className="space-y-1">
      <Link href="/insights" className="text-sm text-indigo-600 hover:underline">
        ← All runs
      </Link>
      <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
      <p className="text-sm text-slate-600">{subtitle}</p>
      {step && <p className="text-sm font-medium text-slate-700">{step}</p>}
    </header>
  );
}
