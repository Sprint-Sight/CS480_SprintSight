"use client";

export function PromptAliases({ aliases, emptyLabel }: { aliases: string[]; emptyLabel?: string }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1">
      <span className="text-xs text-slate-500">Aliases now:</span>
      {aliases.length === 0 && emptyLabel && (
        <span className="text-xs text-slate-500">{emptyLabel}</span>
      )}
      {aliases.map((alias) => (
        <span key={alias} className="rounded bg-slate-100 px-2 py-0.5 text-xs">
          {alias}
        </span>
      ))}
    </div>
  );
}

export function PromptTemplateBlock({ template }: { template: string }) {
  return (
    <div className="mt-4">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Prompt template</h3>
        <button
          type="button"
          className="text-xs text-indigo-700 hover:underline"
          onClick={() => void navigator.clipboard.writeText(template)}
        >
          Copy
        </button>
      </div>
      <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">
        {template}
      </pre>
    </div>
  );
}
