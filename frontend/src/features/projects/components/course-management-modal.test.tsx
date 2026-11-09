import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  CourseManagementModal,
  formatCourseLabel,
} from "@/features/projects/components/course-management-modal";
import type { Course } from "@/features/projects/types";

const sectionOne: Course = {
  id: "course-1",
  code: "CS111",
  name: "Intro to Programming",
  section: "1",
  year: 2026,
  term: "Fall",
};
const sectionTwo: Course = { ...sectionOne, id: "course-2", section: "2" };

const emptyForm = { code: "", name: "", section: "", year: 2026, term: "Fall" };

/** Holds the real editing state, like the projects page container does. */
function Harness({ initialEditing = null }: { initialEditing?: Course | null }) {
  const [editingCourse, setEditingCourse] = useState<Course | null>(initialEditing);
  const [courseForm, setCourseForm] = useState(emptyForm);
  return (
    <CourseManagementModal
      isOpen
      courses={[sectionOne, sectionTwo]}
      editingCourse={editingCourse}
      courseForm={courseForm}
      userName="Prof"
      onClose={vi.fn()}
      onSave={vi.fn()}
      onDelete={vi.fn()}
      setCourseForm={setCourseForm}
      setEditingCourse={setEditingCourse}
    />
  );
}

function rowFor(course: Course) {
  const editButton = screen.getByRole("button", { name: `Edit ${formatCourseLabel(course)}` });
  const row = editButton.closest("tr");
  if (!row) throw new Error("row not found");
  return { row, editButton };
}

describe("CourseManagementModal editing highlight", () => {
  it("highlights nothing and shows 'New Course' when no course is being edited", () => {
    render(<Harness />);

    expect(rowFor(sectionOne).row.dataset.editing).toBeUndefined();
    expect(rowFor(sectionTwo).row.dataset.editing).toBeUndefined();
    expect(screen.getByRole("heading", { name: "New Course" })).toBeTruthy();
  });

  it("highlights only the clicked section when two sections share a course code", () => {
    render(<Harness />);

    fireEvent.click(rowFor(sectionTwo).editButton);

    const two = rowFor(sectionTwo);
    expect(two.row.dataset.editing).toBe("true");
    expect(two.editButton.getAttribute("aria-pressed")).toBe("true");
    expect(within(two.row).getByText("Editing")).toBeTruthy();

    const one = rowFor(sectionOne);
    expect(one.row.dataset.editing).toBeUndefined();
    expect(one.editButton.getAttribute("aria-pressed")).toBe("false");
    expect(within(one.row).getByText("Edit")).toBeTruthy();
  });

  it("names the edited section in the form heading", () => {
    render(<Harness />);

    fireEvent.click(rowFor(sectionTwo).editButton);
    expect(
      screen.getByRole("heading", { name: "Editing CS111 · Section 2 (Fall 2026)" }),
    ).toBeTruthy();

    fireEvent.click(rowFor(sectionOne).editButton);
    expect(
      screen.getByRole("heading", { name: "Editing CS111 · Section 1 (Fall 2026)" }),
    ).toBeTruthy();
    expect(rowFor(sectionTwo).row.dataset.editing).toBeUndefined();
  });

  it("clears the highlight and heading on Reset", () => {
    render(<Harness initialEditing={sectionOne} />);
    expect(rowFor(sectionOne).row.dataset.editing).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    expect(rowFor(sectionOne).row.dataset.editing).toBeUndefined();
    expect(screen.getByRole("heading", { name: "New Course" })).toBeTruthy();
  });
});
