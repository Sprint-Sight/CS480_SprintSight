"use client";

import { StudentEvaluationView } from "@/features/peer-evaluation/components/student-evaluation-view";
import { InstructorEvaluationView } from "@/features/peer-evaluation/components/instructor-evaluation-view";
import { useAssessmentReport } from "@/features/assessment/hooks/use-assessment-report";
import { useStudentProjectContext } from "@/features/student/hooks/use-student-project-context";
import { usePeerTeammates } from "@/features/peer-evaluation/hooks/use-peer-teammates";

export default function PeerEvaluationPageContent() {
  const assessment = useAssessmentReport();
  const studentContext = useStudentProjectContext(assessment.role === "student");
  const { teammates } = usePeerTeammates(studentContext.project);

  const isStudent = assessment.role === "student";
  const isInstructor = assessment.role === "instructor";

  // For students, use student project context; for instructors, use assessment scope
  const scope = isStudent
    ? studentContext.project && studentContext.courses.length > 0
      ? // Find the course that matches the project's course_code
        (() => {
          const matchedCourse = studentContext.courses.find(
            (course) => course.code === studentContext.project!.course_code
          );
          return matchedCourse
            ? { courseId: matchedCourse.id, projectId: studentContext.project!.id }
            : null;
        })()
      : null
    : assessment.scope;

  if (!scope) {
    return (
      <div className="space-y-5 p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6">
          <p className="text-center text-amber-900">Unable to load scope information.</p>
        </div>
      </div>
    );
  }

  if (isStudent) {
    return (
      <div className="space-y-5 p-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Peer Evaluation</h1>
          <p className="mt-1 text-sm text-slate-500">
            Evaluate your teammates on their contributions and collaboration.
          </p>
        </div>
        <StudentEvaluationView
          courseId={scope.courseId}
          projectId={scope.projectId}
          teammates={teammates}
        />
      </div>
    );
  }

  if (isInstructor) {
    return (
      <div className="space-y-5 p-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Peer Evaluation</h1>
          <p className="mt-1 text-sm text-slate-500">
            Manage evaluation windows and review all peer evaluations in your course.
          </p>
        </div>
        <InstructorEvaluationView courseId={scope.courseId} />
      </div>
    );
  }

  return (
    <div className="space-y-5 p-8">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6">
        <p className="text-center text-amber-900">You do not have access to peer evaluations.</p>
      </div>
    </div>
  );
}
