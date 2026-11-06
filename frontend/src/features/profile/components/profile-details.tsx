import type { UserProfile } from "@/features/profile/types";

function getInitials(name: string): string {
  if (!name) return "US";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function ProfileDetails({ profile }: { profile: UserProfile }) {
  const initials = getInitials(profile.name);
  const roleLabel = profile.role
    ? profile.role.charAt(0).toUpperCase() + profile.role.slice(1)
    : "User";

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-blue-600">Profile</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{profile.name}</h1>
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
              <p className="mt-1 text-slate-900">{profile.email || "N/A"}</p>
            </div>
            <div>
              <span className="font-medium text-slate-500">Department</span>
              <p className="mt-1 text-slate-900">{profile.department ?? "—"}</p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">
            {profile.role === "instructor" || profile.role === "admin"
              ? "Teaching summary"
              : "Academic summary"}
          </h2>
          <div className="mt-4 space-y-4">
            {profile.role === "instructor" || profile.role === "admin" ? (
              <>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Active sections</span>
                  <span className="font-semibold text-slate-900">
                    {profile.activeSectionsCount}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Teams monitored</span>
                  <span className="font-semibold text-slate-900">
                    {profile.teamsMonitoredCount}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Reviews pending</span>
                  <span className="font-semibold text-slate-900">
                    {profile.pendingReviewsCount ?? "—"}
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Enrolled courses</span>
                  <span className="font-semibold text-slate-900">
                    {profile.enrolledCoursesCount ?? "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                  <span className="text-slate-600">Assigned Team</span>
                  <span className="font-semibold text-slate-900">
                    {profile.teamName ?? "—"}
                  </span>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
