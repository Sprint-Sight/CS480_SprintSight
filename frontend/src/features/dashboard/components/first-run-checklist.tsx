import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";

export type FirstRunChecklistProps = {
  hasCourse: boolean;
  hasProject: boolean;
};

type ChecklistStep = {
  label: string;
  description: string;
  done: boolean;
  href?: string;
};

// Rendered only before any Git or Jira data is synced, so the last two steps are always open here.
export function FirstRunChecklist({ hasCourse, hasProject }: FirstRunChecklistProps) {
  const steps: ChecklistStep[] = [
    { label: "Create a course", description: "Add the course your teams belong to.", done: hasCourse, href: "/projects?manageCourses=1" },
    { label: "Create a project", description: "Add one project per team.", done: hasProject, href: "/projects" },
    { label: "Connect Git and Jira, then sync", description: "Connect the repository and Jira board for the project, then run ingestion.", done: false, href: "/artifact-viewer" },
    { label: "Generate an assessment", description: "Create the sprint assessment report once data is synced.", done: false, href: "/assessment-report" },
  ];

  return (
    <section aria-labelledby="first-run-title" className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 id="first-run-title" className="text-lg font-semibold text-slate-900">Get started with SprintSight</h2>
      <p className="mt-1 text-sm text-slate-600">Complete these steps in order to see sprint data on this dashboard.</p>
      <ol className="mt-4 space-y-3">
        {steps.map((step) => (
          <li key={step.label} className="flex items-start gap-3">
            {step.done ? (
              <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
            ) : (
              <Circle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-slate-300" />
            )}
            <div>
              <p className={step.done ? "text-sm font-medium text-slate-500 line-through" : "text-sm font-medium text-slate-900"}>
                {step.href && !step.done ? <Link href={step.href} className="underline underline-offset-2 hover:text-blue-700">{step.label}</Link> : step.label}
                {step.done && <span className="sr-only"> (done)</span>}
              </p>
              <p className="text-xs text-slate-500">{step.description}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
