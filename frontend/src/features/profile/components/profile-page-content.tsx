"use client";

import { Loader2 } from "lucide-react";

import { ProfileDetails } from "@/features/profile/components/profile-details";
import { useProfileData } from "@/features/profile/hooks/use-profile-data";

export default function ProfilePageContent() {
  const { profile, isLoading } = useProfileData();

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500" role="status">
        <Loader2 className="h-6 w-6 animate-spin" />
        <span className="ml-2 text-sm font-medium">Loading profile...</span>
      </div>
    );
  }

  return <ProfileDetails profile={profile} />;
}
