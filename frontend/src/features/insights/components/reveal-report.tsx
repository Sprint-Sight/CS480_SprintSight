import { JudgeChip } from "@/features/insights/components/chips";
import {
  DegradedNotice,
  JudgeTiles,
  PromptVersionsList,
  RevealComparison,
  TraceTimeline,
  UnacceptedCitationsTable,
} from "@/features/insights/components/reveal-panels";
import type { JudgeStatus, Reveal, TraceView } from "@/features/insights/types";

type RevealReportProps = {
  reveal: Reveal;
  /** Latest judge status (polled); falls back to the one in `reveal`. */
  judgeStatus: JudgeStatus;
  /** Undefined while the trace is still loading. */
  trace: TraceView | undefined;
};

/** The AI results for one report: scores vs instructor, judge checks, citations, trace, prompts. */
export function RevealReport({ reveal, judgeStatus, trace }: RevealReportProps) {
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
          <p className="text-sm text-slate-600">
            The judge is still running; this updates automatically.
          </p>
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
        <PromptVersionsList versions={reveal.promptVersions} />
      </section>
    </div>
  );
}
