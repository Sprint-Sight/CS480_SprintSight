"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/lib/auth/session";
import { getTeachingSummary } from "@/features/profile/profile-api";
import type { UserProfile } from "@/features/profile/types";

export function useProfileData() {
  const session = useSession();
  const user = session?.user ?? null;
  const role = user?.role ?? "student";
  const email = user?.email ?? "";
  const name = user?.fullName || (email ? email.split("@")[0] : "User");
  const isFaculty = role === "instructor" || role === "admin";

  const [teaching, setTeaching] = useState({ activeSectionsCount: 0, teamsMonitoredCount: 0 });
  const [isLoading, setIsLoading] = useState(isFaculty);

  useEffect(() => {
    if (!isFaculty) {
      setIsLoading(false);
      return;
    }

    let isCurrent = true;
    setIsLoading(true);
    getTeachingSummary()
      .then((summary) => {
        if (isCurrent) setTeaching(summary);
      })
      .catch((error) => {
        // Keep the zero counts; the rest of the profile is still useful.
        console.error("Failed to fetch profile details:", error);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [isFaculty]);

  // NOTE: students receive a 403 on GET /courses, and there is no endpoint yet for a
  // student's courses, department, or pending reviews, so those stay as placeholders.
  const profile: UserProfile = {
    name,
    email,
    role,
    department: "Software Engineering",
    activeSectionsCount: teaching.activeSectionsCount,
    teamsMonitoredCount: teaching.teamsMonitoredCount,
    pendingReviewsCount: 0, // Implement if you add a reviews endpoint later
    teamName: "Unassigned", // Would require an endpoint to fetch student's specific project
    enrolledCoursesCount: role === "student" ? 1 : 0, // Placeholder for student
  };

  return { profile, isLoading };
}
