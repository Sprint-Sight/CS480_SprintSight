import { UserPlus, X } from "lucide-react";

type Student = { id: string; email: string; full_name: string };
type AssignedStudent = Student & { projectName: string };

type ProjectMembersModalProps = {
  isOpen: boolean;
  projectName: string;
  hasEnrolledStudents: boolean;
  availableStudents: Student[];
  assignedStudents: AssignedStudent[];
  selectedStudentId: string;
  onClose: () => void;
  onSelectStudent: (studentId: string) => void;
  onAddMember: () => void;
};

export function ProjectMembersModal({
  isOpen,
  projectName,
  hasEnrolledStudents,
  availableStudents,
  assignedStudents,
  selectedStudentId,
  onClose,
  onSelectStudent,
  onAddMember,
}: ProjectMembersModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl" role="dialog" aria-modal="true" aria-labelledby="project-members-title">
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 id="project-members-title" className="text-lg font-semibold text-slate-900">Add Project Member</h2>
            <p className="mt-0.5 text-sm text-slate-500">Choose an enrolled student for {projectName}.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close project member picker" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5">
          {availableStudents.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
              {hasEnrolledStudents && assignedStudents.length > 0
                ? "All students enrolled in this course are already assigned to a project team. They are listed below."
                : hasEnrolledStudents
                  ? "No students are currently available to add to this project."
                : "No students are enrolled in this course yet. Use the Roster button to enroll an existing student first."}
            </p>
          ) : (
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">Enrolled student</span>
              <select value={selectedStudentId} onChange={(event) => onSelectStudent(event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100">
                <option value="">Select a student</option>
                {availableStudents.map((student) => (
                  <option key={student.id} value={student.id}>{student.full_name} ({student.email})</option>
                ))}
              </select>
            </label>
          )}
          {assignedStudents.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-2 text-sm font-medium text-slate-700">
                Already assigned to a project in this course
              </h3>
              <ul className="space-y-2">
                {assignedStudents.map((student) => (
                  <li
                    key={student.id}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <p className="text-sm font-medium text-slate-800">
                      {student.full_name}
                    </p>
                    <p className="text-xs text-slate-500">{student.email}</p>
                    <p className="mt-1 text-xs text-blue-700">
                      Project group: {student.projectName}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" onClick={onClose} className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50">Cancel</button>
          <button type="button" onClick={onAddMember} disabled={!selectedStudentId} className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50">
            <UserPlus className="h-4 w-4" />
            Add to Project
          </button>
        </div>
      </div>
    </div>
  );
}