"use client";

import { useState, useCallback } from "react";
import {
  submitEvaluation,
  updateEvaluation,
  getMyEvaluations,
  getEvaluationStatus,
  getCourseEvaluations,
  getProjectEvaluations,
  getMemberEvaluations,
  getEvaluationConfig,
  setEvaluationConfig,
  type PeerEvaluationResponse,
  type CoursePeerEvaluationSummary,
  type PeerEvaluationSummary,
  type MemberPeerEvaluationDetail,
  type EvaluationStatusResponse,
  type PeerEvaluationConfigResponse,
  type SetConfigPayload,
} from "@/features/peer-evaluation/peer-evaluation-api";

type EvaluationFormData = {
  projectId: string;
  ratedId: string;
  evaluationId?: string;
  score: number;
  remarks?: string;
};

export function usePeerEvaluation() {
  const [myEvaluations, setMyEvaluations] = useState<PeerEvaluationResponse[]>([]);
  const [courseEvaluations, setCourseEvaluations] = useState<CoursePeerEvaluationSummary | null>(
    null,
  );
  const [projectEvaluations, setProjectEvaluations] = useState<PeerEvaluationSummary | null>(null);
  const [memberEvaluations, setMemberEvaluations] = useState<MemberPeerEvaluationDetail | null>(
    null,
  );
  const [evaluationStatus, setEvaluationStatus] = useState<EvaluationStatusResponse | null>(null);
  const [evaluationConfig, setEvaluationConfigState] = useState<PeerEvaluationConfigResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMyEvaluations = useCallback(async (projectId?: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getMyEvaluations(projectId);
      setMyEvaluations(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load evaluations";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadCourseEvaluations = useCallback(async (courseId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getCourseEvaluations(courseId);
      setCourseEvaluations(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load course evaluations";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadMemberEvaluations = useCallback(async (projectId: string, memberId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getMemberEvaluations(projectId, memberId);
      setMemberEvaluations(data);
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load member evaluations";
      setError(message);
      setMemberEvaluations(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadProjectEvaluations = useCallback(async (projectId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getProjectEvaluations(projectId);
      setProjectEvaluations(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load project evaluations";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const checkEvaluationStatus = useCallback(async (courseId: string) => {
    try {
      setError(null);
      const data = await getEvaluationStatus(courseId);
      setEvaluationStatus(data);
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to check evaluation status";
      setError(message);
      return null;
    }
  }, []);

  const loadEvaluationConfig = useCallback(async (courseId: string) => {
    try {
      setError(null);
      const data = await getEvaluationConfig(courseId);
      setEvaluationConfigState(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load evaluation config";
      setError(message);
    }
  }, []);

  const submitNewEvaluation = useCallback(
    async (formData: EvaluationFormData): Promise<void> => {
      try {
        setIsLoading(true);
        setError(null);
        const payload = {
          project_id: formData.projectId,
          rated_id: formData.ratedId,
          score: formData.score,
          remarks: formData.remarks,
        };
        const result = formData.evaluationId
          ? await updateEvaluation(formData.evaluationId, {
              score: formData.score,
              remarks: formData.remarks ?? null,
            })
          : await submitEvaluation(payload);

        setMyEvaluations((prev) => {
          const index = prev.findIndex((e) => e.rated_id === formData.ratedId);
          if (index >= 0) {
            const updated = [...prev];
            updated[index] = result;
            return updated;
          }
          return [...prev, result];
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to submit evaluation";
        setError(message);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const updateEvaluationWindow = useCallback(
    async (courseId: string, payload: SetConfigPayload) => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await setEvaluationConfig(courseId, payload);
        setEvaluationConfigState(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to update evaluation window";
        setError(message);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    myEvaluations,
    courseEvaluations,
    projectEvaluations,
    memberEvaluations,
    evaluationStatus,
    evaluationConfig,
    isLoading,
    error,
    loadMyEvaluations,
    loadCourseEvaluations,
    loadProjectEvaluations,
    loadMemberEvaluations,
    checkEvaluationStatus,
    loadEvaluationConfig,
    submitNewEvaluation,
    updateEvaluationWindow,
    clearError,
  };
}
