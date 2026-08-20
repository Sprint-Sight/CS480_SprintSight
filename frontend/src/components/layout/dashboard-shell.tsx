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
  Eye,
  FileText,
  FolderOpen,
  GitCompare,
  LayoutDashboard,
  Pencil,
  Search,
  Settings,
  User,
  Users,
} from "lucide-react";

type DashboardShellProps = {
  children: React.ReactNode;
};

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
};

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Sprint Overview", href: "/sprint-overview", icon: Activity },
  { label: "Artifact Viewer", href: "/artifact-viewer", icon: Eye },
  { label: "Collaboration", href: "/collaboration", icon: BarChart3 },
  { label: "Assessment Report", href: "/assessment-report", icon: FileText },
  { label: "Contributions", href: "/contributions", icon: Users },
  { label: "Instructor Review", href: "/instructor-review", icon: Pencil },
  { label: "Progress", href: "/progress", icon: GitCompare },
  { label: "Settings", href: "/settings", icon: Settings },
];

const semesterOptions = ["Spring 2026", "Fall 2025", "Summer 2025"];
const sectionOptions = [
  "SE3402-A — Software Engineering",
  "SE3402-B — Software Engineering",
  "CS480-A — Capstone",
];
const teamOptions = [
  "Team Alpha — E-Commerce",
  "Team Beta — Chat App",
  "Team Gamma — Task Manager",
  "Team Delta — Social Network",
];

function isActivePath(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function DashboardShell({ children }: DashboardShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const isProjectsArea = pathname === "/projects" || pathname.startsWith("/projects/");
  const isProjectsListPage = pathname === "/projects";
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [role, setRole] = useState<"student" | "instructor">("instructor");
  const [selectedSemester, setSelectedSemester] = useState("Spring 2026");
  const [selectedSection, setSelectedSection] = useState("SE3402-A — Software Engineering");
  const [selectedTeam, setSelectedTeam] = useState("Team Alpha — E-Commerce");
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    const email = sessionStorage.getItem("sprintsight-auth-email");

    if (!savedRole || !email) {
      router.replace("/login");
      return;
    }

    setRole(savedRole);
    setIsAuthorized(true);
  }, [router]);

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
    if (isAuthorized && role === "student" && isProjectsArea) {
      router.replace("/");
    }
  }, [isAuthorized, role, isProjectsArea, router]);

  const profileLabel = useMemo(() => {
    return role === "student" ? "Student" : "Instructor";
  }, [role]);

  const handleLogout = () => {
    sessionStorage.removeItem("sprintsight-auth-role");
    sessionStorage.removeItem("sprintsight-auth-email");
    setIsProfileMenuOpen(false);
    router.replace("/login");
  };

  if (!isAuthorized) {
    return null;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="border-r border-slate-200 bg-white md:sticky md:top-0 md:h-screen">
          <div className="flex h-full flex-col md:h-screen">
            {/* Centered Logo Header */}
            <div className="flex items-center justify-center border-b border-slate-200 px-4 py-3">
              <Image
                src="/logo.png"
                alt="SprintSight Logo"
                width={160}
                height={60}
                priority
                className="h-14 w-auto max-w-full object-contain"
              />
            </div>

            <nav className="flex-1 px-3 py-4 space-y-1">
              {navItems.map((item) => {
                if (role === "student" && item.href === "/projects") {
                  return null;
                }

                const active = isActivePath(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-blue-50 text-blue-700 font-medium"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    }`}
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto p-3 border-t border-slate-200">
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

        <section className="min-w-0">
          <header className="border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
            <div className="flex items-center justify-between gap-4">
              <div className="relative hidden w-full max-w-xl sm:block">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search projects, sprints, students..."
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <div className="ml-auto flex items-center gap-3">
                <button
                  type="button"
                  className="relative flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-600 transition-colors hover:bg-slate-100"
                  aria-label="Notifications"
                >
                  <Bell className="h-4 w-4" />
                  <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500" />
                </button>

                <div ref={menuRef} className="relative">
                  <button
                    type="button"
                    onClick={() => setIsProfileMenuOpen((open) => !open)}
                    className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-2 py-1.5 text-left transition-colors hover:bg-slate-100"
                    aria-expanded={isProfileMenuOpen}
                    aria-label="Open profile menu"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
                      SC
                    </div>
                    <div className="flex flex-col text-right">
                      <span className="text-sm font-semibold text-slate-800">Dr. Sarah Chen</span>
                      <span className="text-[11px] text-slate-500">{profileLabel}</span>
                    </div>
                  </button>

                  {isProfileMenuOpen && (
                    <div className="absolute right-0 z-50 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-[0_12px_28px_rgba(15,23,42,0.12)]">
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-100"
                      >
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
                          SC
                        </div>
                        <div>
                          <div className="font-semibold text-slate-900">Dr. Sarah Chen</div>
                          <div className="text-xs text-slate-500">{profileLabel}</div>
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

            {role === "instructor" && !isProjectsListPage && (
              <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
                <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600">
                  <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                  Scope
                </div>

                <div className="relative">
                  <select
                    value={selectedSemester}
                    onChange={(e) => setSelectedSemester(e.target.value)}
                    className="appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  >
                    {semesterOptions.map((semester) => (
                      <option key={semester} value={semester}>
                        {semester}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>

                <div className="relative">
                  <select
                    value={selectedSection}
                    onChange={(e) => setSelectedSection(e.target.value)}
                    className="appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  >
                    {sectionOptions.map((section) => (
                      <option key={section} value={section}>
                        {section}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>

                <div className="relative">
                  <select
                    value={selectedTeam}
                    onChange={(e) => setSelectedTeam(e.target.value)}
                    className="appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-700 shadow-sm focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  >
                    {teamOptions.map((team) => (
                      <option key={team} value={team}>
                        {team}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>

                <div className="ml-auto flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-1.5 text-sm text-blue-700">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  On Track · 4 students · avg 82
                </div>
              </div>
            )}
          </header>
          <main>{children}</main>
        </section>
      </div>
    </div>
  );
}