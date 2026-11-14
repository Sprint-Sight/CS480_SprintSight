"use client";

import { useState } from "react";
import {
  DIMENSIONS,
  DIMENSION_LABELS,
  MAX_REASON,
  type Dimension,
  type LabelDraft,
} from "@/features/insights/types";

type Draft = { score: string; reason: string };
type Props = {
  initial: LabelDraft[];
  locked: boolean;
  saving: boolean;
  onSave: (labels: LabelDraft[], reveal: boolean) => void;
};

export function BlindLabelForm({ initial, locked, saving, onSave }: Props) {
  const [drafts, setDrafts] = useState<Record<Dimension, Draft>>(
    () =>
      Object.fromEntries(
        DIMENSIONS.map((d) => {
          const found = initial.find((l) => l.dimension === d);
          return [d, { score: found ? String(found.score) : "", reason: found?.reason ?? "" }];
        }),
      ) as Record<Dimension, Draft>,
  );
  const filled = DIMENSIONS.filter((d) => drafts[d].score !== "");
  const complete = filled.length === DIMENSIONS.length;
  const toLabels = (): LabelDraft[] =>
    filled.map((d) => ({
      dimension: d,
      score: Number(drafts[d].score),
      reason: drafts[d].reason.trim() || null,
    }));
  const update = (d: Dimension, patch: Partial<Draft>) =>
    setDrafts((prev) => ({ ...prev, [d]: { ...prev[d], ...patch } }));

  return (
    <form
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (complete) onSave(toLabels(), true);
      }}
    >
      <div>
        <h2 className="text-base font-semibold text-slate-900">Your scores</h2>
        <p className="text-sm text-slate-600">
          Score each dimension 1–10 from the evidence alone. The AI score stays hidden until all six
          are submitted. After you reveal, labels are locked.
        </p>
      </div>
      {locked && (
        <p className="rounded bg-slate-100 p-2 text-sm text-slate-700">
          These labels are locked because the AI results were revealed.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {DIMENSIONS.map((d) => {
          const label = DIMENSION_LABELS[d];
          return (
            <fieldset key={d} className="space-y-2" disabled={locked || saving}>
              <legend className="text-sm font-medium text-slate-800">{label}</legend>
              <select
                aria-label={`${label} score`}
                value={drafts[d].score}
                onChange={(e) => update(d, { score: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              >
                <option value="">Select a score</option>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <textarea
                aria-label={`${label} reason`}
                maxLength={MAX_REASON}
                rows={2}
                value={drafts[d].reason}
                placeholder="Optional reason"
                onChange={(e) => update(d, { reason: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
              <p className="text-right text-xs text-slate-500">
                {drafts[d].reason.length}/{MAX_REASON}
              </p>
            </fieldset>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-sm text-slate-600">{filled.length} of 6 scored</span>
        <button
          type="button"
          disabled={locked || saving || filled.length === 0}
          onClick={() => onSave(toLabels(), false)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Save draft
        </button>
        <button
          type="submit"
          disabled={locked || saving || !complete}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "Saving…" : "Submit and reveal AI results"}
        </button>
      </div>
    </form>
  );
}
