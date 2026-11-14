"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { BlindLabelForm } from "@/features/insights/components/blind-label-form";
import { JudgeChip } from "@/features/insights/components/chips";
import { EvidencePanel } from "@/features/insights/components/evidence-panel";
import {
  DegradedNotice,
  JudgeTiles,
  PromptVersionsList,
  RevealComparison,
  TraceTimeline,
  UnacceptedCitationsTable,
} from "@/features/insights/components/reveal-panels";
import {
  useEvidence,
  useInsightsConfig,
  useJudgeStatus,
  useReveal,
  useSaveLabels,
  useTrace,
} from "@/features/insights/hooks/use-insights";
import { getErrorMessage } from "@/lib/api/client";

function RevealStep({ reportId }: { reportId: string }) {
  const reveal = useReveal(reportId, true);
  const judge = useJudgeStatus(reportId);
  const trace = useTrace(reportId, reveal.isSuccess);
  if (reveal.isLoading) return <p className="text-sm text-slate-500">Loading AI results…</p>;
  if (reveal.error || !reveal.data)
    return <p className="text-sm text-red-700">{getErrorMessage(reveal.error)}</p>;
  const r = reveal.data;
  const status = judge.data?.judgeStatus ?? r.judgeStatus;
  const override = r.comparison === "override";
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">
          {override ? "AI vs instructor override" : "AI vs your scores"}
        </h2>
        <p className="text-sm text-slate-600">
          Overall AI score {r.overallAiScore.toFixed(1)} / 10 · model{" "}
          <span className="font-mono">{r.modelName}</span>
        </p>
        <RevealComparison dimensions={r.dimensions} mode={r.comparison} />
      </section>
      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          Judge checks <JudgeChip status={status} />
        </h2>
        {status === "pending" && (
          <p className="text-sm text-slate-600">
            The judge is still running; this updates automatically.
          </p>
        )}
        <DegradedNotice notice={r.judge.notice} />
        <JudgeTiles tiles={r.judge.tiles} />
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Citations the judge did not fully accept</h2>
        {r.judge.available ? (
          <UnacceptedCitationsTable
            rows={r.judge.unacceptedCitations}
            truncated={r.judge.citationsTruncated}
          />
        ) : (
          <DegradedNotice notice={r.judge.notice} />
        )}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Trace timeline</h2>
        {trace.data &&
          (trace.data.available ? (
            <TraceTimeline trace={trace.data} />
          ) : (
            <DegradedNotice notice={trace.data.notice} />
          ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Prompt versions used</h2>
        <PromptVersionsList versions={r.promptVersions} />
      </section>
    </div>
  );
}

function BlindReportContent({ reportId }: { reportId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const evidence = useEvidence(reportId);
  const save = useSaveLabels(reportId);

  if (evidence.isLoading) return <p className="text-sm text-slate-500">Loading evidence…</p>;
  if (evidence.error || !evidence.data) {
    const notFound = (evidence.error as { status?: number } | null)?.status === 404;
    return (
      <p className="text-sm text-red-700">
        {notFound ? "Report not found, or not in your courses." : getErrorMessage(evidence.error)}
      </p>
    );
  }
  const ev = evidence.data;
  const showReveal = ev.canReveal && (searchParams.get("step") === "reveal" || ev.locked);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Link href="/insights" className="text-sm text-indigo-600 hover:underline">
          ← All runs
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">{ev.teamName}</h1>
        <p className="text-sm text-slate-600">
          {ev.courseCode} {ev.section} · {ev.sprintId}
        </p>
        <p className="text-sm font-medium text-slate-700">
          {showReveal
            ? "Step 2 of 2: Compare with the AI"
            : "Step 1 of 2: Score blind from the evidence"}
        </p>
      </header>
      {showReveal ? (
        <RevealStep reportId={reportId} />
      ) : (
        <>
          <EvidencePanel evidence={ev} />
          <BlindLabelForm
            key={reportId}
            initial={ev.labels}
            locked={ev.locked}
            saving={save.isPending}
            onSave={(labels, reveal) =>
              save.mutate(labels, {
                onSuccess: (result) => {
                  if (reveal && result.canReveal)
                    router.replace(`/insights/reports/${reportId}?step=reveal`);
                  else toast.success(`Saved ${result.labelsDone} of 6`);
                },
                onError: (error) => toast.error(getErrorMessage(error)),
              })
            }
          />
          {ev.canReveal && (
            <Link
              href={`/insights/reports/${reportId}?step=reveal`}
              className="inline-block text-sm font-medium text-indigo-600 hover:underline"
            >
              View AI results (locks your labels)
            </Link>
          )}
        </>
      )}
    </div>
  );
}

export const LOCKED_MESSAGE =
  "AI Insights unlock after this report's scores are saved on the Assessment Report page. Saving notifies the team's students.";

/** INSIGHTS_MODE=override_gate: no evidence step and no labels; the reveal is the whole page. */
function OverrideReportContent({ reportId }: { reportId: string }) {
  const reveal = useReveal(reportId, true);
  if (reveal.isLoading) return <p className="text-sm text-slate-500">Loading AI results…</p>;
  const status = (reveal.error as { status?: number } | null)?.status;
  if (status === 404)
    return <p className="text-sm text-red-700">Report not found, or not in your courses.</p>;
  if (status === 409) {
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
  if (reveal.error || !reveal.data)
    return <p className="text-sm text-red-700">{getErrorMessage(reveal.error)}</p>;
  const r = reveal.data;
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Link href="/insights" className="text-sm text-indigo-600 hover:underline">
          ← All runs
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">{r.teamName}</h1>
        <p className="text-sm text-slate-600">
          {r.courseCode} · {r.sprintId}
        </p>
      </header>
      <RevealStep reportId={reportId} />
    </div>
  );
}

export function ReportInsightsContent({ reportId }: { reportId: string }) {
  const config = useInsightsConfig();
  if (config.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  return config.data?.mode === "override_gate" ? (
    <OverrideReportContent reportId={reportId} />
  ) : (
    <BlindReportContent reportId={reportId} />
  );
}
