"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { useState } from "react";

import { BlindLabelForm } from "@/features/insights/components/blind-label-form";
import { EvidencePanel } from "@/features/insights/components/evidence-panel";
import { InsightsLockedNotice } from "@/features/insights/components/insights-locked-notice";
import { PromptDetailDialog } from "@/features/insights/components/prompt-detail-dialog";
import { ReportHeader } from "@/features/insights/components/report-header";
import { RevealReport } from "@/features/insights/components/reveal-report";
import {
  useEvidence,
  useInsightsConfig,
  useJudgeStatus,
  usePromptDetail,
  useReveal,
  useSaveLabels,
  useTrace,
} from "@/features/insights/hooks/use-insights";
import { getErrorMessage } from "@/lib/api/client";

const NOT_FOUND = "Report not found, or not in your courses.";
const httpStatus = (error: unknown) => (error as { status?: number } | null)?.status;

/** Loads the AI results, judge status, trace and the open prompt; RevealReport draws them. */
function RevealStep({ reportId }: { reportId: string }) {
  const [openPrompt, setOpenPrompt] = useState<string | null>(null);
  const reveal = useReveal(reportId, true);
  const judge = useJudgeStatus(reportId);
  const trace = useTrace(reportId, reveal.isSuccess);
  const prompt = usePromptDetail(reportId, openPrompt ?? "", openPrompt !== null);
  if (reveal.isLoading) return <p className="text-sm text-slate-500">Loading AI results…</p>;
  if (reveal.error || !reveal.data)
    return <p className="text-sm text-red-700">{getErrorMessage(reveal.error)}</p>;
  return (
    <>
      <RevealReport
        reveal={reveal.data}
        judgeStatus={judge.data?.judgeStatus ?? reveal.data.judgeStatus}
        judgeProgress={judge.data}
        trace={trace.data}
        onOpenPrompt={setOpenPrompt}
      />
      {openPrompt && (
        <PromptDetailDialog
          name={openPrompt}
          dimensions={reveal.data.dimensions}
          detail={prompt.data}
          isLoading={prompt.isLoading}
          isError={prompt.isError}
          onClose={() => setOpenPrompt(null)}
        />
      )}
    </>
  );
}

/** INSIGHTS_MODE=blind_label: score blind from the evidence (step 1), then compare (step 2). */
function BlindReportContent({ reportId }: { reportId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const evidence = useEvidence(reportId);
  const save = useSaveLabels(reportId);

  if (evidence.isLoading) return <p className="text-sm text-slate-500">Loading evidence…</p>;
  if (evidence.error || !evidence.data) {
    return (
      <p className="text-sm text-red-700">
        {httpStatus(evidence.error) === 404 ? NOT_FOUND : getErrorMessage(evidence.error)}
      </p>
    );
  }
  const ev = evidence.data;
  const showReveal = ev.canReveal && (searchParams.get("step") === "reveal" || ev.locked);

  return (
    <div className="space-y-6">
      <ReportHeader
        title={ev.teamName}
        subtitle={`${ev.courseCode} ${ev.section} · ${ev.sprintId}`}
        step={
          showReveal
            ? "Step 2 of 2: Compare with the AI"
            : "Step 1 of 2: Score blind from the evidence"
        }
      />
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

/** INSIGHTS_MODE=override_gate: no evidence step and no labels; the reveal is the whole page. */
function OverrideReportContent({ reportId }: { reportId: string }) {
  const reveal = useReveal(reportId, true);
  if (reveal.isLoading) return <p className="text-sm text-slate-500">Loading AI results…</p>;
  const status = httpStatus(reveal.error);
  if (status === 404) return <p className="text-sm text-red-700">{NOT_FOUND}</p>;
  if (status === 409) return <InsightsLockedNotice />;
  if (reveal.error || !reveal.data)
    return <p className="text-sm text-red-700">{getErrorMessage(reveal.error)}</p>;
  const r = reveal.data;
  return (
    <div className="space-y-6">
      <ReportHeader title={r.teamName} subtitle={`${r.courseCode} · ${r.sprintId}`} />
      <RevealStep reportId={reportId} />
    </div>
  );
}

export function ReportInsightsContent({ reportId }: { reportId: string }) {
  const config = useInsightsConfig();
  // The dashboard shell's <main> has no padding; each page adds the shared p-4/6/8 itself.
  // Wrapping here pads every state (loading, not found, locked, error and the report).
  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {config.isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : config.data?.mode === "override_gate" ? (
        <OverrideReportContent reportId={reportId} />
      ) : (
        <BlindReportContent reportId={reportId} />
      )}
    </div>
  );
}
