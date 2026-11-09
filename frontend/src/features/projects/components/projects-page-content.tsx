"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpen, Plus, Search, SlidersHorizontal, Users, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";

import { CourseManagementModal } from "@/features/projects/components/course-management-modal";
import { ProjectCard } from "@/features/projects/components/project-card";
import { ProjectFilterModal } from "@/features/projects/components/project-filter-modal";
import { ProjectMembersModal } from "@/features/projects/components/project-members-modal";
import { ProjectModal } from "@/features/projects/components/project-modal";
import { RosterModal, type StudentFormErrors } from "@/features/projects/components/roster-modal";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";
import { EmptyState } from "@/components/ui/empty-state";
import { getDefaultJiraEmail, isUuid, toProjectPayload, type ProjectFormValues } from "@/features/projects/components/projects-api";
import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { invalidateProjectCaches } from "@/features/projects/course-projects-api";
import type { Course, Project } from "@/features/projects/types";
import { useProjectFilters, type ProjectFilters } from "@/features/projects/hooks/use-project-filters";
import { CSVImportModal } from "@/features/projects/components/csv-import-modal";
import { useStudentImport } from "@/features/projects/hooks/use-student-import";
import { useInstructorJiraCredentials } from "@/features/settings/hooks/use-instructor-jira-credentials";
import { useSession } from "@/lib/auth/session";

const sortOptions = [
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
] as const;

const DEFAULT_FILTERS: ProjectFilters = {
  teamName: "",
  module: "All modules",
  sortBy: "name-asc",
};

