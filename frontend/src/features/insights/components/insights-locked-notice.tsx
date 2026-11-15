import Link from "next/link";

export const LOCKED_MESSAGE =
  "AI Insights unlock after this report's scores are saved on the Assessment Report page. Saving notifies the team's students.";

/** override_gate mode: shown until the instructor has saved an override for the report. */
export function InsightsLockedNotice() {
  return (
    <div className="space-y-3">
      <Link href="/insights" className="text-sm text-indigo-600 hover:underline">
        ← All runs
      </Link>
      <div
        role="status"
        className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
      >
        <p className="font-medium">AI Insights are locked for this report</p>
        <p>{LOCKED_MESSAGE}</p>
        <Link
          href="/assessment-report"
          className="inline-block font-medium text-indigo-700 hover:underline"
        >
          Open Assessment Report
        </Link>
      </div>
    </div>
  );
}
