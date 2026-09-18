"use client";

import { useEffect, useState } from "react";

import type { ResolvedAssessmentScope } from "@/features/assessment/assessment-scope";
import { getInstructorGuidance, saveInstructorGuidance } from "@/features/instructor-feedback/instructor-ai-feedback-api";

const MAX_GUIDANCE_LENGTH = 5000;

export function useInstructorAiFeedback(scope: ResolvedAssessmentScope | null, isOpen: boolean) {
  const [expectationsText, setExpectationsText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");

  useEffect(() => {
    if (!isOpen || !scope) {
      setExpectationsText("");
      setError("");
      setIsLoading(false);
      return;
    }
    const assessmentScope = scope;

    async function loadGuidance() {
      setIsLoading(true);
      setError("");
      setSaveMessage("");
      try {
        const response = await getInstructorGuidance(assessmentScope);
        setExpectationsText(response.expectations_text || "");
      } catch (loadError) {
        setExpectationsText("");
        setError(loadError instanceof Error ? loadError.message : "Could not load instructor guidance.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadGuidance();
  }, [isOpen, scope]);

  const updateExpectationsText = (value: string) => {
    setExpectationsText(value.slice(0, MAX_GUIDANCE_LENGTH));
    setSaveMessage("");
  };

  const saveGuidance = async () => {
    const trimmedText = expectationsText.trim();
    if (!scope) {
      setError("Select a valid course, project, and sprint before saving guidance.");
      return;
    }
    if (!trimmedText) {
      setError("Enter grading guidance before saving.");
      return;
    }

    setError("");
    setSaveMessage("");
    setIsSaving(true);
    try {
      await saveInstructorGuidance(scope, trimmedText);
      setExpectationsText(trimmedText);
      setSaveMessage("Guidance saved for the selected project and sprint.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save instructor guidance.");
    } finally {
      setIsSaving(false);
    }
  };

  return { expectationsText, isLoading, isSaving, error, saveMessage, updateExpectationsText, saveGuidance };
}