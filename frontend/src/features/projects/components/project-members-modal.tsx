import { UserPlus, X } from "lucide-react";

type Student = { id: string; email: string; full_name: string };

type ProjectMembersModalProps = {
  isOpen: boolean;
  projectName: string;
  availableStudents: Student[];
  selectedStudentId: string;
  onClose: () => void;
  onSelectStudent: (studentId: string) => void;
  onAddMember: () => void;
};

export function ProjectMembersModal({
  isOpen,
  projectName,
  availableStudents,
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
              Every enrolled student is already assigned to a project in this course, or the course roster is empty.
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