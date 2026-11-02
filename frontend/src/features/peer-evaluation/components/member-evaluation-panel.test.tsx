import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemberEvaluationPanel } from "@/features/peer-evaluation/components/member-evaluation-panel";
import type { MemberPeerEvaluationDetail } from "@/features/peer-evaluation/peer-evaluation-api";

const member: MemberPeerEvaluationDetail = {
  course_id: "course-1",
  project_id: "project-1",
  project_name: "Team Alpha",
  member_id: "student-1",
  member_email: "student1@example.com",
  member_full_name: "Student One",
  evaluations: [{
    evaluation_id: "evaluation-1",
    course_id: "course-1",
    project_id: "project-1",
    rater_id: "student-2",
    rater_email: "student2@example.com",
    rater_full_name: "Student Two",
    rated_id: "student-1",
    rated_email: "student1@example.com",
    rated_full_name: "Student One",
    score: 2,
    remarks: "Could communicate more often.",
    created_at: "2026-10-27T00:00:00Z",
    is_score_outlier: true,
    score_z_score: -1.5,
  }],
  total_score: 2,
  average_score: 2,
  evaluation_count: 1,
  is_total_outlier: true,
  total_z_score: -1.2,
  outlier_direction: "low",
  course_average_total: 4,
  course_total_score_std_dev: 1,
  enrolled_student_count: 4,
  students_with_received_evaluations: 3,
  students_below_course_average: 1,
};

describe("MemberEvaluationPanel", () => {
  it("shows all evaluations under their rated member and opens separate Jira evidence", () => {
    const onViewJiraContribution = vi.fn();
    render(
      <MemberEvaluationPanel
        members={[member]}
        jiraOutlierStudentIds={new Set(["student-1"])}
        isLoading={false}
        error={null}
        jiraReportError={null}
        onViewJiraContribution={onViewJiraContribution}
      />,
    );

    expect(screen.getByText("Student One")).toBeTruthy();
    expect(screen.getByText("Student Two")).toBeTruthy();
    expect(screen.getByText("Could communicate more often.")).toBeTruthy();
    expect(screen.getByText("Peer-score outlier (low)")).toBeTruthy();
    expect(screen.getByText("Score outlier")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Jira contribution outlier/i }));
    expect(onViewJiraContribution).toHaveBeenCalledWith("student-1");
  });
});
