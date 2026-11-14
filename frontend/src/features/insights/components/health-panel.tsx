import type { InsightsHealth } from "@/features/insights/types";

function Row({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-2 text-sm last:border-0">
      <span>{label}</span>
      <span className={ok ? "text-emerald-700" : "text-red-700"}>
        {ok ? "✓" : "✗"} {value}
      </span>
    </div>
  );
}

export function HealthPanel({ health }: { health: InsightsHealth }) {
  const m = health.mlflow;
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-4"
      aria-label="Pipeline health"
    >
      <h2 className="mb-2 text-base font-semibold">Pipeline health</h2>
      <Row label="MLflow reachable" ok={m.reachable} value={m.reachable ? "Yes" : "No"} />
      <Row
        label="Client / server version"
        ok={m.versionsMatch}
        value={`${m.clientVersion ?? "?"} / ${m.serverVersion ?? "?"}`}
      />
      <Row
        label="Labels pending MLflow sync"
        ok={health.labelsPendingSync === 0}
        value={String(health.labelsPendingSync)}
      />
      <Row
        label="Overrides pending MLflow sync"
        ok={health.overridesPendingSync === 0}
        value={String(health.overridesPendingSync)}
      />
      <Row
        label="Reports awaiting judge"
        ok={health.reportsAwaitingJudge === 0}
        value={String(health.reportsAwaitingJudge)}
      />
      <Row
        label="MLflow telemetry off (backend)"
        ok={health.telemetryDisabled}
        value={health.telemetryDisabled ? "Off" : "On"}
      />
      <p className="mt-2 text-xs text-slate-500">
        Checked {new Date(health.generatedAt).toLocaleTimeString()}
      </p>
    </section>
  );
}