export default function ProjectsPageContent() {
  const [searchTerm, setSearchTerm] = useState("");
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);
  const [draftFilters, setDraftFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);

  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [isSavingProject, setIsSavingProject] = useState(false);
  const isSavingProjectRef = useRef(false);

  const [isCourseModalOpen, setIsCourseModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [isRosterModalOpen, setIsRosterModalOpen] = useState(false);
  const [projectForMemberSelection, setProjectForMemberSelection] = useState<Project | null>(null);
  const [selectedProjectMemberIds, setSelectedProjectMemberIds] = useState<string[]>([]);
  const [isAddingProjectMembers, setIsAddingProjectMembers] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<{ projectId: string; userId: string; fullName: string } | null>(null);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [courseToDelete, setCourseToDelete] = useState<string | null>(null);
  const [studentFormErrors, setStudentFormErrors] = useState<StudentFormErrors>({});

  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const { isLoading: isImporting, error: importError, parsedRows, validateAndPreview, submitImport, clearState: clearImportState } = useStudentImport();

  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const [courseStudents, setCourseStudents] = useState<Array<{ id: string; email: string; full_name: string; is_active: boolean }>>([]);
  const [allStudents, setAllStudents] = useState<Array<{ id: string; email: string; full_name: string; is_active: boolean }>>([]);
  const [studentSearchTerm, setStudentSearchTerm] = useState("");
  const [isLoadingStudents, setIsLoadingStudents] = useState(false);
  const [studentDirectoryError, setStudentDirectoryError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const session = useSession();
  const queryClient = useQueryClient();
  const canUseInstructorCredentials = Boolean(session?.user) && session?.user?.role !== "student";
  const jiraCredentials = useInstructorJiraCredentials(canUseInstructorCredentials);
  const moduleOptions = useMemo(() => ["All modules", ...Array.from(new Set(projects.map((project) => project.module).filter(Boolean)))], [projects]);

  const [projectForm, setProjectForm] = useState<ProjectFormValues>({
    project_name: "",
    team_name: "",
    description: "",
    github_repo_url: "",
    local_repo_path: "",
    jira_domain: "",
    jira_project_key: "",
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
    const token = getSessionToken();
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

  const loadCourseStudents = useCallback(async () => {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      setCourseStudents([]);
      return;
    }

    try {
      const students = await apiRequest<Array<{ id: string; email: string; full_name: string; is_active: boolean }>>(
        `/courses/${selectedCourseId}/students`
      );
      setCourseStudents(students);
    } catch (error) {
      console.error("Failed to load course students:", error);
      setCourseStudents([]);
    }
  }, [selectedCourseId]);

  const loadAllStudents = useCallback(async () => {
    setIsLoadingStudents(true);
    setStudentDirectoryError("");
    try {
      const students = await apiRequest<
        Array<{ id: string; email: string; full_name: string; is_active: boolean; role: string }>
      >("/users");
      setAllStudents(students.filter((student) => student.role === "student"));
    } catch (error) {
      const message = getErrorMessage(error, "Failed to load student accounts.");
      setStudentDirectoryError(message);
      console.error("Failed to load student directory:", error);
    } finally {
      setIsLoadingStudents(false);
    }
  }, []);

  const loadProjects = useCallback(async () => {
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
        module: project.course_code,
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
  }, [selectedCourseId]);

  useEffect(() => {
    reloadCourses();
  }, []);

  useEffect(() => {
    loadCourseStudents();
    loadProjects();
  }, [selectedCourseId, loadCourseStudents, loadProjects]);

  useEffect(() => {
    if (isRosterModalOpen) void loadAllStudents();
  }, [isRosterModalOpen, loadAllStudents]);

  const appliedFilterCount = useMemo(() => {
    let count = 0;
    if (appliedFilters.teamName.trim()) count += 1;
    if (appliedFilters.module !== "All modules") count += 1;
    if (appliedFilters.sortBy !== "name-asc") count += 1;
    return count;
  }, [appliedFilters]);

  function handleOpenCourseManagement() {
    setEditingCourse(null);
    setCourseForm({ code: "", name: "", section: "", year: new Date().getFullYear(), term: "Fall" });
    setIsCourseModalOpen(true);
  }

  function handleOpenCreateProject() {
    setEditingProject(null);
    setProjectForm({ project_name: "", team_name: "", description: "", github_repo_url: "", local_repo_path: "", jira_domain: "", jira_project_key: "" });
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
      jira_domain: project.jira_domain || "",
      jira_project_key: project.jira_project_key || "",
    });
    setIsProjectModalOpen(true);
  }

  function handleDeleteProject(projectId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const project = projects.find((candidate) => candidate.id === projectId);
    if (project) setProjectToDelete(project);
  }

  async function handleConfirmDeleteProject() {
    if (!projectToDelete) return;
    const projectId = projectToDelete.id;
    setProjectToDelete(null);

    try {
      if (!isUuid(projectId)) {
        throw new Error("This project is not backed by a real backend record.");
      }
      await apiRequest(`/projects/${projectId}`, { method: "DELETE" });
      await loadProjects();
      invalidateProjectCaches(queryClient);
      toast.success("Project deleted.");
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to delete project."));
    }
  }

  async function handleSaveProject() {
    // A ref (not state) so two clicks in the same tick cannot both start a save.
    if (isSavingProjectRef.current) return;
    isSavingProjectRef.current = true;
    setIsSavingProject(true);
    try {
      const projectName = projectForm.project_name.trim();
      const teamName = projectForm.team_name.trim();
      const repositoryUrl = projectForm.github_repo_url.trim();
      const jiraEmail = jiraCredentials.jiraEmail.trim();
      const jiraDomain = projectForm.jira_domain.trim();
      const jiraProjectKey = projectForm.jira_project_key.trim();

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

      const hasJiraConfiguration = Boolean(jiraDomain || jiraProjectKey);
      if (hasJiraConfiguration && (!jiraEmail || !jiraDomain || !jiraProjectKey)) {
        throw new Error("Enter the shared Jira account email and this group's Jira domain and project key.");
      }
      if (
        hasJiraConfiguration &&
        !jiraCredentials.hasSavedToken &&
        !jiraCredentials.jiraApiToken.trim()
      ) {
        throw new Error("Save a shared Jira API token in Settings before configuring Jira for this group.");
      }

      if (jiraCredentials.hasUnsavedChanges && !(await jiraCredentials.saveCredentials())) {
        throw new Error(jiraCredentials.error || "Unable to save the shared Jira credentials.");
      }

      const projectPayload = toProjectPayload(projectForm, jiraEmail || getDefaultJiraEmail());

      if (editingProject) {
        const updatePayload = {
          project_name: projectName,
          team_name: teamName,
          description: projectForm.description.trim() || undefined,
          github_repo_url: repositoryUrl || undefined,
          local_repo_path: projectForm.local_repo_path.trim() || undefined,
          ...(hasJiraConfiguration ? { jira_domain: jiraDomain, jira_project_key: jiraProjectKey } : {}),
        };
        await apiRequest(`/projects/${editingProject.id}`, {
          method: "PATCH",
          body: JSON.stringify(updatePayload),
        });
        await loadProjects();
        invalidateProjectCaches(queryClient);
        toast.success("Project updated.");
      } else {
        await apiRequest(`/courses/${selectedCourseId}/projects`, {
          method: "POST",
          body: JSON.stringify(projectPayload),
        });
        await loadProjects();
        invalidateProjectCaches(queryClient);
        toast.success("Project created.");
      }
      setIsProjectModalOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to save project."));
    } finally {
      isSavingProjectRef.current = false;
      setIsSavingProject(false);
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
        toast.success("Course updated.");
      } else {
        const createdCourse = await apiRequest<Course>("/courses", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        setCourses((previous) => [...previous, { id: String(createdCourse.id), code: createdCourse.code, name: createdCourse.name, section: createdCourse.section, year: createdCourse.year, term: createdCourse.term }]);
        setSelectedCourseId(String(createdCourse.id));
        toast.success("Course created.");
      }

      setIsCourseModalOpen(false);
      setEditingCourse(null);
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to save course."));
    }
  }

  function handleDeleteCourse(courseId: string = selectedCourseId) {
    if (!courseId || !isUuid(courseId)) {
      toast.error("Please select a valid course before deleting it.");
      return;
    }
    setCourseToDelete(courseId);
  }

  async function handleConfirmDeleteCourse() {
    const courseId = courseToDelete;
    setCourseToDelete(null);
    if (!courseId) return;

    try {
      await apiRequest(`/courses/${courseId}`, { method: "DELETE" });
      invalidateProjectCaches(queryClient);
      toast.success("Course deleted.");
      if (selectedCourseId === courseId) {
        setSelectedCourseId("");
      }
      await reloadCourses();
      setIsCourseModalOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to delete course."));
    }
  }

  async function handleCreateStudent() {
    const trimmedEmail = studentForm.email.trim().toLowerCase();
    const trimmedName = studentForm.full_name.trim();
    const fallbackPassword = studentForm.password;

    const errors: StudentFormErrors = {};
    if (!trimmedName) errors.name = "Full name is required.";
    if (!trimmedEmail) errors.email = "Email is required.";
    if (fallbackPassword && fallbackPassword.length < 8) {
      errors.password = "Use at least 8 characters.";
    }
    setStudentFormErrors(errors);
    if (Object.keys(errors).length > 0) return;

    try {
      const student = await apiRequest<{
        id: string;
        email: string;
        full_name: string;
        signup_email_sent: boolean;
      }>("/users", {
        method: "POST",
        body: JSON.stringify({
          email: trimmedEmail,
          full_name: trimmedName,
          ...(fallbackPassword ? { password: fallbackPassword } : {}),
        }),
      });

      if (student.signup_email_sent) {
        toast.success(
          `Student ${student.full_name} was created. A first-time password setup link was queued for delivery to ${student.email}.${
            fallbackPassword
              ? " They can also log in once with the fallback password you set."
              : ""
          } Enroll them in a course from the student directory below.`,
        );
      } else {
        toast.warning(
          `Student ${student.full_name} was created, but the setup email could not be queued. Check the backend SMTP configuration and logs.${
            fallbackPassword
              ? " They can still log in once with the fallback password you set."
              : " You can enroll them in a course from the student directory below."
          }`,
        );
      }

      setStudentForm({ email: "", full_name: "", password: "" });
      setStudentFormErrors({});
      await loadAllStudents();
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to create student."));
    }
  }

  async function handleEnrollExistingStudent(userId: string) {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      toast.error("Please select a valid course before enrolling students.");
      return;
    }
    try {
      const student = await apiRequest<{ full_name: string }>(
        `/courses/${selectedCourseId}/students/${userId}`,
        { method: "POST" },
      );
      await loadCourseStudents();
      toast.success(`${student.full_name} was enrolled in this course.`);
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to enroll student."));
    }
  }

  async function handleUnenrollStudent(userId: string) {
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      toast.error("Please select a valid course before unenrolling a student.");
      return;
    }

    try {
      await apiRequest(`/courses/${selectedCourseId}/students/${userId}`, { method: "DELETE" });
      setCourseStudents((previous) => previous.filter((student) => student.id !== userId));
      toast.success("Student unenrolled.");
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to unenroll student."));
    }
  }

  async function handleAddProjectMember(projectId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedCourseId || !isUuid(selectedCourseId)) {
      toast.error("Please select a valid course before adding a project member.");
      return;
    }
    const project = projects.find((candidate) => candidate.id === projectId);
    if (!project) return;
    await loadCourseStudents();
    setSelectedProjectMemberIds([]);
    setProjectForMemberSelection(project);
  }

  function handleToggleProjectMember(studentId: string) {
    setSelectedProjectMemberIds((selectedIds) =>
      selectedIds.includes(studentId)
        ? selectedIds.filter((selectedId) => selectedId !== studentId)
        : [...selectedIds, studentId],
    );
  }

  function handleRemoveProjectMember(projectId: string, userId: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const project = projects.find((candidate) => candidate.id === projectId);
    const member = project?.members.find((candidate) => candidate.id === userId);
    if (member) setMemberToRemove({ projectId, userId, fullName: member.full_name });
  }

  async function handleConfirmedRemoveProjectMember() {
    if (!memberToRemove) return;
    try {
      await apiRequest(`/projects/${memberToRemove.projectId}/members/${memberToRemove.userId}`, { method: "DELETE" });
      await loadProjects();
      invalidateProjectCaches(queryClient);
      toast.success("Project member removed.");
    } catch (error) {
      toast.error(getErrorMessage(error, "Failed to remove project member."));
    } finally {
      setMemberToRemove(null);
    }
  }

  async function handleConfirmAddProjectMember() {
    if (
      !projectForMemberSelection ||
      selectedProjectMemberIds.length === 0 ||
      isAddingProjectMembers
    ) return;

    setIsAddingProjectMembers(true);
    const addedStudentIds: string[] = [];
    const failedStudents: Array<{ id: string; message: string }> = [];
    try {
      for (const studentId of selectedProjectMemberIds) {
        try {
          await apiRequest(
            `/projects/${projectForMemberSelection.id}/members/${studentId}`,
            { method: "POST" },
          );
          addedStudentIds.push(studentId);
        } catch (error) {
          failedStudents.push({
            id: studentId,
            message: getErrorMessage(error, "Request failed"),
          });
        }
      }

      if (addedStudentIds.length > 0) {
        await loadProjects();
        invalidateProjectCaches(queryClient);
      }

      if (failedStudents.length > 0) {
        setSelectedProjectMemberIds(failedStudents.map(({ id }) => id));
        const failureDetails = failedStudents.map(({ id, message }) => {
          const studentName = courseStudents.find((student) => student.id === id)?.full_name ?? id;
          return `${studentName}: ${message}`;
        });
        toast.warning(
          `${addedStudentIds.length} student${addedStudentIds.length === 1 ? "" : "s"} added. ` +
          `${failedStudents.length} could not be added; failed students remain selected so you can retry.\n\n` +
          failureDetails.join("\n"),
        );
      } else {
        setProjectForMemberSelection(null);
        setSelectedProjectMemberIds([]);
        toast.success(
          `${addedStudentIds.length} student${addedStudentIds.length === 1 ? "" : "s"} added to the project.`,
        );
      }
    } finally {
      setIsAddingProjectMembers(false);
    }
  }

  function updateDraftFilter<K extends keyof ProjectFilters>(key: K, value: ProjectFilters[K]) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  }

  const filteredProjects = useProjectFilters(projects, searchTerm, appliedFilters);

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-blue-950 sm:text-3xl">Projects</h1>
          <p className="mt-1 text-base text-slate-500">Manage course sections, roster, and team project metrics</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm ring-1 ring-slate-100 min-h-11">
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-0">
              <BookOpen className="h-4 w-4 text-slate-400" />
              <select value={selectedCourseId} onChange={(event) => setSelectedCourseId(event.target.value)} className="min-h-9 min-w-[220px] appearance-none bg-transparent pr-5 text-sm font-semibold text-slate-700 outline-none">
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

            <button
              type="button"
              onClick={handleOpenCourseManagement}
              title="Manage courses"
              className="inline-flex h-9 items-center justify-center rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Course Management
            </button>
          </div>

          <button type="button" onClick={() => { setStudentSearchTerm(""); setIsRosterModalOpen(true); }} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
            <Users className="h-4 w-4 text-slate-500" />
            Students
          </button>

          <button type="button" onClick={() => setIsImportModalOpen(true)} disabled={!selectedCourseId} title="Bulk import students from CSV" className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
            <Upload className="h-4 w-4 text-slate-500" />
            Import Students
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

      {projects.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description={selectedCourseId ? "Create the first project for this course to start tracking a team." : "Select or create a course first. New Project becomes available once a course is selected."}
          action={selectedCourseId ? (
            <button type="button" onClick={handleOpenCreateProject} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800">
              <Plus className="h-4 w-4" />
              New Project
            </button>
          ) : undefined}
          className="rounded-2xl border border-dashed border-slate-300 bg-white p-10"
        />
      ) : filteredProjects.length === 0 ? (
        <EmptyState
          title="No projects match your filters"
          description="Try a different team name or module, or clear the filters to see every project."
          action={
            <button type="button" onClick={() => { setSearchTerm(""); setAppliedFilters(DEFAULT_FILTERS); setDraftFilters(DEFAULT_FILTERS); }} className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
              Clear filters
            </button>
          }
          className="rounded-2xl border border-dashed border-slate-300 bg-white p-10"
        />
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

      <ProjectModal
        isOpen={isProjectModalOpen}
        editingProject={editingProject}
        projectForm={projectForm}
        jiraEmail={jiraCredentials.jiraEmail}
        jiraApiToken={jiraCredentials.jiraApiToken}
        hasSavedJiraToken={jiraCredentials.hasSavedToken}
        isSaving={isSavingProject}
        onClose={() => {
          if (!isSavingProject) setIsProjectModalOpen(false);
        }}
        onSave={handleSaveProject}
        onJiraEmailChange={jiraCredentials.setJiraEmail}
        onJiraApiTokenChange={jiraCredentials.setJiraApiToken}
        setProjectForm={setProjectForm}
      />

      <CourseManagementModal
        isOpen={isCourseModalOpen}
        courses={courses}
        editingCourse={editingCourse}
        courseForm={courseForm}
        userName={session?.user?.fullName || "Instructor"}
        onClose={() => setIsCourseModalOpen(false)}
        onSave={handleCreateOrUpdateCourse}
        onDelete={handleDeleteCourse}
        setCourseForm={setCourseForm}
        setEditingCourse={setEditingCourse}
      />

      <RosterModal
        isOpen={isRosterModalOpen}
        hasSelectedCourse={Boolean(selectedCourseId && isUuid(selectedCourseId))}
        courseStudents={courseStudents}
        allStudents={allStudents}
        studentSearchTerm={studentSearchTerm}
        isLoadingStudents={isLoadingStudents}
        studentDirectoryError={studentDirectoryError}
        studentForm={studentForm}
        studentFormErrors={studentFormErrors}
        onClose={() => {
          setIsRosterModalOpen(false);
        }}
        onCreateStudent={handleCreateStudent}
        onEnrollExisting={handleEnrollExistingStudent}
        onUnenroll={handleUnenrollStudent}
        onRefreshStudents={() => void loadAllStudents()}
        setStudentSearchTerm={setStudentSearchTerm}
        setStudentForm={setStudentForm}
      />

      <CSVImportModal
        isOpen={isImportModalOpen}
        courseId={selectedCourseId}
        courseName={
          selectedCourseId
            ? courses.find((c) => c.id === selectedCourseId)
              ? `${courses.find((c) => c.id === selectedCourseId)?.code} · ${courses.find((c) => c.id === selectedCourseId)?.section}`
              : "Unknown Course"
            : "No Course Selected"
        }
        onClose={() => {
          setIsImportModalOpen(false);
          clearImportState();
        }}
        onValidatePreview={validateAndPreview}
        onSubmit={async () => {
          const result = await submitImport(selectedCourseId);
          await loadProjects();
          await loadCourseStudents();
          invalidateProjectCaches(queryClient);
          return result;
        }}
        isLoading={isImporting}
        error={importError}
        parsedRows={parsedRows}
      />

      <ProjectMembersModal
        isOpen={Boolean(projectForMemberSelection)}
        projectName={projectForMemberSelection?.team_name || "this project"}
        hasEnrolledStudents={courseStudents.length > 0}
        availableStudents={courseStudents.filter((student) => !projects.some((project) => project.members.some((member) => member.id === student.id)))}
        assignedStudents={courseStudents.flatMap((student) => {
          const assignedProject = projects.find((project) =>
            project.members.some((member) => member.id === student.id),
          );
          return assignedProject
            ? [{ ...student, projectName: assignedProject.team_name }]
            : [];
        })}
        selectedStudentIds={selectedProjectMemberIds}
        isAddingMembers={isAddingProjectMembers}
        onClose={() => {
          setProjectForMemberSelection(null);
          setSelectedProjectMemberIds([]);
        }}
        onToggleStudent={handleToggleProjectMember}
        onAddMember={handleConfirmAddProjectMember}
      />

      <ConfirmationModal
        isOpen={Boolean(memberToRemove)}
        onClose={() => setMemberToRemove(null)}
        onConfirm={handleConfirmedRemoveProjectMember}
        title="Remove Project Member"
        message={`Remove ${memberToRemove?.fullName || "this student"} from the project? They will remain enrolled in the course.`}
        confirmText="Remove Member"
        cancelText="Keep Member"
      />

      <ConfirmationModal
        isOpen={Boolean(projectToDelete)}
        onClose={() => setProjectToDelete(null)}
        onConfirm={() => void handleConfirmDeleteProject()}
        title="Delete Project"
        message={`Delete ${projectToDelete?.team_name || "this project"}? This cannot be undone.`}
        confirmText="Delete Project"
        cancelText="Cancel"
        variant="danger"
      />

      <ConfirmationModal
        isOpen={Boolean(courseToDelete)}
        onClose={() => setCourseToDelete(null)}
        onConfirm={() => void handleConfirmDeleteCourse()}
        title="Delete Course"
        message="Delete this course and all associated projects? This cannot be undone."
        confirmText="Delete Course"
        cancelText="Cancel"
        variant="danger"
      />

      <ProjectFilterModal
        isOpen={isFilterModalOpen}
        draftFilters={draftFilters}
        moduleOptions={moduleOptions}
        sortOptions={sortOptions}
        onDraftChange={updateDraftFilter}
        onClearForm={() => setDraftFilters(DEFAULT_FILTERS)}
        onApply={() => {
          setAppliedFilters(draftFilters);
          setIsFilterModalOpen(false);
        }}
        onClose={() => setIsFilterModalOpen(false)}
      />
    </div>
  );
}