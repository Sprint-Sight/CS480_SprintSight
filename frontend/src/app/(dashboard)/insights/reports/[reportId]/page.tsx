import { Suspense } from "react";

import { ReportInsightsContent } from "@/features/insights/components/report-insights-content";

type Props = { params: Promise<{ reportId: string }> };

// Next 15: dynamic route params are a Promise. useSearchParams needs the Suspense boundary.
export default async function ReportInsightsPage({ params }: Props) {
  const { reportId } = await params;
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <ReportInsightsContent reportId={reportId} />
    </Suspense>
  );
}
