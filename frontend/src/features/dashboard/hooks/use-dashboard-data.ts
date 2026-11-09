"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { scopeProjectsQueryOptions } from "@/features/projects/course-projects-api";
import { isUuid } from "@/features/projects/components/projects-api";
import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { readScope, subscribeScope } from "@/features/ingestion/scope-store";
import { getStudentProjects } from "@/features/student/student-project-api";
import type { DashboardProject, DashboardRole, GitMetrics, JiraRun, JiraSnapshot } from "@/features/dashboard/types";
import { useSession } from "@/lib/auth/session";

type DashboardState = {
  role: DashboardRole;
  fullName: string;
  mounted: boolean;
  projects: DashboardProject[];
  courseCount: number;
  selectedProjectId: string;
  sprintId: string;
  gitMetrics: GitMetrics | null;
  jiraSnapshot: JiraSnapshot | null;
  isLoading: boolean;
  loadError: string;
  setSelectedProjectId: (projectId: string) => void;
  setSprintId: (sprintId: string) => void;
};

// Checked structurally (ApiError.status) so tests can mock the client module freely.
function isNotFound(error: unknown): boolean {
  return (error as { status?: unknown } | null)?.status === 404;
}

export function useDashboardData(router: { replace: (path: string) => void }): DashboardState {
  const session = useSession();
  const queryClient = useQueryClient();
  const sessionRole = session?.user?.role;
  const role: DashboardRole = sessionRole === "student" ? "student" : "instructor";
  const fullName = session?.user?.fullName ?? "";
  const mounted = Boolean(session?.user) && sessionRole !== "admin";
  const [projects, setProjects] = useState<DashboardProject[]>([]);
  const [courseCount, setCourseCount] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [sprintId, setSprintId] = useState(() => readScope().selectedSprintId);
  const [gitMetrics, setGitMetrics] = useState<GitMetrics | null>(null);
  const [jiraSnapshot, setJiraSnapshot] = useState<JiraSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (sessionRole === "admin") router.replace("/admin");
  }, [router, sessionRole]);

  useEffect(() => {
    if (!mounted) return;
    if (role === "student") {
      void getStudentProjects().then((studentProjects) => {
        const projects = studentProjects.map((project) => ({ id: project.id, courseId: "", label: `${project.team_name} - ${project.project_name}` }));
        setProjects(projects);
        setSelectedProjectId(projects[0]?.id || "");
        setLoadError(projects.length ? "" : "You are not assigned to a project yet.");
        setIsLoading(false);
      }).catch((error) => {
        setLoadError(getErrorMessage(error, "Could not load your project."));
        setIsLoading(false);
      });
      return;
    }

    async function loadProjects() {
      try {
        const groups = await queryClient.fetchQuery(scopeProjectsQueryOptions(queryClient));
        const options = groups.flatMap(({ course, projects: courseProjects }) => courseProjects.map((project) => ({
          id: project.id,
          courseId: course.id,
          label: `${project.team_name} - ${project.project_name}`,
        })));
        const persisted = readScope();
        setCourseCount(groups.length);
        setProjects(options);
        setSelectedProjectId(options.find((project) => project.id === persisted.selectedProjectId)?.id || options[0]?.id || "");
        if (options.length === 0) {
          setLoadError("No project is available in your current course scope.");
          setIsLoading(false);
        }
      } catch (error) {
        setLoadError(getErrorMessage(error, "Unable to load project scope."));
        setIsLoading(false);
      }
    }
    loadProjects();
  }, [mounted, role, queryClient]);

  useEffect(() => {
    const updateScope = () => {
      const scope = readScope();
      if (scope.selectedProjectId) setSelectedProjectId(scope.selectedProjectId);
      setSprintId(scope.selectedSprintId);
    };
    return subscribeScope(updateScope);
  }, []);

  useEffect(() => {
    const selectedProject = projects.find((item) => item.id === selectedProjectId);
    if (!selectedProject || !isUuid(selectedProject.id) || !sprintId.trim()) return;
    const projectId = selectedProject.id;
    const courseId = selectedProject.courseId;
    const currentSprintId = sprintId.trim();
    if (role === "student") {
      setGitMetrics(null);
      setJiraSnapshot(null);
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    const { signal } = controller;

    async function loadJiraSnapshot(): Promise<JiraSnapshot | null> {
      const runs = await apiRequest<JiraRun[]>(`/jira-ingestion/runs/${projectId}/${encodeURIComponent(currentSprintId)}`, { signal });
      const completedRun = runs.find((run) => run.processing_status === "completed");
      if (!completedRun) return null;
      return apiRequest<JiraSnapshot>(`/jira-ingestion/runs/${projectId}/${encodeURIComponent(completedRun.sprint_id)}/${completedRun.run_id}/cleaned`, { signal });
    }

    async function loadDashboard() {
      setIsLoading(true);
      setLoadError("");
      setGitMetrics(null);
      setJiraSnapshot(null);
      const [gitResult, jiraResult] = await Promise.allSettled([
        apiRequest<GitMetrics>(`/repo-ingestion/runs/${projectId}/${encodeURIComponent(currentSprintId)}?course_id=${encodeURIComponent(courseId)}`, { signal }),
        loadJiraSnapshot(),
      ]);
      if (signal.aborted) return;
      const errors: string[] = [];
      if (gitResult.status === "fulfilled") setGitMetrics(gitResult.value);
      else if (!isNotFound(gitResult.reason)) errors.push(getErrorMessage(gitResult.reason, "Unable to load Git data."));
      if (jiraResult.status === "fulfilled") setJiraSnapshot(jiraResult.value);
      else if (!isNotFound(jiraResult.reason)) errors.push(getErrorMessage(jiraResult.reason, "Unable to load Jira data."));
      setLoadError(errors.join(" "));
      setIsLoading(false);
    }
    loadDashboard();
    return () => {
      controller.abort();
      setIsLoading(false);
    };
  }, [projects, role, selectedProjectId, sprintId]);

  return { role, fullName, mounted, projects, courseCount, selectedProjectId, sprintId, gitMetrics, jiraSnapshot, isLoading, loadError, setSelectedProjectId, setSprintId };
}
