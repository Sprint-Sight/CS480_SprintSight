import { UserMinus, X } from "lucide-react";

type RosterModalProps = {
  isOpen: boolean;
  courseStudents: Array<{ id: string; email: string; full_name: string }>;
  studentForm: { email: string; full_name: string; password: string };
  onClose: () => void;
  onEnroll: () => void;
  onUnenroll: (userId: string) => void;
  setStudentForm: React.Dispatch<
    React.SetStateAction<{ email: string; full_name: string; password: string }>
  >;
};

export function RosterModal({
  isOpen,
  courseStudents,
  studentForm,
  onClose,
  onEnroll,
  onUnenroll,
  setStudentForm,
}: RosterModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto bg-slate-950/40 p-4 sm:p-6">
      <div className="mx-auto my-4 flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl sm:my-8">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Course Roster & Enrollment</h2>
            <p className="mt-0.5 text-sm text-slate-500">Create student accounts and manage enrollment.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close roster" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5 sm:px-6">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Enroll or create student</span>
              <span className="text-xs text-slate-400">Password required</span>
            </div>
            <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
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
              <input
                type="password"
                placeholder="Password"
                value={studentForm.password}
                onChange={(event) => setStudentForm((current) => ({ ...current, password: event.target.value }))}
                className="h-10 min-w-0 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 sm:col-span-2"
              />
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={onEnroll}
                className="h-10 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:ring-offset-1"
              >
                Enroll
              </button>
            </div>
          </div>

          <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {courseStudents.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                No students enrolled in this course yet.
              </div>
            ) : (
              courseStudents.map((student) => (
                <div
                  key={student.id}
                  className="flex items-center justify-between rounded-lg border border-slate-100 p-2.5 hover:bg-slate-50"
                >
                  <div>
                    <div className="text-sm font-medium text-slate-700">{student.full_name}</div>
                    <div className="text-xs text-slate-500">{student.email}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onUnenroll(student.id)}
                    className="text-slate-400 hover:text-rose-600"
                    title="Unenroll student"
                  >
                    <UserMinus className="h-4 w-4" />
                  </button>
                </div>
              ))
            )}
          </div>
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
