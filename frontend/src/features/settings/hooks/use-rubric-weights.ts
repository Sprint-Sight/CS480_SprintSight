"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { INITIAL_SETTINGS } from "@/features/settings/data";
import { readScope } from "@/features/ingestion/scope-store";
import { coursesQueryOptions, type Course } from "@/features/projects/course-projects-api";
import {
  getRubricWeights,
  saveRubricWeights,
} from "@/features/settings/settings-api";
import type { RubricDimensionId, RubricWeight } from "@/features/settings/types";
import { getErrorMessage } from "@/lib/api/client";

/** The backend accepts totals within 0.99-1.01; stay inside that on the client. */
const TOTAL_TOLERANCE = 0.5;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function fromApiWeights(weights: Record<string, number>): RubricWeight[] {
  return INITIAL_SETTINGS.rubric.map((dimension) => ({
    ...dimension,
    value: typeof weights[dimension.id] === "number" ? weights[dimension.id] * 100 : 0,
  }));
}

function toApiWeights(rubric: RubricWeight[]): Record<string, number> {
  return Object.fromEntries(rubric.map((dimension) => [dimension.id, dimension.value / 100]));
}

function sameWeights(left: RubricWeight[], right: RubricWeight[]) {
  return left.every((dimension, index) => Math.abs(dimension.value - (right[index]?.value ?? 0)) < 0.001);
}

export function useRubricWeights(enabled: boolean) {
  const queryClient = useQueryClient();
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [rubric, setRubric] = useState<RubricWeight[]>(INITIAL_SETTINGS.rubric);
  const [savedRubric, setSavedRubric] = useState<RubricWeight[]>(INITIAL_SETTINGS.rubric);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  // Load the instructor's courses from the shared cache and default to the course chosen in the scope bar.
  useEffect(() => {
    if (!enabled) return;
    let isCurrent = true;
    setIsLoading(true);
    queryClient
      .fetchQuery(coursesQueryOptions())
      .then((courseList) => {
        if (!isCurrent) return;
        setCourses(courseList);
        const scopedCourseId = readScope().selectedCourseId;
        const initialCourse = courseList.find((course) => course.id === scopedCourseId) ?? courseList[0];
        setSelectedCourseId(initialCourse?.id ?? "");
        if (!initialCourse) setIsLoading(false);
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        setError(getErrorMessage(loadError, "Unable to load courses."));
        setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [enabled, queryClient]);

  // Load the selected course's saved weights.
  useEffect(() => {
    if (!enabled || !selectedCourseId) return;
    let isCurrent = true;
    setIsLoading(true);
    setError("");
    getRubricWeights(selectedCourseId)
      .then((response) => {
        if (!isCurrent) return;
        const loaded = fromApiWeights(response.weights);
        setRubric(loaded);
        setSavedRubric(loaded);
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        setError(getErrorMessage(loadError, "Unable to load rubric weights."));
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [enabled, selectedCourseId]);

  const totalWeight = useMemo(() => rubric.reduce((sum, dimension) => sum + dimension.value, 0), [rubric]);
  const isValidTotal = Math.abs(totalWeight - 100) <= TOTAL_TOLERANCE;
  const hasUnsavedChanges = !sameWeights(rubric, savedRubric);

  const updateWeight = (id: RubricDimensionId, value: number) => {
    setRubric((previous) =>
      previous.map((dimension) => (dimension.id === id ? { ...dimension, value: clamp(value, 0, 100) } : dimension)),
    );
  };

  const selectCourse = (courseId: string) => {
    setSelectedCourseId(courseId);
  };

  /** Resolves true when there is nothing to save or the save succeeded. */
  const saveWeights = async (): Promise<boolean> => {
    if (!hasUnsavedChanges) return true;
    if (!selectedCourseId) {
      setError("Select a course before saving rubric weights.");
      return false;
    }
    if (!isValidTotal) {
      setError("Rubric weights must add up to 100% before saving.");
      return false;
    }
    setIsSaving(true);
    setError("");
    try {
      const response = await saveRubricWeights(selectedCourseId, toApiWeights(rubric));
      const saved = fromApiWeights(response.weights);
      setRubric(saved);
      setSavedRubric(saved);
      return true;
    } catch (saveError) {
      setError(getErrorMessage(saveError, "Unable to save rubric weights."));
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  return {
    courses,
    selectedCourseId,
    selectCourse,
    rubric,
    totalWeight,
    isValidTotal,
    hasUnsavedChanges,
    isLoading,
    isSaving,
    error,
    updateWeight,
    saveWeights,
  };
}
