"use client";

import { BrainCircuit } from "lucide-react";

import { InstructorAiFeedbackEditor } from "@/features/instructor-feedback/components/instructor-ai-feedback-editor";
import { useInstructorAiFeedback } from "@/features/instructor-feedback/hooks/use-instructor-ai-feedback";

export default function InstructorAiFeedbackPageContent() {
  const feedback = useInstructorAiFeedback();

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-8">
      <header className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-100 text-blue-700"><BrainCircuit className="h-5 w-5" /></div>
        <div><h1 className="text-3xl font-bold text-blue-950">Instructor AI Feedback</h1><p className="mt-1 text-sm text-slate-500">Set the grading expectations used by the AI assessment for the selected project and sprint.</p></div>
      </header>
      <InstructorAiFeedbackEditor value={feedback.expectationsText} isLoading={feedback.isLoading} isSaving={feedback.isSaving} error={feedback.error} saveMessage={feedback.saveMessage} onChange={feedback.updateExpectationsText} onSave={feedback.saveGuidance} />
    </div>
  );
}