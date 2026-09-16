import type { DashboardProject, DashboardRole } from "@/features/dashboard/types";

type DashboardHeaderProps = {
  role: DashboardRole;
  fullName: string;
};

export function DashboardHeader({ role, fullName }: DashboardHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{role === "student" ? "My Dashboard" : "Dashboard"}</h1>
        <p className="mt-1 text-slate-500">{fullName || (role === "student" ? "Student" : "Instructor")}</p>
      </div>
    </div>
  );
}
