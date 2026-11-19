"use client";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  PromptAliases,
  PromptTemplateBlock,
} from "@/features/insights/components/prompt-template-block";
import type { PromptDetail, RevealDimension } from "@/features/insights/types";

export function PromptDetailDialog({
  name,
  dimensions,
  detail,
  isLoading,
  isError,
  onClose,
}: {
  name: string;
  dimensions: RevealDimension[];
  detail: PromptDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}) {
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
        {isLoading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
        {isError && <p className="mt-4 text-sm text-red-700">Could not load this prompt.</p>}
        {detail?.notice && <p className="mt-4 text-sm text-amber-700">{detail.notice}</p>}
        {detail && (
          <>
            <PromptAliases aliases={detail.aliases} />
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
            {detail.template && <PromptTemplateBlock template={detail.template} />}
          </>
        )}
        <DialogClose className="mt-4 rounded border px-3 py-1 text-sm">Close</DialogClose>
      </DialogContent>
    </Dialog>
  );
}
