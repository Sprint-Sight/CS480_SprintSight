"use client";

import { useState } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { usePromptRegistry, usePromptVersion } from "@/features/insights/hooks/use-insights";

type Selected = { name: string; version: number; role: string };

function VersionCell({
  name,
  version,
  role,
  onOpen,
}: {
  name: string;
  version: number | null;
  role: string;
  onOpen: (selected: Selected) => void;
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

export function PromptRegistryPanel() { // Shows the prompt registry in a table format
  const registry = usePromptRegistry();
  const [selected, setSelected] = useState<Selected | null>(null);
  if (registry.isLoading) return <p className="text-sm text-slate-500">Loading prompt registry…</p>;
  if (registry.error || !registry.data)
    return <p className="text-sm text-red-700">Could not load the prompt registry.</p>;
  const { available, notice, prompts } = registry.data;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4" aria-label="Prompt registry">
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
                  <VersionCell name={p.name} version={p.production} role="production" onOpen={setSelected} />
                </td>
                <td className="py-1 pr-3">
                  <VersionCell name={p.name} version={p.challenger} role="challenger" onOpen={setSelected} />
                </td>
                <td className="py-1">
                  <VersionCell name={p.name} version={p.latest} role="latest" onOpen={setSelected} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected && <PromptVersionDialog {...selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

function PromptVersionDialog({ name, version, role, onClose }: Selected & { onClose: () => void }) {
  const query = usePromptVersion(name, version, true);
  const detail = query.data;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl p-6" dismissOnOutsideClick>
        <DialogTitle className="font-mono text-base font-semibold">
          {name} v{version}
        </DialogTitle>
        <DialogDescription className="mt-1 text-sm text-slate-600">
          Opened from the <span className="font-medium">{role}</span> column
          {detail?.commitMessage && <> · {detail.commitMessage}</>}
          {detail?.createdAt && <> · created {new Date(detail.createdAt).toLocaleString()}</>}
        </DialogDescription>
        {query.isLoading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
        {query.isError && <p className="mt-4 text-sm text-red-700">Could not load this version.</p>}
        {detail?.notice && <p className="mt-4 text-sm text-amber-700">{detail.notice}</p>}
        {detail?.available && (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-1">
              <span className="text-xs text-slate-500">Aliases now:</span>
              {detail.aliases.length === 0 && <span className="text-xs text-slate-500">none</span>}
              {detail.aliases.map((alias) => (
                <span key={alias} className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                  {alias}
                </span>
              ))}
            </div>
            {detail.diff && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold">
                  Changes from v{version - 1}
                </summary>
                <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-50 p-3 text-xs">
                  {detail.diff.split("\n").map((line, index) => (
                    <div
                      key={index}
                      className={
                        line.startsWith("+")
                          ? "bg-green-100 text-green-900"
                          : line.startsWith("-")
                            ? "bg-red-100 text-red-900"
                            : ""
                      }
                    >
                      {line || " "}
                    </div>
                  ))}
                </pre>
              </details>
            )}
            {detail.template && (
              <div className="mt-4">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Prompt template</h3>
                  <button
                    type="button"
                    className="text-xs text-indigo-700 hover:underline"
                    onClick={() => void navigator.clipboard.writeText(detail.template ?? "")}
                  >
                    Copy
                  </button>
                </div>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">
                  {detail.template}
                </pre>
              </div>
            )}
          </>
        )}
        <DialogClose className="mt-4 rounded border px-3 py-1 text-sm">Close</DialogClose>
      </DialogContent>
    </Dialog>
  );
}
