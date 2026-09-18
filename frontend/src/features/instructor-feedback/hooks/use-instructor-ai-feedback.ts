"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getInstructorGuidance, saveInstructorGuidance } from "@/features/instructor-feedback/instructor-ai-feedback-api";
import { readIngestionState } from "@/features/ingestion/state";

const MAX_GUIDANCE_LENGTH = 5000;

type Scope = {
  courseId: string;
  projectId: string;
  sprintId: string;
};

const emptyScope: Scope = { courseId: "", projectId: "", sprintId: "sprint-1" };

export function useInstructorAiFeedback() {
  const router = useRouter();
  const [scope, setScope] = useState<Scope>(emptyScope);
  const [expectationsText, setExpectationsText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");

  useEffect(() => {
    if (sessionStorage.getItem("sprintsight-auth-role") !== "instructor") {
      router.replace("/");
    }
  }, [router]);

  useEffect(() => {
    const updateScope = () => {
      const state = readIngestionState();
      setScope({
        courseId: state.selectedCourseId || "",
        projectId: state.selectedProjectId || "",
        sprintId: state.selectedSprintId || "sprint-1",
      });
    };

    updateScope();
    window.addEventListener("sprintsight-ingestion-updated", updateScope);
    return () => window.removeEventListener("sprintsight-ingestion-updated", updateScope);
  }, []);

  useEffect(() => {
    if (!scope.courseId || !scope.projectId || !scope.sprintId) {
      setExpectationsText("");
      setError("Select a course, project, and sprint from the shared scope to add grading guidance.");
      setIsLoading(false);
      return;
    }

    async function loadGuidance() {
      setIsLoading(true);
      setError("");
      setSaveMessage("");
      try {
        const response = await getInstructorGuidance(scope);
        setExpectationsText(response.expectations_text || "");
      } catch (loadError) {
        setExpectationsText("");
        setError(loadError instanceof Error ? loadError.message : "Could not load instructor guidance.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadGuidance();
  }, [scope]);

  const updateExpectationsText = (value: string) => {
    setExpectationsText(value.slice(0, MAX_GUIDANCE_LENGTH));
    setSaveMessage("");
  };

  const saveGuidance = async () => {
    const trimmedText = expectationsText.trim();
    if (!scope.courseId || !scope.projectId) {
      setError("Select a course and project from the shared scope before saving.");
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