export type UserProfile = {
  name: string;
  email: string;
  role: "student" | "instructor" | "admin";
  /** null when no endpoint provides the value yet; rendered as "—". */
  department: string | null;
  activeSectionsCount?: number;
  teamsMonitoredCount?: number;
  pendingReviewsCount: number | null;
  teamName: string | null;
  enrolledCoursesCount: number | null;
};
