"use client";

import { BrainCircuit, Cable, RefreshCw, Save, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { INITIAL_SETTINGS } from "@/features/settings/data";
import type { ApiConnectionSettings, RubricWeight } from "@/features/settings/types";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function SettingsPageContent() {
  const router = useRouter();
  const [isAuthorized, setIsAuthorized] = useState(false);

  const [rubric, setRubric] = useState(INITIAL_SETTINGS.rubric);
  const [selectedModelId, setSelectedModelId] = useState(INITIAL_SETTINGS.selectedModelId);
  const [llmParams, setLlmParams] = useState(INITIAL_SETTINGS.llmParams);
  const [apiConnections, setApiConnections] = useState<ApiConnectionSettings>(INITIAL_SETTINGS.apiConnections);
  const [saveMessage, setSaveMessage] = useState("");

  const totalWeight = useMemo(() => rubric.reduce((sum, item) => sum + item.value, 0), [rubric]);

  useEffect(() => {
    const role = sessionStorage.getItem("sprintsight-auth-role");
    if (role === "student") {
      router.replace("/");
    } else {
      setIsAuthorized(true);
    }
  }, [router]);

  function updateRubricWeight(id: RubricWeight["id"], value: number) {
    setRubric((prev) => prev.map((item) => (item.id === id ? { ...item, value: clamp(value, 0, 100) } : item)));
  }

  function updateApiField<K extends keyof ApiConnectionSettings>(field: K, value: ApiConnectionSettings[K]) {
    setApiConnections((prev) => ({ ...prev, [field]: value }));
  }

  function handleTestConnection(target: "github" | "jira") {
    if (target === "github") {
      updateApiField("githubConnected", Boolean(apiConnections.githubToken.trim()));
      return;
    }
    const jiraReady = Boolean(apiConnections.jiraToken.trim()) && Boolean(apiConnections.jiraDomain.trim());
    updateApiField("jiraConnected", jiraReady);
  }

  function handleSave() {
    setSaveMessage(`Settings saved at ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`);
  }

  // Do not render the page at all until we confirm they are not a student
  if (!isAuthorized) {
    return null; 
  }

  return (
    <div className="space-y-5 p-8">
      <div>
        <h1 className="text-4xl font-bold tracking-tight text-blue-950">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Configure grading rubrics, AI models, and integrations</p>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="inline-flex items-center gap-2 text-xl font-semibold text-blue-950">
          <SlidersHorizontal className="h-5 w-5" />
          Grading Rubric Configuration
        </h2>

        <div className="mt-4 max-w-xl space-y-3">
          {rubric.map((item) => (
            <div key={item.id}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-medium text-slate-700">{item.label}</span>
                <span className="font-semibold text-blue-900">{item.value}%</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={item.value}
                onChange={(event) => updateRubricWeight(item.id, Number(event.target.value))}
                className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-[#2F5B85]"
              />
            </div>
          ))}
        </div>

        <p className={`mt-4 text-sm font-semibold ${totalWeight === 100 ? "text-emerald-600" : "text-amber-600"}`}>
          Total Weight: {totalWeight}%
        </p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="inline-flex items-center gap-2 text-xl font-semibold text-blue-950">
          <BrainCircuit className="h-5 w-5" />
          LLM Model Selection
        </h2>

        <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
          {INITIAL_SETTINGS.llmModels.map((model) => {
            const selected = selectedModelId === model.id;
            return (
              <label
                key={model.id}
                className={`cursor-pointer rounded-xl border px-3 py-2 transition ${selected ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}
              >
                <div className="flex items-start gap-2">
                  <input
                    type="radio"
                    name="llm-model"
                    checked={selected}
                    onChange={() => setSelectedModelId(model.id)}
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
            );
          })}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-700">Temperature</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={llmParams.temperature}
              onChange={(event) =>
                setLlmParams((prev) => ({ ...prev, temperature: clamp(Number(event.target.value), 0, 1) }))
              }
              className="h-10 w-full rounded-lg border border-slate-200 px-3"
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-700">Top P</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={llmParams.topP}
              onChange={(event) =>
                setLlmParams((prev) => ({ ...prev, topP: clamp(Number(event.target.value), 0, 1) }))
              }
              className="h-10 w-full rounded-lg border border-slate-200 px-3"
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-medium text-slate-700">Max Tokens</span>
            <input
              type="number"
              min={256}
              max={8192}
              step={64}
              value={llmParams.maxTokens}
              onChange={(event) =>
                setLlmParams((prev) => ({ ...prev, maxTokens: clamp(Number(event.target.value), 256, 8192) }))
              }
              className="h-10 w-full rounded-lg border border-slate-200 px-3"
            />
          </label>
        </div>

        <label className="mt-3 inline-flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={llmParams.enableChainOfThought}
            onChange={(event) => setLlmParams((prev) => ({ ...prev, enableChainOfThought: event.target.checked }))}
          />
          Enable reasoning trace capture (for instructor audit only)
        </label>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="inline-flex items-center gap-2 text-xl font-semibold text-blue-950">
          <Cable className="h-5 w-5" />
          API Connections
        </h2>

        <div className="mt-4 max-w-xl space-y-3">
          <div>
            <label className="text-sm font-medium text-slate-700">GitHub Access Token</label>
            <div className="mt-1 flex gap-2">
              <input
                type="password"
                value={apiConnections.githubToken}
                onChange={(event) => updateApiField("githubToken", event.target.value)}
                className="h-10 flex-1 rounded-lg border border-slate-200 px-3"
              />
              <button
                type="button"
                onClick={() => handleTestConnection("github")}
                className="inline-flex h-10 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm"
              >
                <RefreshCw className="h-4 w-4" />
                Test
              </button>
            </div>
            <p className={`mt-1 text-xs ${apiConnections.githubConnected ? "text-emerald-600" : "text-rose-600"}`}>
              {apiConnections.githubConnected ? "Connected" : "Not connected"}
            </p>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">Jira API Token</label>
            <div className="mt-1 flex gap-2">
              <input
                type="password"
                value={apiConnections.jiraToken}
                onChange={(event) => updateApiField("jiraToken", event.target.value)}
                className="h-10 flex-1 rounded-lg border border-slate-200 px-3"
              />
              <button
                type="button"
                onClick={() => handleTestConnection("jira")}
                className="inline-flex h-10 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm"
              >
                <RefreshCw className="h-4 w-4" />
                Test
              </button>
            </div>
            <p className={`mt-1 text-xs ${apiConnections.jiraConnected ? "text-emerald-600" : "text-rose-600"}`}>
              {apiConnections.jiraConnected ? "Connected" : "Not connected"}
            </p>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">Jira Domain</label>
            <input
              type="text"
              value={apiConnections.jiraDomain}
              onChange={(event) => updateApiField("jiraDomain", event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-3"
            />
          </div>
        </div>
      </section>

      <div className="flex items-center justify-end gap-3">
        {saveMessage && <p className="text-sm text-emerald-600">{saveMessage}</p>}
        <button
          type="button"
          onClick={handleSave}
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white transition hover:bg-blue-950"
        >
          <Save className="h-4 w-4" />
          Save Settings
        </button>
      </div>
    </div>
  );
}