"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

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
  const queryClient = useQueryClient();

  const [teaching, setTeaching] = useState({ activeSectionsCount: 0, teamsMonitoredCount: 0 });
  const [isLoading, setIsLoading] = useState(isFaculty);

  useEffect(() => {
    if (!isFaculty) {
      setIsLoading(false);
      return;
    }

    let isCurrent = true;
    setIsLoading(true);
    getTeachingSummary(queryClient)
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
  }, [isFaculty, queryClient]);

  // No endpoint yet provides department, pending reviews, a student's team, or a student's
  // enrolled courses, so those stay null and render as "—" instead of invented values.
  const profile: UserProfile = {
    name,
    email,
    role,
    department: null,
    activeSectionsCount: teaching.activeSectionsCount,
    teamsMonitoredCount: teaching.teamsMonitoredCount,
    pendingReviewsCount: null,
    teamName: null,
    enrolledCoursesCount: null,
  };

  return { profile, isLoading };
}
