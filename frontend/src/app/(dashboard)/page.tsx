"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  GitCommit,
  ListChecks,
  Loader2,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useRouter } from "next/navigation";
import { apiRequest, isUuid } from "@/features/projects/components/projects-api";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

type Role = "student" | "instructor" | "admin";

type ProjectOption = { id: string; courseId: string; label: string };
type GitMetrics = {
  sprint_id: string;
  commit_frequency: number;
  code_churn: number;
  assigned_story_points: number | null;
  completion_percent: number | null;
  commits: Array<{ sha: string; author: string; message: string; timestamp: string; lines_added: number; lines_deleted: number }>;
};
type JiraRun = { run_id: string; sprint_id: string; processing_status: string; captured_at: string; project_id: string };
type JiraSnapshot = { tickets: Array<{ ticket_id: string; summary: string; status: string | null; assignee: string | null; story_points: number | null }> };

export default function DashboardPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("instructor");
  const [fullName, setFullName] = useState<string>("");
  const [mounted, setMounted] = useState(false);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [sprintId, setSprintId] = useState("sprint-1");
  const [gitMetrics, setGitMetrics] = useState<GitMetrics | null>(null);
  const [jiraSnapshot, setJiraSnapshot] = useState<JiraSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as Role | null;
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
      const persisted = readIngestionState();
      const firstGitRun = Object.values(persisted.gitBySprint)[0];
      const firstJiraRun = Object.values(persisted.jiraBySprint)[0];
      const projectId = persisted.selectedProjectId || firstGitRun?.project_id || firstJiraRun?.project_id;
      const courseId = persisted.selectedCourseId || firstGitRun?.course_id || firstJiraRun?.course_id;
      if (!projectId || !courseId) {
        setLoadError("No synced project data is available for your account yet.");
        setIsLoading(false);
        return;
      }
      setProjects([{ id: projectId, courseId, label: "My project" }]);
      setSelectedProjectId(projectId);
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
    };
    window.addEventListener("sprintsight-ingestion-updated", updateScope);
    return () => window.removeEventListener("sprintsight-ingestion-updated", updateScope);
  }, []);

  useEffect(() => {
    const selectedProject = projects.find((item) => item.id === selectedProjectId);
    if (!selectedProject || !isUuid(selectedProject.id) || !sprintId.trim()) return;
    const project = selectedProject;
    if (role === "student") {
      const ingestion = getProjectIngestion(project.id, sprintId.trim());
      setGitMetrics(ingestion.git || null);
      setJiraSnapshot(ingestion.jira || null);
      setLoadError(ingestion.git || ingestion.jira ? "" : "No synced ingestion data is available for this sprint.");
      setIsLoading(false);
      return;
    }
    async function loadDashboard() {
      setIsLoading(true);
      setLoadError("");
      setGitMetrics(null);
      setJiraSnapshot(null);
      try {
        const git = await apiRequest<GitMetrics>(`/repo-ingestion/runs/${project.id}/${encodeURIComponent(sprintId.trim())}?course_id=${encodeURIComponent(project.courseId)}`);
        setGitMetrics(git);
        const runs = await apiRequest<JiraRun[]>(`/jira-ingestion/runs/${project.id}/${encodeURIComponent(sprintId.trim())}`);
        const completedRun = runs.find((run) => run.processing_status === "completed");
        if (completedRun) {
          const snapshot = await apiRequest<JiraSnapshot>(`/jira-ingestion/runs/${project.id}/${encodeURIComponent(completedRun.sprint_id)}/${completedRun.run_id}/cleaned`);
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

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const completedTickets = jiraSnapshot?.tickets.filter((ticket) => /done|closed|resolved/i.test(ticket.status || "")).length || 0;
  const chartData = (gitMetrics?.commits || []).reduce<Array<{ name: string; commits: number }>>((days, commit) => {
    const name = new Date(commit.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const day = days.find((item) => item.name === name);
    if (day) day.commits += 1;
    else days.push({ name, commits: 1 });
    return days;
  }, []);

  if (!mounted) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
        <h1 className="text-2xl font-bold text-slate-900">{role === "student" ? "My Dashboard" : "Dashboard"}</h1>
        <p className="text-slate-500 mt-1">
          {fullName || (role === "student" ? "Student" : "Instructor")} - {selectedProject?.label || "Loading project scope"}
        </p>
        </div>
        <label className="space-y-1 text-sm text-slate-600">
          <span className="block text-xs font-semibold uppercase tracking-wider">Sprint</span>
          <input value={sprintId} onChange={(event) => setSprintId(event.target.value)} onBlur={() => setSprintId((value) => value.trim() || "sprint-1")} className="h-10 rounded-lg border border-slate-200 bg-white px-3" />
        </label>
      </div>
      {isLoading && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading ingested project data...</div>}
      {loadError && <p className="text-sm text-rose-600">{loadError}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { title: "Commits", value: gitMetrics?.commits.length ?? "-", sub: gitMetrics ? `${gitMetrics.commit_frequency.toFixed(1)} commits/day` : "No Git run loaded", icon: GitCommit, color: "text-blue-500" },
          { title: "Code Churn", value: gitMetrics?.code_churn ?? "-", sub: "Lines changed in this sprint", icon: Activity, color: "text-indigo-500" },
          { title: "Completion", value: gitMetrics?.completion_percent == null ? "-" : `${Math.round(gitMetrics.completion_percent)}%`, sub: gitMetrics?.assigned_story_points == null ? "Story points unavailable" : `${gitMetrics.assigned_story_points} assigned story points`, icon: ListChecks, color: "text-emerald-500" },
          { title: "Jira Tickets", value: jiraSnapshot?.tickets.length ?? "-", sub: jiraSnapshot ? `${completedTickets} completed` : "No processed Jira run", icon: AlertTriangle, color: "text-rose-500" },
        ].map((metric, idx) => (
          <div key={idx} className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">{metric.title}</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">{metric.value}</h3>
              </div>
              <div className={`p-2 bg-slate-50 rounded-lg ${metric.color}`}>
                <metric.icon className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-slate-500">{metric.sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Commit Activity</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                <Line
                  type="monotone"
                  dataKey="commits"
                  stroke="#1e3a8a"
                  strokeWidth={3}
                  dot={{ r: 4, fill: "#1e3a8a", strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: "#3b82f6", strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-4">Jira Work</h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3">
            {(jiraSnapshot?.tickets || []).slice(0, 6).map((ticket) => (
              <div key={ticket.ticket_id} className="p-3 rounded-lg border border-slate-100 bg-slate-50 flex items-start gap-3">
                <div className="mt-1.5 w-2 h-2 rounded-full flex-shrink-0 bg-blue-500" />
                <div>
                  <p className="text-xs font-semibold text-slate-800">{ticket.ticket_id} - {ticket.summary}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{ticket.status || "Unknown status"}{ticket.assignee ? ` - ${ticket.assignee}` : ""}</p>
                </div>
              </div>
            ))}
            {!isLoading && !jiraSnapshot?.tickets.length && <p className="text-sm text-slate-500">No processed Jira tickets are available for this sprint.</p>}
          </div>
        </div>
      </div>

      <section className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Recent Git Evidence</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead><tr className="border-b border-slate-200"><th className="pb-3 text-sm font-semibold text-slate-500">Commit</th><th className="pb-3 text-sm font-semibold text-slate-500">Author</th><th className="pb-3 text-sm font-semibold text-slate-500">Message</th><th className="pb-3 text-sm font-semibold text-slate-500">Changed</th></tr></thead>
            <tbody>{(gitMetrics?.commits || []).slice(0, 8).map((commit) => <tr key={commit.sha} className="border-b border-slate-100 last:border-0"><td className="py-3 text-sm font-mono text-slate-700">{commit.sha.slice(0, 8)}</td><td className="py-3 text-sm text-slate-700">{commit.author}</td><td className="py-3 text-sm text-slate-600">{commit.message}</td><td className="py-3 text-sm text-slate-600">+{commit.lines_added} / -{commit.lines_deleted}</td></tr>)}</tbody>
          </table>
          {!isLoading && !gitMetrics?.commits.length && <p className="py-4 text-sm text-slate-500">No Git ingestion data is available for this sprint.</p>}
        </div>
      </section>
    </div>
  );
}