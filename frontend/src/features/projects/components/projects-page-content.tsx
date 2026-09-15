"use client";

import { BookOpen, Plus, Search, Settings, SlidersHorizontal, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CourseManagementModal } from "@/features/projects/components/course-management-modal";
import { ProjectCard } from "@/features/projects/components/project-card";
import { ProjectModal } from "@/features/projects/components/project-modal";
import { RosterModal } from "@/features/projects/components/roster-modal";
import { apiRequest, getAuthToken, getDefaultJiraEmail, isUuid, toProjectPayload, type ProjectFormValues } from "@/features/projects/components/projects-api";
import { PROJECTS } from "@/features/projects/data";
import type { Course, Project, ProjectStatus } from "@/features/projects/types";

const statusOptions: Array<"All statuses" | ProjectStatus> = ["All statuses", "Active", "At Risk", "Completed"];
const sprintOptions = [
  "All sprints",
  ...Array.from(new Set(PROJECTS.flatMap((project) => project.sprints.map((sprint) => sprint.name)))),
];
const moduleOptions = ["All modules", ...Array.from(new Set(PROJECTS.map((project) => project.module)))];
const sortOptions = [
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
  { value: "score-desc", label: "Score (Highest first)" },
  { value: "score-asc", label: "Score (Lowest first)" },
  { value: "completion-desc", label: "Completion (Highest first)" },
  { value: "completion-asc", label: "Completion (Lowest first)" },
  { value: "status-priority", label: "Status (At Risk first)" },
] as const;

type SortValue = (typeof sortOptions)[number]["value"];

type ProjectFilters = {
  teamName: string;
  status: "All statuses" | ProjectStatus;
  sprint: string;
  module: string;
  minScore: string;
  maxScore: string;
  minCompletion: string;
  maxCompletion: string;
  sortBy: SortValue;
};

const DEFAULT_FILTERS: ProjectFilters = {
  teamName: "",
  status: "All statuses",
  sprint: "All sprints",
  module: "All modules",
  minScore: "",
  maxScore: "",
  minCompletion: "",
  maxCompletion: "",
  sortBy: "name-asc",
};

