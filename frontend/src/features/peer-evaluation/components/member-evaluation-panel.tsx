"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Star } from "lucide-react";
import type { MemberPeerEvaluationDetail } from "@/features/peer-evaluation/peer-evaluation-api";

type MemberOption = {
  id: string;
  name: string;
};

type MemberEvaluationPanelProps = {
  projectId: string | null;
  members: MemberOption[];
  detail: MemberPeerEvaluationDetail | null;
  isLoading: boolean;
  onSelectMember: (projectId: string, memberId: string) => void;
};

export function MemberEvaluationPanel({
  projectId,
  members,
  detail,
  isLoading,
  onSelectMember,
}: MemberEvaluationPanelProps) {
  const [selectedMemberId, setSelectedMemberId] = useState<string>("");

  const uniqueMembers = useMemo(() => {
    const seen = new Set<string>();
    return members.filter((member) => {
      if (seen.has(member.id)) return false;
      seen.add(member.id);
      return true;
    });
  }, [members]);

  useEffect(() => {
    setSelectedMemberId("");
  }, [projectId]);

  if (!projectId || uniqueMembers.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">Member evaluations</h3>
        <p className="mt-1 text-sm text-slate-600">
          Scores and remarks from teammates, plus course-wide outlier stats.
        </p>
      </div>

      <select
        value={selectedMemberId}
        onChange={(event) => {
          const memberId = event.target.value;
          setSelectedMemberId(memberId);
          if (memberId) {
            onSelectMember(projectId, memberId);
          }
        }}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
      >
        <option value="">Select a member</option>
        {uniqueMembers.map((member) => (
          <option key={member.id} value={member.id}>
            {member.name}
          </option>
        ))}
      </select>

      {isLoading && selectedMemberId && (
        <p className="text-sm text-slate-600">Loading member evaluations...</p>
      )}

      {detail && detail.member_id === selectedMemberId && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium uppercase text-slate-600">Total score</p>
              <p className="mt-2 text-2xl font-bold text-slate-900">{detail.total_score}</p>
              <p className="mt-1 text-xs text-slate-500">
                Average {detail.average_score ?? "—"} from {detail.evaluation_count} teammate
                {detail.evaluation_count === 1 ? "" : "s"}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium uppercase text-slate-600">Course average total</p>
              <p className="mt-2 text-2xl font-bold text-slate-900">
                {detail.course_average_total ?? "—"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                SD {detail.course_total_score_std_dev ?? "—"} · {detail.students_below_course_average} of{" "}
                {detail.enrolled_student_count} enrolled below average
              </p>
            </div>
            <div
              className={`rounded-lg border p-4 ${
                detail.is_total_outlier
                  ? "border-amber-200 bg-amber-50"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <p className="text-xs font-medium uppercase text-slate-600">Outlier (1 SD)</p>
              <p className="mt-2 text-2xl font-bold text-slate-900">
                {detail.is_total_outlier
                  ? detail.outlier_direction === "low"
                    ? "Low"
                    : "High"
                  : "No"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                z-score {detail.total_z_score ?? "—"}
              </p>
            </div>
          </div>

          {detail.is_total_outlier && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                This member&apos;s total is at least one standard deviation{" "}
                {detail.outlier_direction} compared with other enrolled students who received
                evaluations.
              </p>
            </div>
          )}

          <ul className="space-y-2">
            {detail.evaluations.map((evaluation) => (
              <li
                key={evaluation.evaluation_id}
                className="rounded-lg border border-slate-200 px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-slate-900">{evaluation.rater_full_name}</p>
                  <div className="flex items-center gap-2">
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <Star
                          key={star}
                          className={`h-4 w-4 ${
                            star <= evaluation.score
                              ? "fill-yellow-400 text-yellow-400"
                              : "text-slate-300"
                          }`}
                        />
                      ))}
                    </div>
                    {evaluation.is_score_outlier && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                        Score outlier
                      </span>
                    )}
                  </div>
                </div>
                <p className="mt-2 text-sm text-slate-700">
                  {evaluation.remarks || "No remarks."}
                </p>

              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
