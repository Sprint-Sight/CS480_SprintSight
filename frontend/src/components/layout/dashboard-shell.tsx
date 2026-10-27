"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  ChevronDown,
  ClipboardList,
  Eye,
  FileText,
  FolderOpen,
  GitCompare,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Search,
  Settings,
  User,
  Loader2,
  X,
} from "lucide-react";

import { apiRequest, getAuthToken } from "@/features/projects/components/projects-api";
import { readIngestionState, writeIngestionState } from "@/features/ingestion/state";
import { useNotifications } from "@/hooks/use-notifications";
import { NotificationsDropdown } from "@/components/ui/notifications-modal";

type DashboardShellProps = {
  children: React.ReactNode;
};

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
};

type ScopeSection = {
  id: string;
  name: string;
  code: string;
};

type ScopeTeam = {
  id: string;
  name: string;
  courseId: string;
  status: string;
  studentCount: number;
  averageScore: number;
};

const instructorNavItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Sprint Overview", href: "/sprint-overview", icon: Activity },
  { label: "Artifact Viewer", href: "/artifact-viewer", icon: Eye },
  { label: "Collaboration", href: "/collaboration", icon: BarChart3 },
  { label: "Assessment Report", href: "/assessment-report", icon: FileText },
  { label: "Peer Evaluation", href: "/peer-evaluation", icon: MessageSquare },
  { label: "Progress", href: "/progress", icon: GitCompare },
  { label: "Audit Log", href: "/audit-log", icon: ClipboardList },
  { label: "Settings", href: "/settings", icon: Settings },
];

const studentNavItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "My Sprint", href: "/sprint-overview", icon: Activity },
  { label: "Artifact Viewer", href: "/artifact-viewer", icon: Eye },
  { label: "Collaboration", href: "/collaboration", icon: BarChart3 },
  { label: "Results & Feedback", href: "/assessment-report", icon: FileText },
  { label: "Peer Evaluation", href: "/peer-evaluation", icon: MessageSquare },
  { label: "Progress", href: "/progress", icon: GitCompare },
];

const instructorScopeRoutes = new Set([
  "/",
  "/sprint-overview",
  "/artifact-viewer",
  "/collaboration",
  "/assessment-report",
  "/peer-evaluation",
  "/progress",
]);

