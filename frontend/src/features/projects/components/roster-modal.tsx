import { UserMinus, UserPlus, X } from "lucide-react";

type Student = { id: string; email: string; full_name: string; is_active: boolean };

type RosterModalProps = {
  isOpen: boolean;
  hasSelectedCourse: boolean;
  courseStudents: Student[];
  allStudents: Student[];
  studentSearchTerm: string;
  isLoadingStudents: boolean;
  studentDirectoryError: string;
  studentForm: { email: string; full_name: string };
  onClose: () => void;
  onCreateStudent: () => void;
  onEnrollExisting: (userId: string) => void;
  onUnenroll: (userId: string) => void;
  onRefreshStudents: () => void;
  setStudentSearchTerm: (value: string) => void;
  setStudentForm: React.Dispatch<
    React.SetStateAction<{ email: string; full_name: string }>
  >;
};

export function RosterModal({
  isOpen,
  hasSelectedCourse,
  courseStudents,
  allStudents,
  studentSearchTerm,
  isLoadingStudents,
  studentDirectoryError,
  studentForm,
  onClose,
  onCreateStudent,
  onEnrollExisting,
  onUnenroll,
  onRefreshStudents,
  setStudentSearchTerm,
  setStudentForm,
}: RosterModalProps) {
  if (!isOpen) return null;
  const enrolledIds = new Set(courseStudents.map((student) => student.id));
  const availableStudents = allStudents.filter((student) => {
    const search = studentSearchTerm.trim().toLowerCase();
    return (
      !enrolledIds.has(student.id) &&
      (!search ||
        student.full_name.toLowerCase().includes(search) ||
        student.email.toLowerCase().includes(search))
    );
  });

  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto bg-slate-950/40 p-4 sm:p-6">
      <div className="mx-auto my-4 flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl sm:my-8">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Students & Course Roster</h2>
            <p className="mt-0.5 text-sm text-slate-500">
              Enroll existing students, or create new student accounts without a course.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close roster" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5 sm:px-6">
          {/* --- All students (existing accounts) --- */}
          <section>
            <div className="mb-2">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-800">
                  All students ({allStudents.length})
                </h3>
                <button
                  type="button"
                  onClick={onRefreshStudents}
                  disabled={isLoadingStudents}
                  className="text-xs font-medium text-blue-700 hover:text-blue-800 disabled:text-slate-400"
                >
                  {isLoadingStudents ? "Loading..." : "Refresh"}
                </button>
              </div>
              <p className="text-xs text-slate-500">
                {hasSelectedCourse
                  ? "Click a student below to enroll them in the selected course."
                  : "Select a course above to enable enrollment."}
              </p>
            </div>
            <input
              type="search"
              placeholder="Search students by name or email"
              value={studentSearchTerm}
              onChange={(event) => setStudentSearchTerm(event.target.value)}
              className="mb-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
              {studentDirectoryError ? (
                <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                  {studentDirectoryError}
                </div>
              ) : isLoadingStudents && allStudents.length === 0 ? (
                <div className="p-4 text-sm text-slate-500">Loading student accounts...</div>
              ) : availableStudents.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                  {allStudents.length === 0
                    ? "No student accounts found in the system."
                    : "No unenrolled students match your search."}
                </div>
              ) : (
                availableStudents.map((student) => {
                  const canEnroll = hasSelectedCourse && student.is_active;
                  return (
                    <div
                      key={student.id}
                      className="flex items-center justify-between rounded-lg border border-slate-100 p-2.5 hover:bg-blue-50 cursor-pointer transition-colors"
                      role="button"
                      tabIndex={0}
                      onClick={() => canEnroll && onEnrollExisting(student.id)}
                      onKeyDown={(e) => e.key === "Enter" && canEnroll && onEnrollExisting(student.id)}
                      aria-label={`Enroll ${student.full_name} in the course`}
                    >
                      <div>
                        <div className="text-sm font-medium text-slate-900">{student.full_name}</div>
                        <div className="text-xs text-slate-500">{student.email}</div>
                        {!student.is_active && (
                          <div className="text-xs text-rose-600">Account disabled</div>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (canEnroll) onEnrollExisting(student.id);
                        }}
                        disabled={!canEnroll}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:text-slate-400"
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                        Enroll
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          {/* --- Create new student account (secondary) --- */}
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Create new student account
              </span>
              <span className="text-xs text-slate-400">No course enrollment yet</span>
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
              <input
                type="text"
                placeholder="Student Name"
                value={studentForm.full_name}
                onChange={(event) => setStudentForm((current) => ({ ...current, full_name: event.target.value }))}
                className="h-10 min-w-0 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
              <input
                type="email"
                placeholder="Student Email"
                value={studentForm.email}
                onChange={(event) => setStudentForm((current) => ({ ...current, email: event.target.value }))}
                className="h-10 min-w-0 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={onCreateStudent}
                className="h-10 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:ring-offset-1"
              >
                Create Student & Email Setup Link
              </button>
            </div>
          </div>

          {/* --- Enrolled in this course --- */}
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-800">
              Enrolled in this course ({courseStudents.length})
            </h3>
            <div className="max-h-52 space-y-2 overflow-y-auto pr-1">
            {courseStudents.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                {hasSelectedCourse
                  ? "No students enrolled in this course yet."
                  : "Select a course above to view or manage its roster."}
              </div>
            ) : (
              courseStudents.map((student) => (
                <div
                  key={student.id}
                  className="flex items-center justify-between rounded-lg border border-slate-100 p-2.5 hover:bg-slate-50"
                >
                  <div>
                    <div className="text-sm font-medium text-slate-900">{student.full_name}</div>
                    <div className="text-xs text-slate-500">{student.email}</div>
                    {!student.is_active && <div className="text-xs text-rose-600">Account disabled</div>}
                  </div>
                  <button
                    type="button"
                    onClick={() => onUnenroll(student.id)}
                    disabled={!hasSelectedCourse}
                    className="text-slate-400 hover:text-rose-600"
                    title="Unenroll student"
                  >
                    <UserMinus className="h-4 w-4" />
                  </button>
                </div>
              ))
            )}
            </div>
          </section>
        </div>

        <div className="flex justify-end border-t border-slate-200 px-5 py-4 sm:px-6">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
