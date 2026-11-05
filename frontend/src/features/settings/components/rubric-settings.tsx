"use client";

import { useId } from "react";

import type { CourseOption } from "@/features/settings/settings-api";
import type { RubricDimensionId, RubricWeight } from "@/features/settings/types";

type RubricSettingsProps = {
  rubric: RubricWeight[];
  totalWeight: number;
  isValidTotal: boolean;
  hasUnsavedChanges: boolean;
  courses: CourseOption[];
  selectedCourseId: string;
  isDisabled: boolean;
  isLoading: boolean;
  error: string;
  onCourseChange: (courseId: string) => void;
  onChange: (id: RubricDimensionId, value: number) => void;
};

function formatPercent(value: number) {
  return `${Math.round(value * 10) / 10}%`;
}

export function RubricSettings({
  rubric,
  totalWeight,
  isValidTotal,
  hasUnsavedChanges,
  courses,
  selectedCourseId,
  isDisabled,
  isLoading,
  error,
  onCourseChange,
  onChange,
}: RubricSettingsProps) {
  const baseId = useId();
  const courseSelectId = `${baseId}-course`;

  return (
    <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xl font-semibold text-blue-950">Grading Rubric Configuration</h2>

      <div className="mt-4 space-y-1">
        <label htmlFor={courseSelectId} className="text-sm font-medium text-slate-700">
          Course
        </label>
        <select
          id={courseSelectId}
          value={selectedCourseId}
          onChange={(event) => onCourseChange(event.target.value)}
          disabled={isDisabled || courses.length === 0}
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 disabled:opacity-60"
        >
          {courses.length === 0 && <option value="">No courses available</option>}
          {courses.map((course) => (
            <option key={course.id} value={course.id}>
              {course.code} · {course.section} · {course.term} {course.year}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-500">
          Weights apply to every assessment generated for this course.
        </p>
      </div>

      {isLoading && (
        <p role="status" className="mt-3 text-sm text-slate-500">
          Loading rubric weights...
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-600">
          {error}
        </p>
      )}

      <div className="mt-4 w-full min-w-0 space-y-3">
        {rubric.map((item) => {
          const sliderId = `${baseId}-${item.id}`;
          return (
            <div key={item.id}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <label htmlFor={sliderId} className="font-medium text-slate-700">
                  {item.label}
                </label>
                <span className="font-semibold text-blue-900">{formatPercent(item.value)}</span>
              </div>
              <input
                id={sliderId}
                type="range"
                min={0}
                max={100}
                step={1}
                value={item.value}
                disabled={isDisabled}
                onChange={(event) => onChange(item.id, Number(event.target.value))}
                className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-[#2F5B85] disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>
          );
        })}
      </div>

      <p
        role="status"
        className={`mt-4 text-sm font-semibold ${isValidTotal ? "text-emerald-600" : "text-amber-600"}`}
      >
        Total Weight: {formatPercent(totalWeight)}
        {!isValidTotal && " — must add up to 100% before saving"}
      </p>
      {hasUnsavedChanges && isValidTotal && (
        <p className="mt-1 text-xs text-slate-500">
          Unsaved rubric changes. Click Save Settings to apply them.
        </p>
      )}
    </section>
  );
}
