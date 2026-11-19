"use client";

import type { PromptRegistry } from "@/features/insights/types";

export type PromptVersionSelection = { name: string; version: number; role: string };

function VersionCell({
  name,
  version,
  role,
  onOpen,
}: {
  name: string;
  version: number | null;
  role: string;
  onOpen: (selection: PromptVersionSelection) => void;
}) {
  if (version == null) return <>—</>;
  return (
    <button
      type="button"
      onClick={() => onOpen({ name, version, role })}
      aria-label={`View ${name} ${role} version ${version}`}
      className="rounded px-1.5 py-0.5 text-indigo-700 underline-offset-2 hover:bg-indigo-50 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
    >
      v{version}
    </button>
  );
}

export function PromptRegistryPanel({
  registry,
  isLoading,
  isError,
  onOpenVersion,
}: {
  registry: PromptRegistry | undefined;
  isLoading: boolean;
  isError: boolean;
  onOpenVersion: (selection: PromptVersionSelection) => void;
}) {
  if (isLoading) return <p className="text-sm text-slate-500">Loading prompt registry…</p>;
  if (isError || !registry)
    return <p className="text-sm text-red-700">Could not load the prompt registry.</p>;
  const { available, notice, prompts } = registry;
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-4"
      aria-label="Prompt registry"
    >
      <h2 className="mb-1 text-base font-semibold">Prompt registry</h2>
      <p className="mb-2 text-xs text-slate-500">
        {notice}
        {available && " Click a version to read its template and see what changed."}
      </p>
      {available && (
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-600">
            <tr>
              <th className="py-1 pr-3">Prompt</th>
              <th className="py-1 pr-3">production</th>
              <th className="py-1 pr-3">challenger</th>
              <th className="py-1">latest</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((p) => (
              <tr key={p.name} className="border-t border-slate-100">
                <td className="py-1 pr-3 font-mono text-xs">{p.name}</td>
                <td className="py-1 pr-3">
                  <VersionCell
                    name={p.name}
                    version={p.production}
                    role="production"
                    onOpen={onOpenVersion}
                  />
                </td>
                <td className="py-1 pr-3">
                  <VersionCell
                    name={p.name}
                    version={p.challenger}
                    role="challenger"
                    onOpen={onOpenVersion}
                  />
                </td>
                <td className="py-1">
                  <VersionCell
                    name={p.name}
                    version={p.latest}
                    role="latest"
                    onOpen={onOpenVersion}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
