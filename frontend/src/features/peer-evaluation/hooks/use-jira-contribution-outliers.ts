"use client";

import { useCallback, useState } from "react";
import {
  getJiraContributionOutliers,
  getStudentJiraContribution,
  type JiraContributionOutlierReport,
  type JiraContributionStudent,
} from "@/features/peer-evaluation/peer-evaluation-api";

export function useJiraContributionOutliers() {
  const [report, setReport] = useState<JiraContributionOutlierReport | null>(null);
  const [studentDetail, setStudentDetail] = useState<JiraContributionStudent | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [onlyOutliers, setOnlyOutliers] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReport = useCallback(async (courseId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      setSelectedStudentId(null);
      setStudentDetail(null);
      setReport(await getJiraContributionOutliers(courseId, onlyOutliers));
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : "Failed to load Jira contribution report");
    } finally {
      setIsLoading(false);
    }
  }, [onlyOutliers]);

  const selectStudent = useCallback(async (courseId: string, studentId: string) => {
    setSelectedStudentId(studentId);
    setStudentDetail(null);
    try {
      setIsDetailLoading(true);
      setError(null);
      setStudentDetail(await getStudentJiraContribution(courseId, studentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load student Jira contribution");
    } finally {
      setIsDetailLoading(false);
    }
  }, []);

  const closeStudentDetail = useCallback(() => {
    setSelectedStudentId(null);
    setStudentDetail(null);
    setError(null);
  }, []);

  return {
    report,
    studentDetail,
    selectedStudentId,
    onlyOutliers,
    setOnlyOutliers,
    isLoading,
    isDetailLoading,
    error,
    loadReport,
    selectStudent,
    closeStudentDetail,
  };
}
