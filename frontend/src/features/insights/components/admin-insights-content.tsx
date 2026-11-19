"use client";

import Link from "next/link";
import { useState } from "react";

import { useRequireAdmin } from "@/features/auth/hooks/use-require-admin";
import { HealthPanel } from "@/features/insights/components/health-panel";
import {
  PromptRegistryPanel,
  type PromptVersionSelection,
} from "@/features/insights/components/prompt-registry-panel";
import { PromptVersionDialog } from "@/features/insights/components/prompt-version-dialog";
import {
  useInsightsHealth,
  usePromptRegistry,
  usePromptVersion,
} from "@/features/insights/hooks/use-insights";
import { getErrorMessage } from "@/lib/api/client";

export function AdminInsightsContent() {
  const allowed = useRequireAdmin();
  // Wait for the admin check so non-admins never request pipeline health or the prompt registry.
  const health = useInsightsHealth(allowed);
  const registry = usePromptRegistry(allowed);
  const [selected, setSelected] = useState<PromptVersionSelection | null>(null);
  const version = usePromptVersion(
    selected?.name ?? "",
    selected?.version ?? 0,
    selected !== null,
  );
  if (!allowed) return null;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <Link href="/admin" className="text-sm text-indigo-600 hover:underline">
        ← Admin
      </Link>
      <h1 className="text-2xl font-semibold">Evaluation insights</h1>
      {health.isLoading ? (
        <p className="text-sm text-slate-500">Checking pipeline…</p>
      ) : health.error || !health.data ? (
        <p className="text-sm text-red-700">{getErrorMessage(health.error)}</p>
      ) : (
        <HealthPanel health={health.data} />
      )}
      <PromptRegistryPanel
        registry={registry.data}
        isLoading={registry.isLoading}
        isError={registry.isError}
        onOpenVersion={setSelected}
      />
      {selected && (
        <PromptVersionDialog
          name={selected.name}
          version={selected.version}
          role={selected.role}
          detail={version.data}
          isLoading={version.isLoading}
          isError={version.isError}
          onClose={() => setSelected(null)}
        />
      )}
      <p className="text-sm text-slate-500">
        Course, model and agreement comparisons arrive in Tiers 2–3.
      </p>
    </main>
  );
}