import { Loader2, Save } from "lucide-react";

type InstructorAiFeedbackEditorProps = {
  value: string;
  isLoading: boolean;
  isSaving: boolean;
  error: string;
  saveMessage: string;
  onChange: (value: string) => void;
  onSave: () => void;
};

const MAX_GUIDANCE_LENGTH = 5000;

export function InstructorAiFeedbackEditor({ value, isLoading, isSaving, error, saveMessage, onChange, onSave }: InstructorAiFeedbackEditorProps) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Grading Guidance</h2>
          <p className="mt-1 text-sm text-slate-500">Describe the deliverables, priorities, and evidence the AI should consider for this sprint.</p>
        </div>
        <span className="text-xs font-medium text-slate-500">{value.length.toLocaleString()} / {MAX_GUIDANCE_LENGTH.toLocaleString()}</span>
      </div>

      {isLoading ? (
        <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading saved guidance...</div>
      ) : (
        <textarea value={value} onChange={(event) => onChange(event.target.value)} maxLength={MAX_GUIDANCE_LENGTH} rows={12} placeholder="For this sprint, prioritize..." className="mt-4 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100" />
      )}

      {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
      {!isLoading && !error && !value && <p className="mt-3 text-sm text-slate-500">No guidance has been saved for this project and sprint yet.</p>}
      {saveMessage && <p className="mt-3 text-sm text-emerald-700">{saveMessage}</p>}

      <div className="mt-4 flex justify-end">
        <button type="button" onClick={onSave} disabled={isLoading || isSaving} className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50">
          {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {isSaving ? "Saving..." : "Save Guidance"}
        </button>
      </div>
    </section>
  );
}