export type UserProfile = {
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