export default function ProjectsPageContent() {
  const [searchTerm, setSearchTerm] = useState("");
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);
  const [draftFilters, setDraftFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);

  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);

  const [isCourseModalOpen, setIsCourseModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [isRosterModalOpen, setIsRosterModalOpen] = useState(false);
  const [projectForNewMember, setProjectForNewMember] = useState<string | null>(null);

  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const [courseStudents, setCourseStudents] = useState<Array<{ id: string; email: string; full_name: string }>>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  const [projectForm, setProjectForm] = useState<ProjectFormValues>({
    project_name: "",
    team_name: "",
    description: "",
    github_repo_url: "",
    local_repo_path: "",
    jira_email: "",
    jira_domain: "",
    jira_project_key: "",
    jira_api_token: "",
  });

  const [courseForm, setCourseForm] = useState({
    code: "",
    name: "",
    section: "",
    year: new Date().getFullYear(),
    term: "Fall",
  });

  const [studentForm, setStudentForm] = useState({ email: "", full_name: "", password: "" });

  async function reloadCourses() {
    const token = getAuthToken();
    if (!token) {
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      return;
    }

    try {
      const courseList = await apiRequest<Course[]>("/courses");
      const normalizedCourses = courseList.map((course) => ({
        id: String(course.id),
        code: course.code,
        name: course.name,
        section: course.section,
        year: course.year,
        term: course.term,
      }));

      setCourses(normalizedCourses);
      if (normalizedCourses.length === 0) {
        setSelectedCourseId("");
        return;
      }

      setSelectedCourseId((current) => {
        if (current && normalizedCourses.some((course) => course.id === current)) {
          return current;
        }
        return normalizedCourses[0].id;
      });
    } catch (error) {
      console.error("Failed to load courses:", error);
    }
  }

  async function loadCourseStudents() {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      setCourseStudents([]);
      return;
    }

    try {
      const students = await apiRequest<Array<{ id: string; email: string; full_name: string }>>(
        `/courses/${selectedCourseId}/students`
      );
      setCourseStudents(students);
    } catch (error) {
      console.error("Failed to load course students:", error);
      setCourseStudents([]);
    }
  }

  async function loadProjects() {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      setProjects([]);
      return;
    }

    try {
      const projectList = await apiRequest<Array<{
        id: string;
        project_name: string;
        team_name: string;
        description: string | null;
        course_code: string;
        github_repo_url: string | null;
        local_repo_path: string | null;
        jira_email: string | null;
        jira_domain: string | null;
        jira_project_key: string | null;
        members: Array<{ id: string; email: string; full_name: string }>;
      }>>(`/courses/${selectedCourseId}/projects`);
      setProjects(projectList.map((project) => ({
        id: project.id,
        project_name: project.project_name,
        team_name: project.team_name,
        description: project.description || undefined,
        status: "Active",
        score: 0,
        completion: 0,
        module: project.course_code,
        sprints: [],
        members: project.members,
        github_repo_url: project.github_repo_url || undefined,
        local_repo_path: project.local_repo_path || undefined,
        jira_email: project.jira_email || undefined,
        jira_domain: project.jira_domain || undefined,
        jira_project_key: project.jira_project_key || undefined,
      })));
    } catch (error) {
      console.error("Failed to load projects:", error);
      setProjects([]);
    }
  }

  useEffect(() => {
    reloadCourses();
  }, []);

  useEffect(() => {
    loadCourseStudents();
    loadProjects();
  }, [selectedCourseId]);

  const appliedFilterCount = useMemo(() => {
    let count = 0;
    if (appliedFilters.teamName.trim()) count += 1;
    if (appliedFilters.status !== "All statuses") count += 1;
    if (appliedFilters.sprint !== "All sprints") count += 1;
    if (appliedFilters.module !== "All modules") count += 1;
    if (appliedFilters.minScore !== "" || appliedFilters.maxScore !== "") count += 1;
    if (appliedFilters.minCompletion !== "" || appliedFilters.maxCompletion !== "") count += 1;
    if (appliedFilters.sortBy !== "name-asc") count += 1;
    return count;
  }, [appliedFilters]);

  function handleOpenCreateCourse() {
    setEditingCourse(null);
    setCourseForm({ code: "", name: "", section: "", year: new Date().getFullYear(), term: "Fall" });
    setIsCourseModalOpen(true);
  }

  function handleOpenEditCourse() {
    const selectedCourse = courses.find((course) => course.id === selectedCourseId) ?? null;
    setEditingCourse(selectedCourse);
    setCourseForm(
      selectedCourse
        ? { code: selectedCourse.code, name: selectedCourse.name, section: selectedCourse.section, year: selectedCourse.year, term: selectedCourse.term }
        : { code: "", name: "", section: "", year: new Date().getFullYear(), term: "Fall" }
    );
    setIsCourseModalOpen(true);
  }

  function handleOpenCreateProject() {
    setEditingProject(null);
    setProjectForm({ project_name: "", team_name: "", description: "", github_repo_url: "", local_repo_path: "", jira_email: getDefaultJiraEmail(), jira_domain: "", jira_project_key: "", jira_api_token: "" });
    setIsProjectModalOpen(true);
  }

  function handleOpenEditProject(project: Project, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    setEditingProject(project);
    setProjectForm({
      project_name: project.project_name,
      team_name: project.team_name,
      description: project.description || "",
      github_repo_url: project.github_repo_url || "",
      local_repo_path: project.local_repo_path || "",
      jira_email: project.jira_email || getDefaultJiraEmail(),
      jira_domain: project.jira_domain || "",
      jira_project_key: project.jira_project_key || "",
      jira_api_token: "",
    });
    setIsProjectModalOpen(true);
  }

  async function handleDeleteProject(projectId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!confirm("Are you sure you want to delete this project?")) return;

    try {
      if (!isUuid(projectId)) {
        throw new Error("This project is not backed by a real backend record.");
      }
      await apiRequest(`/projects/${projectId}`, { method: "DELETE" });
      await loadProjects();
      window.alert("Project deleted.");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to delete project.");
    }
  }

  async function handleSaveProject() {
    try {
      const projectName = projectForm.project_name.trim();
      const teamName = projectForm.team_name.trim();
      const repositoryUrl = projectForm.github_repo_url.trim();
      const jiraEmail = projectForm.jira_email.trim();
      const jiraDomain = projectForm.jira_domain.trim();
      const jiraProjectKey = projectForm.jira_project_key.trim();
      const jiraApiToken = projectForm.jira_api_token.trim();

      if (!projectName || !teamName) {
        throw new Error("Project name and team name are required.");
      }

      // if (repositoryUrl && !/^https:\/\/(github\.com|gitlab\.com)\/[\w.-]+\/[\w.-]+(?:\/)?$/i.test(repositoryUrl)) {
      //   throw new Error("Repository URL must be an HTTPS GitHub or GitLab repository URL.");
      // }

      if (editingProject && !isUuid(editingProject.id)) {
        throw new Error("This project is not backed by a real backend record and cannot be updated.");
      }

      if (!selectedCourseId || !isUuid(selectedCourseId)) {
        throw new Error("Load or select a valid course before creating a project.");
      }

      const hasJiraConfiguration = Boolean(jiraDomain || jiraProjectKey || jiraApiToken);
      if (hasJiraConfiguration && (!jiraEmail || !jiraDomain || !jiraProjectKey || !jiraApiToken)) {
        throw new Error("Enter Jira email, domain, project key, and API token together.");
      }

      const projectPayload = toProjectPayload(projectForm);

      if (editingProject) {
        const updatePayload = {
          project_name: projectName,
          team_name: teamName,
          description: projectForm.description.trim() || undefined,
          github_repo_url: repositoryUrl || undefined,
          local_repo_path: projectForm.local_repo_path.trim() || undefined,
          ...(hasJiraConfiguration
            ? { jira_email: jiraEmail, jira_domain: jiraDomain, jira_project_key: jiraProjectKey, jira_api_token: jiraApiToken }
            : {}),
        };
        await apiRequest(`/projects/${editingProject.id}`, {
          method: "PATCH",
          body: JSON.stringify(updatePayload),
        });
        await loadProjects();
        window.alert("Project updated.");
      } else {
        await apiRequest(`/courses/${selectedCourseId}/projects`, {
          method: "POST",
          body: JSON.stringify(projectPayload),
        });
        await loadProjects();
        window.alert("Project created.");
      }
      setIsProjectModalOpen(false);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to save project.");
    }
  }

  async function handleCreateOrUpdateCourse() {
    try {
      const payload = {
        code: courseForm.code,
        name: courseForm.name,
        section: courseForm.section,
        year: courseForm.year,
        term: courseForm.term,
      };

      if (editingCourse && isUuid(editingCourse.id)) {
        await apiRequest(`/courses/${editingCourse.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        window.alert("Course updated.");
      } else {
        const createdCourse = await apiRequest<Course>("/courses", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        setCourses((previous) => [...previous, { id: String(createdCourse.id), code: createdCourse.code, name: createdCourse.name, section: createdCourse.section, year: createdCourse.year, term: createdCourse.term }]);
        setSelectedCourseId(String(createdCourse.id));
        window.alert("Course created.");
      }

      setIsCourseModalOpen(false);
      setEditingCourse(null);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to save course.");
    }
  }

  async function handleDeleteCourse(courseId: string = selectedCourseId) {
    if (!courseId || !isUuid(courseId)) {
      window.alert("Please select a valid course before deleting it.");
      return;
    }

    if (!confirm("Delete this course and all associated projects?")) return;

    try {
      await apiRequest(`/courses/${courseId}`, { method: "DELETE" });
      window.alert("Course deleted.");
      if (selectedCourseId === courseId) {
        setSelectedCourseId("");
      }
      await reloadCourses();
      setIsCourseModalOpen(false);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to delete course.");
    }
  }

  async function handleEnrollStudent() {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      window.alert("Please select a valid course before enrolling students.");
      return;
    }

    const trimmedEmail = studentForm.email.trim().toLowerCase();
    const trimmedName = studentForm.full_name.trim();
    const password = studentForm.password;

    if (!trimmedEmail || !trimmedName || !password) {
      window.alert("Student name, email, and password are required.");
      return;
    }
    if (password.length < 8) {
      window.alert("The student password must be at least 8 characters.");
      return;
    }
    if (courseStudents.some((student) => student.email.trim().toLowerCase() === trimmedEmail)) {
      window.alert("This student is already enrolled in the selected course. Their existing password was not changed.");
      return;
    }

    try {
      const student = await apiRequest<{ id: string; email: string; full_name: string; must_change_password?: boolean }>(`/courses/${selectedCourseId}/students`, {
        method: "POST",
        body: JSON.stringify({ email: trimmedEmail, full_name: trimmedName, password }),
      });

      if (projectForNewMember) {
        await apiRequest(`/projects/${projectForNewMember}/members/${student.id}`, { method: "POST" });
        await loadProjects();
        window.alert(`Student ${student.full_name} created and added to the project. They can log in with ${student.email} and the password entered here, then change it after first login.`);
      } else {
        window.alert(`Student ${student.full_name} created and enrolled. They can log in with ${student.email} and the password entered here, then change it after first login.`);
      }

      setStudentForm({ email: "", full_name: "", password: "" });
      setProjectForNewMember(null);
      await loadCourseStudents();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to enroll student.");
    }
  }

  async function handleUnenrollStudent(userId: string) {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      window.alert("Please select a valid course before unenrolling a student.");
      return;
    }

    try {
      await apiRequest(`/courses/${selectedCourseId}/students/${userId}`, { method: "DELETE" });
      setCourseStudents((previous) => previous.filter((student) => student.id !== userId));
      window.alert("Student unenrolled.");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to unenroll student.");
    }
  }

  async function handleAddProjectMember(projectId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      window.alert("Please select a valid course before adding a project member.");
      return;
    }
    setProjectForNewMember(projectId);
    setStudentForm({ email: "", full_name: "", password: "" });
    setIsRosterModalOpen(true);
  }

  async function handleRemoveProjectMember(projectId: string, userId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();

    try {
      await apiRequest(`/projects/${projectId}/members/${userId}`, { method: "DELETE" });
      window.alert("Project member removed.");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to remove project member.");
    }
  }

  function updateDraftFilter<K extends keyof ProjectFilters>(key: K, value: ProjectFilters[K]) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  }

  function parseRangeValue(value: string) {
    if (value.trim() === "") return null;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  const filteredProjects = useMemo(() => {
    const minScore = parseRangeValue(appliedFilters.minScore);
    const maxScore = parseRangeValue(appliedFilters.maxScore);
    const minCompletion = parseRangeValue(appliedFilters.minCompletion);
    const maxCompletion = parseRangeValue(appliedFilters.maxCompletion);

    const matches = projects.filter((project) => {
      const normalizedSearch = searchTerm.trim().toLowerCase();
      const normalizedTeamName = appliedFilters.teamName.trim().toLowerCase();
      const searchBlob = [project.project_name, project.team_name, project.module, ...project.sprints.map((sprint) => sprint.name)]
        .join(" ")
        .toLowerCase();

      const matchesSearch = normalizedSearch.length === 0 || searchBlob.includes(normalizedSearch);
      const matchesTeamName = normalizedTeamName.length === 0 || project.team_name.toLowerCase().includes(normalizedTeamName);
      const matchesStatus = appliedFilters.status === "All statuses" || project.status === appliedFilters.status;
      const matchesSprint = appliedFilters.sprint === "All sprints" || project.sprints.some((sprint) => sprint.name === appliedFilters.sprint);
      const matchesModule = appliedFilters.module === "All modules" || project.module === appliedFilters.module;
      const matchesMinScore = minScore === null || project.score >= minScore;
      const matchesMaxScore = maxScore === null || project.score <= maxScore;
      const matchesMinCompletion = minCompletion === null || project.completion >= minCompletion;
      const matchesMaxCompletion = maxCompletion === null || project.completion <= maxCompletion;

      return (
        matchesSearch &&
        matchesTeamName &&
        matchesStatus &&
        matchesSprint &&
        matchesModule &&
        matchesMinScore &&
        matchesMaxScore &&
        matchesMinCompletion &&
        matchesMaxCompletion
      );
    });

    const sorted = [...matches];
    sorted.sort((left, right) => {
      if (appliedFilters.sortBy === "name-desc") return right.project_name.localeCompare(left.project_name);
      if (appliedFilters.sortBy === "score-desc") return right.score - left.score;
      if (appliedFilters.sortBy === "score-asc") return left.score - right.score;
      if (appliedFilters.sortBy === "completion-desc") return right.completion - left.completion;
      if (appliedFilters.sortBy === "completion-asc") return left.completion - right.completion;
      if (appliedFilters.sortBy === "status-priority") {
        const rank: Record<ProjectStatus, number> = { "At Risk": 0, Active: 1, Completed: 2 };
        const statusDiff = rank[left.status] - rank[right.status];
        if (statusDiff !== 0) return statusDiff;
        return right.score - left.score;
      }
      return left.project_name.localeCompare(right.project_name);
    });

    return sorted;
  }, [searchTerm, appliedFilters, projects]);

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Projects</h1>
          <p className="mt-1 text-base text-slate-500">Manage course sections, roster, and team project metrics</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm ring-1 ring-slate-100">
            <button type="button" onClick={handleOpenCreateCourse} title="Create a new course" className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700 transition hover:bg-blue-100">
              <Plus className="h-4 w-4" />
            </button>

            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5">
              <BookOpen className="h-4 w-4 text-slate-400" />
              <select value={selectedCourseId} onChange={(event) => setSelectedCourseId(event.target.value)} className="h-9 min-w-[220px] appearance-none bg-transparent pr-5 text-sm font-semibold text-slate-700 outline-none">
                {courses.length === 0 ? (
                  <option value="">No courses available</option>
                ) : (
                  courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.code} · {course.section} · {course.term} {course.year}
                    </option>
                  ))
                )}
              </select>
            </div>

            <button type="button" onClick={handleOpenEditCourse} title="Edit selected course" className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-700">
              <Settings className="h-4 w-4" />
            </button>
          </div>

          <button type="button" onClick={() => setIsRosterModalOpen(true)} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
            <Users className="h-4 w-4 text-slate-500" />
            Roster
          </button>

          <button type="button" onClick={handleOpenCreateProject} disabled={!selectedCourseId} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50">
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>
      </div>

      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input type="text" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="Search by project or team name..." className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-11 pr-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2" />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_220px_220px]">
          <div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm text-slate-500 md:flex">
            <SlidersHorizontal className="h-4 w-4" />
            {appliedFilterCount > 0 ? `${appliedFilterCount} filter(s) applied` : "No filters applied"}
          </div>

          <button type="button" onClick={() => { setDraftFilters(appliedFilters); setIsFilterModalOpen(true); }} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none ring-blue-100 transition hover:bg-slate-50 focus:border-blue-300 focus:ring-2">
            <SlidersHorizontal className="h-4 w-4" />
            Filter and Sort
          </button>

          <button type="button" onClick={() => { setAppliedFilters(DEFAULT_FILTERS); setDraftFilters(DEFAULT_FILTERS); }} className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none ring-blue-100 transition hover:bg-slate-50 focus:border-blue-300 focus:ring-2">
            Reset filters
          </button>
        </div>
      </div>

      {filteredProjects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="text-lg font-semibold text-slate-900">No projects matched your filters</h2>
          <p className="mt-1 text-sm text-slate-500">Try broadening your search, sprint, or status selection.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {filteredProjects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onEdit={handleOpenEditProject}
                onDelete={handleDeleteProject}
                onAddMember={handleAddProjectMember}
                onRemoveMember={handleRemoveProjectMember}
              />
          ))}
        </div>
      )}

      <ProjectModal isOpen={isProjectModalOpen} editingProject={editingProject} projectForm={projectForm} onClose={() => setIsProjectModalOpen(false)} onSave={handleSaveProject} setProjectForm={setProjectForm} />

      <CourseManagementModal
        isOpen={isCourseModalOpen}
        courses={courses}
        editingCourse={editingCourse}
        courseForm={courseForm}
        userName={sessionStorage.getItem("sprintsight-auth-name") || "Instructor"}
        onClose={() => setIsCourseModalOpen(false)}
        onSave={handleCreateOrUpdateCourse}
        onDelete={handleDeleteCourse}
        setCourseForm={setCourseForm}
        setEditingCourse={setEditingCourse}
      />

      <RosterModal
        isOpen={isRosterModalOpen}
        courseStudents={courseStudents}
        studentForm={studentForm}
        onClose={() => {
          setIsRosterModalOpen(false);
          setProjectForNewMember(null);
        }}
        onEnroll={handleEnrollStudent}
        onUnenroll={handleUnenrollStudent}
        setStudentForm={setStudentForm}
      />

      {isFilterModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Filter and sort projects</h2>
                <p className="text-sm text-slate-500">Adjust criteria, then apply to refresh the project list.</p>
              </div>
              <button type="button" onClick={() => setIsFilterModalOpen(false)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700">
                ×
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 px-5 py-4 md:grid-cols-2">
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Team name</span>
                <input type="text" value={draftFilters.teamName} onChange={(event) => updateDraftFilter("teamName", event.target.value)} placeholder="e.g. Team Alpha" className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-700 outline-none focus:border-blue-300" />
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Status</span>
                <select value={draftFilters.status} onChange={(event) => updateDraftFilter("status", event.target.value as "All statuses" | ProjectStatus)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300">
                  {statusOptions.map((statusOption) => (
                    <option key={statusOption} value={statusOption}>{statusOption}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Module</span>
                <select value={draftFilters.module} onChange={(event) => updateDraftFilter("module", event.target.value)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300">
                  {moduleOptions.map((moduleOption) => (
                    <option key={moduleOption} value={moduleOption}>{moduleOption}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Sprint</span>
                <select value={draftFilters.sprint} onChange={(event) => updateDraftFilter("sprint", event.target.value)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300">
                  {sprintOptions.map((sprintOption) => (
                    <option key={sprintOption} value={sprintOption}>{sprintOption}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5 md:col-span-2">
                <span className="text-sm font-medium text-slate-700">Sort by</span>
                <select value={draftFilters.sortBy} onChange={(event) => updateDraftFilter("sortBy", event.target.value as SortValue)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300">
                  {sortOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
              <button type="button" onClick={() => setDraftFilters(DEFAULT_FILTERS)} className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50">Clear form</button>
              <button type="button" onClick={() => { setAppliedFilters(draftFilters); setIsFilterModalOpen(false); }} className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800">Apply filters</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}