function isActivePath(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function getInitials(name: string): string {
  if (!name) return "US";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function DashboardShell({ children }: DashboardShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const isProjectsRoot = pathname === "/projects";
  const showsInstructorScope = instructorScopeRoutes.has(pathname);
  const showsSprintScope = showsInstructorScope && pathname !== "/progress";
  const isRestrictedForStudent = pathname === "/projects" || pathname === "/settings" || pathname === "/audit-log";
  const menuRef = useRef<HTMLDivElement | null>(null);

  const [isAuthorized, setIsAuthorized] = useState(false);
  const [role, setRole] = useState<"student" | "instructor">("instructor");
  const [userName, setUserName] = useState<string>("");
  const [userEmail, setUserEmail] = useState<string>("");
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [isNotificationsModalOpen, setIsNotificationsModalOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Use notifications hook
  const { notifications, unreadCount, isLoading: isLoadingNotifications, error: notificationError, markAsRead, markAllAsRead } = useNotifications();

  // Dynamic scope states fetched from DB / API
  const [semesterOptions, setSemesterOptions] = useState<string[]>([]);
  const [sections, setSections] = useState<ScopeSection[]>([]);
  const [teams, setTeams] = useState<ScopeTeam[]>([]);
  
  const [selectedSemester, setSelectedSemester] = useState<string>("");
  const [selectedSectionId, setSelectedSectionId] = useState<string>("");
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [selectedSprintId, setSelectedSprintId] = useState<string>("sprint-1");
  const [isLoadingScope, setIsLoadingScope] = useState<boolean>(false);

  useEffect(() => {
    if (isAuthorized && role === "student" && isRestrictedForStudent) {
      router.replace("/");
    }
  }, [isAuthorized, role, isRestrictedForStudent, router]);

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role");
    const email = sessionStorage.getItem("sprintsight-auth-email");
    const name = sessionStorage.getItem("sprintsight-auth-name");

    if (!savedRole || !email) {
      router.replace("/login");
      return;
    }

    // Redirect admin users out of student/instructor sidebar routes
    if (savedRole === "admin") {
      router.replace("/admin");
      return;
    }

    setRole(savedRole as "student" | "instructor");
    setUserEmail(email);
    if (name) {
      setUserName(name);
    }
    setIsAuthorized(true);
  }, [router]);

  // Fetch Scope options dynamically from DB for instructors
  useEffect(() => {
    if (!isAuthorized || role !== "instructor") return;

    async function fetchScopeData() {
      setIsLoadingScope(true);
      try {
        const courses = await apiRequest<Array<{ id: string; code: string; name: string; section: string; term: string; year: number }>>("/courses");
        const courseSections = courses.map((course) => ({
          id: course.id,
          code: course.code,
          name: `${course.name} - ${course.section}`,
        }));
        const projectGroups = await Promise.all(courses.map(async (course) => ({
          course,
          projects: await apiRequest<Array<{ id: string; team_name: string; members: unknown[] }>>(`/courses/${course.id}/projects`),
        })));
        const scopeTeams = projectGroups.flatMap(({ course, projects }) => projects.map((project) => ({
          id: project.id,
          name: project.team_name,
          status: "Active",
          studentCount: project.members.length,
          averageScore: 0,
          courseId: course.id,
        })));
        const persisted = readIngestionState();
        const selectedTeam = scopeTeams.find((team) => team.id === persisted.selectedProjectId) || scopeTeams[0];

        setSemesterOptions([...new Set(courses.map((course) => `${course.term} ${course.year}`))]);
        setSections(courseSections);
        setTeams(scopeTeams);
        setSelectedSemester(`${courses[0]?.term || ""} ${courses[0]?.year || ""}`.trim());
        setSelectedSectionId(selectedTeam?.courseId || courseSections[0]?.id || "");
        setSelectedTeamId(selectedTeam?.id || "");
        setSelectedSprintId(persisted.selectedSprintId || "sprint-1");
        if (selectedTeam) {
          writeIngestionState({ selectedProjectId: selectedTeam.id, selectedCourseId: selectedTeam.courseId });
        }
      } catch (error) {
        console.error("Failed to load dashboard scope data:", error);
      } finally {
        setIsLoadingScope(false);
      }
    }

    fetchScopeData();
  }, [isAuthorized, role]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsProfileMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (isAuthorized && role === "student" && isProjectsRoot) {
      router.replace("/");
    }
  }, [isAuthorized, role, isProjectsRoot, router]);

  const profileUser = useMemo(() => {
    const fallbackName = userEmail ? userEmail.split("@")[0] : "User";
    const displayName = userName || fallbackName;
    const label = role === "student" ? "Student" : "Instructor";
    const initials = getInitials(displayName);

    return { name: displayName, label, initials };
  }, [role, userName, userEmail]);

  const currentTeamStats = useMemo(() => {
    return teams.find((t) => t.id === selectedTeamId) || null;
  }, [teams, selectedTeamId]);

  const teamsInSelectedSection = useMemo(
    () => teams.filter((team) => team.courseId === selectedSectionId),
    [selectedSectionId, teams],
  );

  useEffect(() => {
    const selectedTeam = teams.find((team) => team.id === selectedTeamId);
    if (selectedTeam) {
      writeIngestionState({ selectedProjectId: selectedTeam.id, selectedCourseId: selectedTeam.courseId });
    }
  }, [selectedTeamId, teams]);

  useEffect(() => {
    const selectedTeam = teams.find((team) => team.id === selectedTeamId && team.courseId === selectedSectionId);
    if (selectedTeam) return;

    const firstTeamInSection = teams.find((team) => team.courseId === selectedSectionId);
    setSelectedTeamId(firstTeamInSection?.id || "");
    writeIngestionState({
      selectedProjectId: firstTeamInSection?.id || "",
      selectedCourseId: selectedSectionId,
    });
  }, [selectedSectionId, selectedTeamId, teams]);

  useEffect(() => {
    if (isAuthorized && role === "instructor") writeIngestionState({ selectedSprintId });
  }, [isAuthorized, role, selectedSprintId]);

  const navItems = role === "student" ? studentNavItems : instructorNavItems;

  const handleLogout = () => {
    sessionStorage.removeItem("sprintsight-auth-role");
    sessionStorage.removeItem("sprintsight-auth-email");
    sessionStorage.removeItem("sprintsight-auth-name");
    localStorage.removeItem("sprintsight-access-token");
    sessionStorage.removeItem("sprintsight-access-token");
    setIsProfileMenuOpen(false);
    router.replace("/login");
  };

  if (!isAuthorized) {
    return null;
  }

  return (
    <>
      <div className="h-dvh overflow-hidden bg-slate-50 text-slate-900">
        <div className="grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden md:grid-cols-[240px_minmax(0,1fr)]">
          {/* Mobile Overlay */}
          {isSidebarOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/50 md:hidden"
              onClick={() => setIsSidebarOpen(false)}
              aria-hidden="true"
            />
          )}

          {/* Sidebar */}
          <aside
            className={`fixed inset-y-0 left-0 z-50 w-64 transform overflow-hidden border-r border-slate-200 bg-white transition-transform duration-300 md:static md:z-auto md:transform-none md:w-auto ${
              isSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
            }`}
          >
            <div className="flex h-full flex-col">
              {/* Logo + Close Button */}
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <Image
                  src="/logo.png"
                  alt="SprintSight Logo"
                  width={160}
                  height={60}
                  priority
                  className="h-14 w-auto max-w-full object-contain"
                />
                <button
                  type="button"
                  onClick={() => setIsSidebarOpen(false)}
                  className="md:hidden p-1 hover:bg-slate-100 rounded-lg text-slate-600"
                  aria-label="Close sidebar"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-4">
                {navItems.map((item) => {
                  const active = isActivePath(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsSidebarOpen(false)}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                        active
                          ? "bg-blue-50 font-medium text-blue-700"
                          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                      }`}
                    >
                      <item.icon className="h-4 w-4 flex-shrink-0" />
                      <span>{item.label}</span>
                    </Link>
                  );
                })}
              </nav>

              <div className="border-t border-slate-200 p-3">
                <button
                  type="button"
                  onClick={handleLogout}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                >
                  Sign Out
                </button>
              </div>
            </div>
          </aside>

          <section className="flex min-h-0 min-w-0 flex-col overflow-hidden">
            <header className="min-w-0 shrink-0 border-b border-slate-200 bg-white px-3 py-3 sm:px-6">
              <div className="flex min-w-0 items-center justify-between gap-3 sm:gap-4">
                {/* Mobile Menu Button */}
                <button
                  type="button"
                  onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                  className="md:hidden p-2 hover:bg-slate-100 rounded-lg text-slate-600"
                  aria-label="Toggle sidebar"
                  aria-expanded={isSidebarOpen}
                >
                  <Menu className="h-5 w-5" />
                </button>

                {/* Search Bar - Hidden on small screens */}
                <div className="relative hidden min-w-0 w-full max-w-xl flex-1 sm:block">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search projects, sprints, students..."
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                {/* Top right actions */}
                <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
                  {/* Notifications */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setIsNotificationsModalOpen(!isNotificationsModalOpen)}
                      className="relative flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-600 transition-colors hover:bg-slate-100"
                      aria-label="Notifications"
                      title="Open notifications"
                      aria-expanded={isNotificationsModalOpen}
                    >
                      <Bell className="h-4 w-4" />
                      {unreadCount > 0 && (
                        <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                          {unreadCount > 99 ? "99+" : unreadCount}
                        </span>
                      )}
                    </button>

                    <NotificationsDropdown
                      isOpen={isNotificationsModalOpen}
                      onClose={() => setIsNotificationsModalOpen(false)}
                      notifications={notifications}
                      unreadCount={unreadCount}
                      isLoading={isLoadingNotifications}
                      error={notificationError}
                      onMarkAsRead={markAsRead}
                      onMarkAllAsRead={markAllAsRead}
                    />
                  </div>

                  {/* Profile Menu */}
                  <div ref={menuRef} className="relative">
                    <button
                      type="button"
                      onClick={() => setIsProfileMenuOpen((open) => !open)}
                      className="flex items-center gap-1.5 sm:gap-2 rounded-full border border-slate-200 bg-slate-50 px-1.5 sm:px-2 py-1.5 text-left transition-colors hover:bg-slate-100"
                      aria-expanded={isProfileMenuOpen}
                      aria-label="Open profile menu"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700 flex-shrink-0">
                        {profileUser.initials}
                      </div>
                      <div className="hidden sm:flex flex-col text-right">
                        <span className="text-sm font-semibold text-slate-800">{profileUser.name}</span>
                        <span className="text-[11px] text-slate-500">{profileUser.label}</span>
                      </div>
                    </button>

                    {isProfileMenuOpen && (
                      <div className="absolute right-0 z-50 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-[0_12px_28px_rgba(15,23,42,0.12)]">
                        <button
                          type="button"
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-100"
                        >
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700 flex-shrink-0">
                            {profileUser.initials}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900">{profileUser.name}</div>
                            <div className="text-xs text-slate-500">{profileUser.label}</div>
                          </div>
                        </button>

                        <div className="my-1 h-px bg-slate-200" />

                        <Link
                          href="/profile"
                          onClick={() => setIsProfileMenuOpen(false)}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-100"
                        >
                          <User className="h-4 w-4 text-slate-500" />
                          View profile
                        </Link>

                        <button
                          type="button"
                          onClick={handleLogout}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-100"
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4 text-slate-500">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" strokeLinecap="round" strokeLinejoin="round" />
                            <path d="M16 17l5-5-5-5" strokeLinecap="round" strokeLinejoin="round" />
                            <path d="M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          Sign out
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {role === "instructor" && showsInstructorScope && (
                <div className="mt-4 flex min-w-0 flex-row flex-wrap items-center gap-2 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-2">
                  <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 flex-shrink-0">
                    <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                    Scope
                  </div>

                  {isLoadingScope ? (
                    <div className="flex items-center gap-2 px-3 text-xs text-slate-500">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading Scope...
                    </div>
                  ) : (
                    <>
                      {/* Semester Select */}
                      {semesterOptions.length > 0 && (
                        <div className="relative w-full min-w-0 max-w-full sm:w-auto sm:min-w-[140px] sm:max-w-xs">
                          <select
                            value={selectedSemester}
                            onChange={(e) => setSelectedSemester(e.target.value)}
                            className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          >
                            {semesterOptions.map((semester) => (
                              <option key={semester} value={semester}>
                                {semester}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        </div>
                      )}

                      {/* Section Select */}
                      {sections.length > 0 && (
                        <div className="relative w-full min-w-0 max-w-full sm:w-auto sm:min-w-[140px] sm:max-w-xs">
                          <select
                            value={selectedSectionId}
                            onChange={(e) => setSelectedSectionId(e.target.value)}
                            className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          >
                            {sections.map((section) => (
                              <option key={section.id} value={section.id}>
                                {section.code} — {section.name}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        </div>
                      )}

                      {/* Team Select */}
                      {teamsInSelectedSection.length > 0 && (
                        <div className="relative w-full min-w-0 max-w-full sm:w-auto sm:min-w-[140px] sm:max-w-xs">
                          <select
                            value={selectedTeamId}
                            onChange={(e) => setSelectedTeamId(e.target.value)}
                            className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          >
                            {teamsInSelectedSection.map((team) => (
                              <option key={team.id} value={team.id}>
                                {team.name}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        </div>
                      )}
                      {showsSprintScope && (
                        <div className="relative w-full min-w-0 max-w-full sm:w-auto sm:min-w-[140px] sm:max-w-xs">
                          <select value={selectedSprintId} onChange={(event) => setSelectedSprintId(event.target.value)} className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100">
                            {Array.from({ length: 10 }, (_, index) => `sprint-${index + 1}`).map((sprintId) => <option key={sprintId} value={sprintId}>{sprintId}</option>)}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        </div>
                      )}
                    </>
                  )}

                  <div className="ml-auto flex min-w-0 max-w-full items-center gap-3 sm:flex-shrink-0">
                    {currentTeamStats && (
                      <div className="flex min-w-0 max-w-full items-center gap-2 overflow-hidden rounded-md border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 sm:text-sm">
                        <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500 flex-shrink-0" />
                        <span className="truncate">{currentTeamStats.status} · {currentTeamStats.studentCount} students · avg {currentTeamStats.averageScore}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </header>
            <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain">
              {children}
            </main>
          </section>
        </div>
      </div>
    </>
  );
}