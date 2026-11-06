/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { ProfileDetails } from "@/features/profile/components/profile-details";
import type { UserProfile } from "@/features/profile/types";

const baseProfile: UserProfile = {
  name: "Ada Lovelace",
  email: "ada@example.edu",
  role: "instructor",
  department: null,
  activeSectionsCount: 2,
  teamsMonitoredCount: 5,
  pendingReviewsCount: null,
  teamName: null,
  enrolledCoursesCount: null,
};

describe("ProfileDetails", () => {
  it("shows a dash instead of invented department or review counts", () => {
    renderComponent(<ProfileDetails profile={baseProfile} />);

    expect(screen.queryByText("Software Engineering")).not.toBeInTheDocument();
    expect(screen.getByText("Reviews pending").nextElementSibling).toHaveTextContent("—");
    expect(screen.getByText("Department").nextElementSibling).toHaveTextContent("—");
  });

  it("renders real instructor teaching counts", () => {
    renderComponent(<ProfileDetails profile={baseProfile} />);

    expect(screen.getByText("Active sections").nextElementSibling).toHaveTextContent("2");
    expect(screen.getByText("Teams monitored").nextElementSibling).toHaveTextContent("5");
  });

  it("shows a dash for unknown student course and team values, not a made-up 1 or Unassigned", () => {
    renderComponent(
      <ProfileDetails
        profile={{ ...baseProfile, role: "student", activeSectionsCount: undefined, teamsMonitoredCount: undefined }}
      />,
    );

    expect(screen.getByText("Enrolled courses").nextElementSibling).toHaveTextContent("—");
    expect(screen.getByText("Assigned Team").nextElementSibling).toHaveTextContent("—");
    expect(screen.queryByText("Unassigned")).not.toBeInTheDocument();
  });
});
