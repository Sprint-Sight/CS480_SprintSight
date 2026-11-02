import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JiraContributionOutlierModal } from "@/features/peer-evaluation/components/jira-contribution-outlier-modal";
import type { JiraContributionStudent } from "@/features/peer-evaluation/peer-evaluation-api";

const student: JiraContributionStudent = {
  student_id: "student-1",
  student_full_name: "Student One",
  course_id: "course-1",
  project_id: "project-1",
  total_tickets: 1,
  total_story_points: 8,
  average_points_per_ticket: 8,
  course_average_total_points: 4,
  course_total_score_std_dev: 2,
  contribution_z_score: 2,
  is_contribution_outlier: true,
  outlier_direction: "high",
  students_below_course_average: 1,
  enrolled_student_count: 2,
  students_with_jira_data: 1,
  tickets: [{
    ticket_id: "PROJ-1",
    summary: "Implement feature",
    story_points: 8,
    status: "Done",
    issue_type: "Story",
    project_id: "project-1",
    sprint_id: "sprint-2",
  }],
};

describe("JiraContributionOutlierModal", () => {
  it("shows aligned contribution metrics and ticket details in a modal", () => {
    render(
      <JiraContributionOutlierModal
        isOpen
        studentName="Student One"
        studentDetail={student}
        isLoading={false}
        error={null}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("Total story points")).toBeTruthy();
    expect(screen.getByText("Course average")).toBeTruthy();
    expect(screen.getByText("PROJ-1")).toBeTruthy();
    expect(screen.getByText("sprint-2")).toBeTruthy();
  });

  it("closes when the close button is pressed", () => {
    const onClose = vi.fn();
    render(
      <JiraContributionOutlierModal
        isOpen
        studentName="Student One"
        studentDetail={null}
        isLoading
        error={null}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close Jira contribution details" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
