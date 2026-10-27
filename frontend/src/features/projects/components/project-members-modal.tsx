import { Loader2, UserPlus, X } from "lucide-react";

type Student = { id: string; email: string; full_name: string };
type AssignedStudent = Student & { projectName: string };

type ProjectMembersModalProps = {
  isOpen: boolean;
  projectName: string;
  hasEnrolledStudents: boolean;
  availableStudents: Student[];
  assignedStudents: AssignedStudent[];
  selectedStudentIds: string[];
  isAddingMembers: boolean;
  onClose: () => void;
  onToggleStudent: (studentId: string) => void;
  onAddMember: () => void;
};

export function ProjectMembersModal({
  isOpen,
  projectName,
  hasEnrolledStudents,
  availableStudents,
  assignedStudents,
  selectedStudentIds,
  isAddingMembers,
  onClose,
  onToggleStudent,
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
          <button type="button" onClick={onClose} disabled={isAddingMembers} aria-label="Close project member picker" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50">
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
            <fieldset disabled={isAddingMembers} className="space-y-2">
              <legend className="mb-2 text-sm font-medium text-slate-700">
                Select enrolled students
              </legend>
              <ul className="max-h-64 space-y-2 overflow-y-auto">
                {availableStudents.map((student) => (
                  <li key={student.id}>
                    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 px-3 py-2.5 hover:bg-slate-50 has-[:checked]:border-blue-300 has-[:checked]:bg-blue-50">
                      <input
                        type="checkbox"
                        checked={selectedStudentIds.includes(student.id)}
                        onChange={() => onToggleStudent(student.id)}
                        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500"
                      />
                      <span>
                        <span className="block text-sm font-medium text-slate-900">
                          {student.full_name}
                        </span>
                        <span className="block text-xs text-slate-500">{student.email}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-slate-500" aria-live="polite">
                {selectedStudentIds.length} student{selectedStudentIds.length === 1 ? "" : "s"} selected
              </p>
            </fieldset>
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
          <button type="button" onClick={onClose} disabled={isAddingMembers} className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">Cancel</button>
          <button type="button" onClick={onAddMember} disabled={selectedStudentIds.length === 0 || isAddingMembers} className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50">
            {isAddingMembers ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            {isAddingMembers ? "Adding..." : `Add ${selectedStudentIds.length || ""} to Project`}
          </button>
        </div>
      </div>
    </div>
  );
}