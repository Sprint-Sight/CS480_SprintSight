import { JudgeChip } from "@/features/insights/components/chips";
import {
  DegradedNotice,
  JudgeTiles,
  PromptVersionsList,
  RevealComparison,
  TraceTimeline,
  UnacceptedCitationsTable,
} from "@/features/insights/components/reveal-panels";
import type { JudgeStatus, JudgeStatusView, Reveal, TraceView } from "@/features/insights/types";

type RevealReportProps = {
  reveal: Reveal;
  /** Latest judge status (polled); falls back to the one in `reveal`. */
  judgeStatus: JudgeStatus;
  /** Undefined while the trace is still loading. */
  trace: TraceView | undefined;
  /** Progress and elapsed time from the polled judge status; undefined until the first poll. */
  judgeProgress?: Pick<JudgeStatusView, "progress" | "elapsedMinutes">;
  onOpenPrompt: (name: string) => void;
};

/** The AI results for one report: scores vs instructor, judge checks, citations, trace, prompts. */
export function RevealReport({
  reveal,
  judgeStatus,
  trace,
  judgeProgress,
  onOpenPrompt,
}: RevealReportProps) {
  const override = reveal.comparison === "override";

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">
          {override ? "AI vs instructor override" : "AI vs your scores"}
        </h2>
        <p className="text-sm text-slate-600">
          Overall AI score {reveal.overallAiScore.toFixed(1)} / 10 · model{" "}
          <span className="font-mono">{reveal.modelName}</span>
        </p>
        <RevealComparison dimensions={reveal.dimensions} mode={reveal.comparison} />
      </section>
      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          Judge checks <JudgeChip status={judgeStatus} />
        </h2>
        {judgeStatus === "pending" && (
          <div className="space-y-1 text-sm text-slate-600">
            <p>The judge is still running; this updates automatically.</p>
            {judgeProgress?.progress && (
              <>
                <p>
                  Checked {judgeProgress.progress.done} of {judgeProgress.progress.total} batches ·
                  running for {judgeProgress.elapsedMinutes} min
                </p>
                <progress
                  className="h-2 w-64"
                  value={judgeProgress.progress.done}
                  max={judgeProgress.progress.total}
                />
              </>
            )}
            {(judgeProgress?.elapsedMinutes ?? 0) >= 20 && (
              <p className="text-amber-700">
                Taking longer than usual. The judge server may be busy or unreachable.
              </p>
            )}
          </div>
        )}
        <DegradedNotice notice={reveal.judge.notice} />
        <JudgeTiles tiles={reveal.judge.tiles} />
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Citations the judge did not fully accept</h2>
        {reveal.judge.available ? (
          <UnacceptedCitationsTable
            rows={reveal.judge.unacceptedCitations}
            truncated={reveal.judge.citationsTruncated}
          />
        ) : (
          <DegradedNotice notice={reveal.judge.notice} />
        )}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Trace timeline</h2>
        {trace &&
          (trace.available ? (
            <TraceTimeline trace={trace} />
          ) : (
            <DegradedNotice notice={trace.notice} />
          ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Prompt versions used</h2>
        <PromptVersionsList versions={reveal.promptVersions} onOpenPrompt={onOpenPrompt} />
      </section>
    </div>
  );
}
