import type { LlmModelOption } from "@/features/settings/types";

type Props = {
  models: LlmModelOption[];
  selectedModelId: string;
  isDisabled: boolean;
  onModelChange: (id: string) => void;
};

export function LlmSettings({
  models,
  selectedModelId,
  isDisabled,
  onModelChange,
}: Props) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xl font-semibold text-blue-950">LLM Model Selection</h2>
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
        {models.map((model) => (
          <label
            key={model.id}
            className={`cursor-pointer rounded-xl border px-3 py-2 transition ${
              selectedModelId === model.id
                ? "border-blue-300 bg-blue-50"
                : "border-slate-200 bg-white hover:bg-slate-50"
            }`}
          >
            <div className="flex items-start gap-2">
              <input
                type="radio"
                name="llm-model"
                checked={selectedModelId === model.id}
                disabled={isDisabled}
                onChange={() => onModelChange(model.id)}
                className="mt-1"
              />
              <div>
                <p className="text-sm font-semibold text-blue-950">
                  {model.provider} {model.model}
                </p>
                <p className="text-xs text-slate-500">{model.description}</p>
              </div>
            </div>
          </label>
        ))}
      </div>
    </section>
  );
}
