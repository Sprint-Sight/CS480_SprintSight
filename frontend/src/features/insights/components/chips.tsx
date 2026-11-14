import { clsx } from "clsx";
import type { CitationCheck, JudgeStatus } from "@/features/insights/types";

const JUDGE: Record<JudgeStatus, { label: string; className: string }> = {
  complete: { label: "Complete", className: "bg-emerald-100 text-emerald-800" },
  pending: { label: "Pending", className: "bg-amber-100 text-amber-800" },
  unknown: { label: "Pending", className: "bg-amber-100 text-amber-800" },
  failed: { label: "Failed", className: "bg-red-100 text-red-800" },
  stale: { label: "Did not finish", className: "bg-slate-200 text-slate-700" },
  no_trace: { label: "No trace", className: "bg-slate-100 text-slate-600" },
};
const chip = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium";

export function HiddenValue() {
  return <span className="text-xs italic text-slate-500">Hidden until labelled</span>;
}

export function JudgeChip({ status }: { status: JudgeStatus }) {
  const s = JUDGE[status] ?? JUDGE.unknown;
  return <span className={clsx(chip, s.className)}>{s.label}</span>;
}

export function CitationChip({ check, hidden }: { check: CitationCheck | null; hidden: boolean }) {
  if (hidden) return <HiddenValue />;
  if (!check) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span
      className={clsx(
        chip,
        check.status === "ok" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800",
      )}
    >
      {Math.round(check.groundedRate * 100)}% grounded
      {check.status === "flagged" ? " · flagged" : ""}
    </span>
  );
}
