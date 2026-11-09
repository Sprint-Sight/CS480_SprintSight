import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { RosterModal } from "@/features/projects/components/roster-modal";

const enrolledHere = {
  id: "s1",
  email: "here@example.com",
  full_name: "Enrolled Here",
  is_active: true,
};
const inSibling = {
  id: "s2",
  email: "sibling@example.com",
  full_name: "In Sibling",
  is_active: true,
};
const notEnrolled = {
  id: "s3",
  email: "free@example.com",
  full_name: "Not Enrolled",
  is_active: true,
};

type RosterProps = ComponentProps<typeof RosterModal>;

function renderRoster(overrides: Partial<RosterProps> = {}) {
  const props: RosterProps = {
    isOpen: true,
    hasSelectedCourse: true,
    courseStudents: [enrolledHere],
    allStudents: [enrolledHere, inSibling, notEnrolled],
    otherSectionEnrollments: { s2: "CS111 · Section 1 (Fall 2026)" },
    isRosterReady: true,
    rosterError: "",
    courseCode: "CS111",
    studentSearchTerm: "",
    isLoadingStudents: false,
    studentDirectoryError: "",
    studentForm: { email: "", full_name: "", password: "" },
    onClose: vi.fn(),
    onCreateStudent: vi.fn(),
    onEnrollExisting: vi.fn(),
    onUnenroll: vi.fn(),
    onRefreshStudents: vi.fn(),
    setStudentSearchTerm: vi.fn(),
    setStudentForm: vi.fn(),
    ...overrides,
  };
  render(<RosterModal {...props} />);
  return props;
}

const enrollButton = (name: string) =>
  screen.queryByRole("button", { name: `Enroll ${name} in the course` });

describe("RosterModal enroll list", () => {
  it("leaves out students enrolled in this section or another section", () => {
    renderRoster();

    expect(enrollButton("Enrolled Here")).toBeNull();
    expect(enrollButton("In Sibling")).toBeNull();
    expect(screen.queryByText("sibling@example.com")).toBeNull();
    // This section's student is still listed under the enrolled roster, with Unenroll.
    expect(screen.getByText("here@example.com")).toBeTruthy();
    expect(screen.getByText("Available to enroll (1)")).toBeTruthy();
  });

  it("explains how many students are hidden and why", () => {
    renderRoster();

    expect(
      screen.getByText("1 student is hidden because they're enrolled in another section of CS111."),
    ).toBeTruthy();
  });

  it("pluralizes the hidden note", () => {
    const another = { ...inSibling, id: "s4", email: "another@example.com", full_name: "Another" };
    renderRoster({
      allStudents: [enrolledHere, inSibling, another, notEnrolled],
      otherSectionEnrollments: {
        s2: "CS111 · Section 1 (Fall 2026)",
        s4: "CS111 · Section 3 (Fall 2026)",
      },
    });

    expect(
      screen.getByText(
        "2 students are hidden because they're enrolled in another section of CS111.",
      ),
    ).toBeTruthy();
  });

  it("lets an unenrolled student be enrolled", () => {
    const props = renderRoster();

    const button = enrollButton("Not Enrolled") as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(props.onEnrollExisting).toHaveBeenCalledWith("s3");
  });

  it("disables Enroll and explains when enrollments could not be loaded", () => {
    const props = renderRoster({
      isRosterReady: false,
      rosterError: "Something went wrong on our side.",
      otherSectionEnrollments: {},
      courseStudents: [],
    });

    expect(screen.getByRole("alert").textContent).toContain(
      "Couldn't check who is already enrolled: Something went wrong on our side.",
    );
    const button = enrollButton("Not Enrolled") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(props.onEnrollExisting).not.toHaveBeenCalled();
  });

  it("says everyone is enrolled when nobody is left to enroll", () => {
    renderRoster({ allStudents: [enrolledHere, inSibling] });

    expect(
      screen.getByText(
        "Every student is already enrolled in this course or another section of it.",
      ),
    ).toBeTruthy();
  });

  it("distinguishes 'no search match' from 'nobody left'", () => {
    renderRoster({ studentSearchTerm: "zzz" });

    expect(screen.getByText("No available students match your search.")).toBeTruthy();
  });
});
