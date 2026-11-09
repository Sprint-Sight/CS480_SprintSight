import { X } from "lucide-react";

import type { Course } from "@/features/projects/types";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

type CourseManagementModalProps = {
  isOpen: boolean;
  courses: Course[];
  editingCourse: Course | null;
  courseForm: {
    code: string;
    name: string;
    section: string;
    year: number;
    term: string;
  };
  userName: string;
  onClose: () => void;
  onSave: () => void;
  onDelete: (courseId: string) => void;
  setCourseForm: React.Dispatch<
    React.SetStateAction<{
      code: string;
      name: string;
      section: string;
      year: number;
      term: string;
    }>
  >;
  setEditingCourse: React.Dispatch<React.SetStateAction<Course | null>>;
};

/** e.g. "CS111 · Section 2 (Fall 2026)", so sections of the same course are distinguishable. */
export function formatCourseLabel(course: Pick<Course, "code" | "section" | "term" | "year">) {
  return `${course.code} · Section ${course.section} (${course.term} ${course.year})`;
}

export function CourseManagementModal({
  isOpen,
  courses,
  editingCourse,
  courseForm,
  userName,
  onClose,
  onSave,
  onDelete,
  setCourseForm,
  setEditingCourse,
}: CourseManagementModalProps) {
  if (!isOpen) return null;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        dismissOnOutsideClick={false}
        className="max-w-4xl rounded-2xl border border-slate-200 p-0"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <DialogTitle asChild>
              <h2 className="text-lg font-semibold text-slate-900">Course Management</h2>
            </DialogTitle>
            <p className="text-sm text-slate-500">
              Manage all instructor-owned courses in one place.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close course management"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Course</th>
                    <th className="px-4 py-3 font-semibold">Section</th>
                    <th className="px-4 py-3 font-semibold">Term</th>
                    <th className="px-4 py-3 font-semibold">Instructor</th>
                    <th className="px-4 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {courses.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                        No courses yet. Add your first course below.
                      </td>
                    </tr>
                  ) : (
                    courses.map((course) => {
                      // Match by id: two sections of the same course share code and name.
                      const isEditing = editingCourse?.id === course.id;
                      return (
                        <tr
                          key={course.id}
                          data-editing={isEditing || undefined}
                          className={isEditing ? "bg-blue-50" : "hover:bg-slate-50"}
                        >
                          <td
                            className={`border-l-4 px-4 py-3 ${isEditing ? "border-l-blue-600" : "border-l-transparent"}`}
                          >
                            <div className="font-semibold text-slate-900">{course.code}</div>
                            <div className="text-xs text-slate-500">{course.name}</div>
                          </td>
                          <td className="px-4 py-3 text-slate-700">{course.section}</td>
                          <td className="px-4 py-3 text-slate-700">
                            {course.term} {course.year}
                          </td>
                          <td className="px-4 py-3 text-slate-700">{userName || "Instructor"}</td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingCourse(course);
                                  setCourseForm({
                                    code: course.code,
                                    name: course.name,
                                    section: course.section,
                                    year: course.year,
                                    term: course.term,
                                  });
                                }}
                                aria-pressed={isEditing}
                                aria-label={`Edit ${formatCourseLabel(course)}`}
                                className={
                                  isEditing
                                    ? "rounded-lg border border-blue-600 bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white"
                                    : "rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                                }
                              >
                                {isEditing ? "Editing" : "Edit"}
                              </button>
                              <button
                                type="button"
                                onClick={() => onDelete(course.id)}
                                className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-100"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-500">
                {editingCourse ? `Editing ${formatCourseLabel(editingCourse)}` : "New Course"}
              </h3>
              <button
                type="button"
                onClick={() => {
                  setEditingCourse(null);
                  setCourseForm({
                    code: "",
                    name: "",
                    section: "",
                    year: new Date().getFullYear(),
                    term: "Fall",
                  });
                }}
                className="text-xs font-medium text-slate-500 hover:text-slate-700"
              >
                Reset
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="block space-y-1">
                <span className="text-sm font-medium text-slate-700">Course Code</span>
                <input
                  type="text"
                  value={courseForm.code}
                  onChange={(event) =>
                    setCourseForm((current) => ({ ...current, code: event.target.value }))
                  }
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
                  placeholder="CS480"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium text-slate-700">Section</span>
                <input
                  type="text"
                  value={courseForm.section}
                  onChange={(event) =>
                    setCourseForm((current) => ({ ...current, section: event.target.value }))
                  }
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
                  placeholder="001"
                />
              </label>

              <label className="block space-y-1 md:col-span-2">
                <span className="text-sm font-medium text-slate-700">Course Name</span>
                <input
                  type="text"
                  value={courseForm.name}
                  onChange={(event) =>
                    setCourseForm((current) => ({ ...current, name: event.target.value }))
                  }
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
                  placeholder="Software Engineering"
                />
              </label>

              <label className="block space-y-1">
                <span className="text-sm font-medium text-slate-700">Year</span>
                <input
                  type="number"
                  min={2000}
                  max={2100}
                  value={courseForm.year}
                  onChange={(event) =>
                    setCourseForm((current) => ({
                      ...current,
                      year: Number(event.target.value || new Date().getFullYear()),
                    }))
                  }
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
                />
              </label>

              <label className="block space-y-1">
                <span className="text-sm font-medium text-slate-700">Term</span>
                <select
                  value={courseForm.term}
                  onChange={(event) =>
                    setCourseForm((current) => ({ ...current, term: event.target.value }))
                  }
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
                >
                  <option value="Fall">Fall</option>
                  <option value="Spring">Spring</option>
                  <option value="Summer">Summer</option>
                </select>
              </label>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
          <button
            type="button"
            onClick={onSave}
            className="h-10 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white hover:bg-blue-800"
          >
            {editingCourse ? "Save Changes" : "Create Course"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
