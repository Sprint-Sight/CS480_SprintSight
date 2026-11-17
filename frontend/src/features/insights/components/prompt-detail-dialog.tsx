"use client";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { usePromptDetail } from "@/features/insights/hooks/use-insights";
import type { RevealDimension } from "@/features/insights/types";

export function PromptDetailDialog({
  reportId,
  name,
  dimensions,
  onClose,
}: {
  reportId: string;
  name: string;
  dimensions: RevealDimension[];
  onClose: () => void;
}) {
  const query = usePromptDetail(reportId, name, true);
  const detail = query.data;
  const dimension = dimensions.find((item) => `Evaluate_${item.dimension}` === name);
  const stat = (label: string, value: string) => (
    <div className="rounded border border-slate-200 p-2">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl p-6" dismissOnOutsideClick>
        <DialogTitle className="font-mono text-base font-semibold">
          {name} {detail?.version && <>v{detail.version}</>}
        </DialogTitle>
        <DialogDescription className="mt-1 text-sm text-slate-600">
          {detail?.commitMessage || "Registered template recorded on this report's trace."}
          {detail?.createdAt && <> · created {new Date(detail.createdAt).toLocaleDateString()}</>}
        </DialogDescription>
        {query.isLoading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
        {query.isError && <p className="mt-4 text-sm text-red-700">Could not load this prompt.</p>}
        {detail?.notice && <p className="mt-4 text-sm text-amber-700">{detail.notice}</p>}
        {detail && (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-1">
              <span className="text-xs text-slate-500">Aliases now:</span>
              {detail.aliases.map((alias) => (
                <span key={alias} className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                  {alias}
                </span>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {dimension && stat("AI score", dimension.aiScore?.toString() ?? "failed")}
              {dimension && stat("Your score", dimension.yourScore?.toString() ?? "—")}
              {dimension && stat("Diff", dimension.diff?.toString() ?? "—")}
              {detail.spanDurationMs != null &&
                stat("Run time", `${(detail.spanDurationMs / 1000).toFixed(1)} s`)}
              {detail.spanStatus && stat("Span status", detail.spanStatus)}
              {detail.unacceptedCitations != null &&
                stat(
                  detail.unacceptedCitationsTruncated
                    ? "Citations not accepted (at least)"
                    : "Citations not accepted",
                  `${detail.unacceptedCitations}${detail.unacceptedCitationsTruncated ? "+" : ""}`,
                )}
            </div>
            {detail.template && (
              <div className="mt-4">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Prompt template</h3>
                  <button
                    type="button"
                    className="text-xs text-indigo-700 hover:underline"
                    onClick={() => void navigator.clipboard.writeText(detail.template ?? "")}
                  >
                    Copy
                  </button>
                </div>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">
                  {detail.template}
                </pre>
              </div>
            )}
          </>
        )}
        <DialogClose className="mt-4 rounded border px-3 py-1 text-sm">Close</DialogClose>
      </DialogContent>
    </Dialog>
  );
}
