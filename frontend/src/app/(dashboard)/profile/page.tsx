"use client";

import { useEffect, useState, useMemo } from "react";
import { Loader2 } from "lucide-react";

type UserProfile = {
  name: string;
  email: string;
  role: "student" | "instructor" | "admin";
  department?: string;
  activeSectionsCount?: number;
  teamsMonitoredCount?: number;
  pendingReviewsCount?: number;
  teamName?: string;
  enrolledCoursesCount?: number;
};

function getInitials(name: string): string {
  if (!name) return "US";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Retrieve base user info and auth token from your frontend session
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") || "student";
    const savedEmail = sessionStorage.getItem("sprintsight-auth-email") || "";
    const savedName = sessionStorage.getItem("sprintsight-auth-name") || "";
    const token = sessionStorage.getItem("sprintsight-auth-token") || ""; 

    // Point this to your FastAPI backend URL (or Next.js proxy)
    const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

    async function fetchProfileData() {
      try {
        let activeSectionsCount = 0;
        let teamsMonitoredCount = 0;

        // Based on projects.py, only INSTRUCTOR and ADMIN can GET /courses
        if ((savedRole === "instructor" || savedRole === "admin") && token) {
          const coursesRes = await fetch(`${API_BASE_URL}/courses`, {
            headers: { Authorization: `Bearer ${token}` },
          });

          if (coursesRes.ok) {
            const courses = await coursesRes.json();
            activeSectionsCount = courses.length;

            // Fetch projects for each course to calculate total monitored teams
            const projectPromises = courses.map((course: any) =>
              fetch(`${API_BASE_URL}/courses/${course.id}/projects`, {
                headers: { Authorization: `Bearer ${token}` },
              }).then((res) => (res.ok ? res.json() : []))
            );

            const projectsArrays = await Promise.all(projectPromises);
            teamsMonitoredCount = projectsArrays.reduce((acc, curr) => acc + curr.length, 0);
          }
        }
        
        // NOTE: Based on projects.py, STUDENTS receive a 403 on GET /courses.
        // To get enrolled courses for students, you will need a dedicated backend 
        // endpoint (e.g., GET /users/me/courses) which is not present in projects.py.
        
        setProfile({
          name: savedName || (savedEmail ? savedEmail.split("@")[0] : "User"),
          email: savedEmail,
          role: savedRole as UserProfile["role"],
          department: "Software Engineering",
          activeSectionsCount,
          teamsMonitoredCount,
          pendingReviewsCount: 0, // Implement if you add a reviews endpoint later
          teamName: "Unassigned", // Would require an endpoint to fetch student's specific project
          enrolledCoursesCount: savedRole === "student" ? 1 : 0, // Placeholder for student
        });

      } catch (error) {
        console.error("Failed to fetch profile details:", error);
        // Fallback on failure
        setProfile({
          name: savedName || (savedEmail ? savedEmail.split("@")[0] : "User"),
          email: savedEmail,
          role: savedRole as UserProfile["role"],
          department: "Software Engineering",
          activeSectionsCount: 0,
          teamsMonitoredCount: 0,
          pendingReviewsCount: 0,
        });
      } finally {
        setIsLoading(false);
      }
    }

    fetchProfileData();
  }, []);

  const initials = useMemo(() => getInitials(profile?.name || ""), [profile?.name]);

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="h-6 w-6 animate-spin" />
        <span className="ml-2 text-sm font-medium">Loading profile...</span>
      </div>
    );
  }

  const roleLabel = profile?.role
    ? profile.role.charAt(0).toUpperCase() + profile.role.slice(1)
    : "User";

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-blue-600">Profile</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{profile?.name}</h1>
        </div>

        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-2xl font-bold text-blue-700">
          {initials}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Account details</h2>
          <div className="mt-4 space-y-4 text-sm text-slate-600">
            <div>
              <span className="font-medium text-slate-500">Role</span>
              <p className="mt-1 text-slate-900">{roleLabel}</p>
            </div>
            <div>
              <span className="font-medium text-slate-500">Email</span>
              <p className="mt-1 text-slate-900">{profile?.email || "N/A"}</p>
            </div>
            <div>
              <span className="font-medium text-slate-500">Department</span>
              <p className="mt-1 text-slate-900">{profile?.department || "N/A"}</p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">
            {profile?.role === "instructor" || profile?.role === "admin" ? "Teaching summary" : "Academic summary"}
          </h2>
          <div className="mt-4 space-y-4">
            {profile?.role === "instructor" || profile?.role === "admin" ? (
              <>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Active sections</span>
                  <span className="font-semibold text-slate-900">{profile.activeSectionsCount}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Teams monitored</span>
                  <span className="font-semibold text-slate-900">{profile.teamsMonitoredCount}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Reviews pending</span>
                  <span className="font-semibold text-slate-900">{profile.pendingReviewsCount}</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Enrolled courses</span>
                  <span className="font-semibold text-slate-900">{profile?.enrolledCoursesCount ?? 1}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Assigned Team</span>
                  <span className="font-semibold text-slate-900">{profile?.teamName || "Unassigned"}</span>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}