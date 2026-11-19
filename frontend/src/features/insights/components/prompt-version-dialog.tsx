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
import type { PromptVersionDetail } from "@/features/insights/types";

export function PromptVersionDialog({
  name,
  version,
  role,
  detail,
  isLoading,
  isError,
  onClose,
}: {
  name: string;
  version: number;
  role: string;
  detail: PromptVersionDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl p-6" dismissOnOutsideClick>
        <DialogTitle className="font-mono text-base font-semibold">
          {name} v{version}
        </DialogTitle>
        <DialogDescription className="mt-1 text-sm text-slate-600">
          Opened from the <span className="font-medium">{role}</span> column
          {detail?.commitMessage && <> · {detail.commitMessage}</>}
          {detail?.createdAt && <> · created {new Date(detail.createdAt).toLocaleString()}</>}
        </DialogDescription>
        {isLoading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
        {isError && <p className="mt-4 text-sm text-red-700">Could not load this version.</p>}
        {detail?.notice && <p className="mt-4 text-sm text-amber-700">{detail.notice}</p>}
        {detail?.available && (
          <>
            <PromptAliases aliases={detail.aliases} emptyLabel="none" />
            {detail.diff && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold">
                  Changes from v{version - 1}
                </summary>
                <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-50 p-3 text-xs">
                  {detail.diff.split("\n").map((line, index) => (
                    <div
                      key={index}
                      className={
                        line.startsWith("+")
                          ? "bg-green-100 text-green-900"
                          : line.startsWith("-")
                            ? "bg-red-100 text-red-900"
                            : ""
                      }
                    >
                      {line || " "}
                    </div>
                  ))}
                </pre>
              </details>
            )}
            {detail.template && <PromptTemplateBlock template={detail.template} />}
          </>
        )}
        <DialogClose className="mt-4 rounded border px-3 py-1 text-sm">Close</DialogClose>
      </DialogContent>
    </Dialog>
  );
}
