"use client";

import { BrainCircuit, X } from "lucide-react";

import type { ResolvedAssessmentScope } from "@/features/assessment/assessment-scope";
import { InstructorAiFeedbackEditor } from "@/features/instructor-feedback/components/instructor-ai-feedback-editor";
import { useInstructorAiFeedback } from "@/features/instructor-feedback/hooks/use-instructor-ai-feedback";

type InstructorAiFeedbackModalProps = {
  isOpen: boolean;
  scope: ResolvedAssessmentScope | null;
  onClose: () => void;
};

export function InstructorAiFeedbackModal({ isOpen, scope, onClose }: InstructorAiFeedbackModalProps) {
  const feedback = useInstructorAiFeedback(scope, isOpen);
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="instructor-ai-feedback-title">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 text-blue-700"><BrainCircuit className="h-5 w-5" /></div>
            <div>
              <h2 id="instructor-ai-feedback-title" className="text-xl font-bold text-blue-950">Instructor AI Feedback</h2>
              <p className="mt-1 text-sm text-slate-500">{scope?.projectLabel} - {scope?.sprintId}</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close instructor AI feedback"><X className="h-5 w-5" /></button>
        </div>
        <div className="pt-5">
          <InstructorAiFeedbackEditor value={feedback.expectationsText} isLoading={feedback.isLoading} isSaving={feedback.isSaving} error={feedback.error} saveMessage={feedback.saveMessage} onChange={feedback.updateExpectationsText} onSave={feedback.saveGuidance} />
        </div>
      </div>
    </div>
  );
}