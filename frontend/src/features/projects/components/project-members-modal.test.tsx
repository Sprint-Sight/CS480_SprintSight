import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectMembersModal } from "@/features/projects/components/project-members-modal";

describe("ProjectMembersModal", () => {
  it("renders available students as checkboxes and enables adding when selected", () => {
    const onToggleStudent = vi.fn();
    const onAddMember = vi.fn();
    const props = {
      isOpen: true,
      projectName: "Team Alpha",
      hasEnrolledStudents: true,
      availableStudents: [
        { id: "student-1", full_name: "Student One", email: "one@example.com" },
        { id: "student-2", full_name: "Student Two", email: "two@example.com" },
      ],
      assignedStudents: [
        {
          id: "student-3",
          full_name: "Student Three",
          email: "three@example.com",
          projectName: "Team Beta",
        },
      ],
      selectedStudentIds: [] as string[],
      isAddingMembers: false,
      onClose: vi.fn(),
      onToggleStudent,
      onAddMember,
    };
    const { rerender } = render(<ProjectMembersModal {...props} />);

    expect(screen.getByRole("checkbox", { name: /Student One/ })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: /Student Two/ })).toBeTruthy();
    expect(screen.getByText("Project group: Team Beta")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /Student Three/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Add to Project/ })).toHaveProperty("disabled", true);

    fireEvent.click(screen.getByRole("checkbox", { name: /Student One/ }));
    expect(onToggleStudent).toHaveBeenCalledWith("student-1");

    rerender(<ProjectMembersModal {...props} selectedStudentIds={["student-1"]} />);
    expect(screen.getByRole("button", { name: /Add 1 to Project/ })).toHaveProperty("disabled", false);
  });
});
