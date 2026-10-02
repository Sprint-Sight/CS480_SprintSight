"use client";

import { useEffect, useMemo, useState } from "react";

import { apiRequest, isUuid } from "@/features/projects/components/projects-api";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import { getStudentProjects } from "@/features/student/student-project-api";
import type { DashboardProject, DashboardRole, GitMetrics, JiraRun, JiraSnapshot } from "@/features/dashboard/types";

type DashboardState = {
  role: DashboardRole;
  fullName: string;
  mounted: boolean;
  projects: DashboardProject[];
  selectedProjectId: string;
  sprintId: string;
  gitMetrics: GitMetrics | null;
  jiraSnapshot: JiraSnapshot | null;
  isLoading: boolean;
  loadError: string;
  setSelectedProjectId: (projectId: string) => void;
  setSprintId: (sprintId: string) => void;
};

export function useDashboardData(router: { replace: (path: string) => void }): DashboardState {
  const [role, setRole] = useState<DashboardRole>("instructor");
  const [fullName, setFullName] = useState("");
  const [mounted, setMounted] = useState(false);
  const [projects, setProjects] = useState<DashboardProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [sprintId, setSprintId] = useState(() => readIngestionState().selectedSprintId || "sprint-1");
  const [gitMetrics, setGitMetrics] = useState<GitMetrics | null>(null);
  const [jiraSnapshot, setJiraSnapshot] = useState<JiraSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as DashboardRole | null;
    const savedName = sessionStorage.getItem("sprintsight-auth-name");
    if (savedRole === "admin") {
      router.replace("/admin");
      return;
    }
    if (savedRole) setRole(savedRole);
    if (savedName) setFullName(savedName);
    setMounted(true);
  }, [router]);

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
        setLoadError(error instanceof Error ? error.message : "Could not load your project.");
        setIsLoading(false);
      });
      return;
    }

    async function loadProjects() {
      try {
        const courses = await apiRequest<Array<{ id: string }>>("/courses");
        const groups = await Promise.all(courses.map(async (course) => ({
          courseId: course.id,
          projects: await apiRequest<Array<{ id: string; team_name: string; project_name: string }>>(`/courses/${course.id}/projects`),
        })));
        const options = groups.flatMap(({ courseId, projects: courseProjects }) => courseProjects.map((project) => ({
          id: project.id,
          courseId,
          label: `${project.team_name} - ${project.project_name}`,
        })));
        const persisted = readIngestionState();
        setProjects(options);
        setSelectedProjectId(options.find((project) => project.id === persisted.selectedProjectId)?.id || options[0]?.id || "");
        if (options.length === 0) {
          setLoadError("No project is available in your current course scope.");
          setIsLoading(false);
        }
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Unable to load project scope.");
        setIsLoading(false);
      }
    }
    loadProjects();
  }, [mounted, role]);

  useEffect(() => {
    const updateScope = () => {
      const state = readIngestionState();
      if (state.selectedProjectId) setSelectedProjectId(state.selectedProjectId);
      setSprintId(state.selectedSprintId || "sprint-1");
    };
    window.addEventListener("sprintsight-ingestion-updated", updateScope);
    return () => window.removeEventListener("sprintsight-ingestion-updated", updateScope);
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

    async function loadDashboard() {
      setIsLoading(true);
      setLoadError("");
      setGitMetrics(null);
      setJiraSnapshot(null);
      try {
        const git = await apiRequest<GitMetrics>(`/repo-ingestion/runs/${projectId}/${encodeURIComponent(currentSprintId)}?course_id=${encodeURIComponent(courseId)}`);
        setGitMetrics(git);
        const runs = await apiRequest<JiraRun[]>(`/jira-ingestion/runs/${projectId}/${encodeURIComponent(currentSprintId)}`);
        const completedRun = runs.find((run) => run.processing_status === "completed");
        if (completedRun) {
          const snapshot = await apiRequest<JiraSnapshot>(`/jira-ingestion/runs/${projectId}/${encodeURIComponent(completedRun.sprint_id)}/${completedRun.run_id}/cleaned`);
          setJiraSnapshot(snapshot);
        }
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Unable to load ingested project data.");
      } finally {
        setIsLoading(false);
      }
    }
    loadDashboard();
  }, [projects, role, selectedProjectId, sprintId]);

  return { role, fullName, mounted, projects, selectedProjectId, sprintId, gitMetrics, jiraSnapshot, isLoading, loadError, setSelectedProjectId, setSprintId };
}
