"use client";

type AssessmentProgressBarProps = {
  message: string;
  progress: number;
};

export function AssessmentProgressBar({ message, progress }: AssessmentProgressBarProps) {
  const value = Math.min(100, Math.max(0, Math.round(progress)));

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">
      <div className="flex justify-between gap-3">
        <span aria-live="polite">{message}</span>
        <span aria-hidden="true">{value}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Assessment progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value}%`}
        className="mt-2 h-2 overflow-hidden rounded-full bg-blue-100"
      >
        <div className="h-full rounded-full bg-blue-800 transition-[width]" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
