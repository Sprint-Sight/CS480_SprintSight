"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { restoreSession } from "@/features/auth/login-api";
import { HealthPanel } from "@/features/insights/components/health-panel";
import { useInsightsHealth } from "@/features/insights/hooks/use-insights";
import { getErrorMessage } from "@/lib/api/client";

function HealthSection() {
  const health = useInsightsHealth();
  if (health.isLoading) return <p className="text-sm text-slate-500">Checking pipeline…</p>;
  if (health.error || !health.data)
    return <p className="text-sm text-red-700">{getErrorMessage(health.error)}</p>;
  return <HealthPanel health={health.data} />;
}

export function AdminInsightsContent() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    let current = true;
    void restoreSession().then((restored) => {
      if (!current) return;
      if (restored?.user?.role !== "admin") router.replace("/login");
      else setAllowed(true);
    });
    return () => {
      current = false;
    };
  }, [router]);
  if (!allowed) return null;
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <Link href="/admin" className="text-sm text-indigo-600 hover:underline">
        ← Admin
      </Link>
      <h1 className="text-2xl font-semibold">Evaluation insights</h1>
      <HealthSection />
      <p className="text-sm text-slate-500">
        Course, model and agreement comparisons arrive in Tiers 2–3.
      </p>
    </main>
  );
}
