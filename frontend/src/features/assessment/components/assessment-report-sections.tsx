"use client";

import { useEffect, useRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import type { RubricScore } from "@/features/assessment/types";

type AssessmentFeedbackReport = {
  rubricScores: RubricScore[];
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
};

type AssessmentFeedbackSectionsProps = {
  report: AssessmentFeedbackReport;
  editMode?: boolean;
  onRubricScoreChange?: (categoryKey: string, patch: Partial<RubricScore>) => void;
  onSummaryChange?: (field: "strengths" | "weaknesses" | "recommendations", value: string) => void;
};

function scoreBarColor(score: number) {
  if (score >= 85) return "bg-[#2F5B85]";
  if (score >= 75) return "bg-[#4F89B3]";
  return "bg-[#78B5D9]";
}

function resizeTextarea(textarea: HTMLTextAreaElement) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

function AutoResizeTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { className, onChange, ...textareaProps } = props;

  useEffect(() => {
    if (textareaRef.current) resizeTextarea(textareaRef.current);
  }, [textareaProps.value]);

  return (
    <textarea
      {...textareaProps}
      ref={textareaRef}
      onChange={(event) => {
        resizeTextarea(event.currentTarget);
        onChange?.(event);
      }}
      className={className}
      style={{ ...textareaProps.style, overflowY: "hidden" }}
    />
  );
}

export function CircularScore({ score }: { score: number }) {
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  return (
    <div className="relative mx-auto flex h-40 w-40 items-center justify-center">
      <svg width="160" height="160" viewBox="0 0 160 160" className="-rotate-90">
        <circle cx="80" cy="80" r={radius} stroke="#dbe6f2" strokeWidth="8" fill="none" />
        <circle
          cx="80"
          cy="80"
          r={radius}
          stroke="#2F5B85"
          strokeWidth="8"
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${progress} ${circumference - progress}`}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-5xl font-bold text-blue-950">{score}</div>
      </div>
    </div>
  );
}

export function AssessmentScoreVisuals({ report }: { report: { overallScore: number; rubricScores: RubricScore[] } }) {
  const radarData = report.rubricScores.map((item) => ({ category: item.category, score: item.score }));
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-500">Overall Sprint Score</h2>
        <CircularScore score={report.overallScore} />
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold text-blue-950">Rubric Score Breakdown</h2>
        <div className="mt-3 h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData}>
              <PolarGrid stroke="#dbe6f2" />
              <PolarAngleAxis dataKey="category" tick={{ fill: "#64748b", fontSize: 12 }} />
              <Radar dataKey="score" stroke="#2F5B85" fill="#4F89B3" fillOpacity={0.35} />
              <Tooltip formatter={(value: number) => `${value}%`} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}

export function AssessmentFeedbackSections({
  report,
  editMode = false,
  onRubricScoreChange,
  onSummaryChange,
}: AssessmentFeedbackSectionsProps) {
  const groups: Array<[string, string[], string]> = [
    ["Strengths", report.strengths, "emerald"],
    ["Weaknesses", report.weaknesses, "rose"],
    ["Recommendations", report.recommendations, "blue"],
  ];

  return (
    <>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold text-blue-950">Category Scores and Justifications</h2>
        {editMode && (
          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Edit any rubric category below. Evidence citations remain read-only and are preserved when saving.
          </p>
        )}
        <div className="mt-4 space-y-3">
          {report.rubricScores.map((item) => {
            const categoryKey = item.categoryKey || item.category;
            return (
              <article key={categoryKey} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-900">{item.category}</h3>
                  {!editMode && <span className="text-sm font-bold text-blue-900">{item.score}%</span>}
                </div>
                {editMode ? (
                  <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
                    <label className="text-xs font-semibold text-slate-600">
                      Score (%)
                      <input
                        aria-label={`${item.category} score`}
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={item.score}
                        onChange={(event) => {
                          const value = event.currentTarget.value;
                          const score = Number(value);
                          if (value !== "" && Number.isFinite(score) && score >= 0 && score <= 100) {
                            onRubricScoreChange?.(categoryKey, { score });
                          }
                        }}
                        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900"
                      />
                    </label>
                    <label className="text-xs font-semibold text-slate-600">
                      Feedback
                      <AutoResizeTextarea
                        aria-label={`${item.category} feedback`}
                        value={item.justification}
                        onChange={(event) => onRubricScoreChange?.(categoryKey, { justification: event.currentTarget.value })}
                        rows={1}
                        maxLength={500}
                        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-700"
                      />
                    </label>
                  </div>
                ) : (
                  <>
                    <div className="h-2 rounded-full bg-slate-200">
                      <div className={`h-full rounded-full ${scoreBarColor(item.score)}`} style={{ width: `${item.score}%` }} />
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{item.justification}</p>
                  </>
                )}
                {item.evidenceCitations && item.evidenceCitations.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
                    {item.evidenceCitations.map((citation) => <li key={citation}>Evidence: {citation}</li>)}
                  </ul>
                )}
              </article>
            );
          })}
        </div>
      </section>
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {groups.map(([title, items, tone]) => {
          const field = title.toLowerCase() as "strengths" | "weaknesses" | "recommendations";
          return (
          <article key={title} className={`rounded-2xl border border-${tone}-200 bg-${tone}-50/40 p-5 shadow-sm`}>
            <h2 className={`text-2xl font-semibold text-${tone}-700`}>{title}</h2>
            {editMode ? (
              <AutoResizeTextarea
                  aria-label={title}
                  value={items.join("\n")}
                  onChange={(event) => onSummaryChange?.(field, event.currentTarget.value)}
                  rows={1}
                  className="mt-3 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
                />
            ) : (
              <ul className="mt-3 space-y-2 text-sm text-slate-700">
                {items.map((item, index) => (
                  <li key={`${title}-${index}`} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-current" />
                    <span>{title === "Recommendations" ? `${index + 1}. ${item}` : item}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>
          );
        })}
      </section>
    </>
  );
}
