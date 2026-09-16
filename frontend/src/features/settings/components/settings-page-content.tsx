"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { INITIAL_SETTINGS } from "@/features/settings/data";
import type { ApiConnectionSettings, RubricWeight, LlmEvaluationParameters } from "@/features/settings/types";
import { SettingsHeader } from "@/features/settings/components/settings-header";
import { RubricSettings } from "@/features/settings/components/rubric-settings";
import { LlmSettings } from "@/features/settings/components/llm-settings";
import { ApiConnectionsSettings } from "@/features/settings/components/api-connections-settings";

function clamp(value: number, min: number, max: number) { return Math.max(min, Math.min(max, value)); }

export default function SettingsPageContent() {
  const router = useRouter();
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [rubric, setRubric] = useState(INITIAL_SETTINGS.rubric);
  const [selectedModelId, setSelectedModelId] = useState(INITIAL_SETTINGS.selectedModelId);
  const [llmParams, setLlmParams] = useState<LlmEvaluationParameters>(INITIAL_SETTINGS.llmParams);
  const [apiConnections, setApiConnections] = useState<ApiConnectionSettings>(INITIAL_SETTINGS.apiConnections);
  const [saveMessage, setSaveMessage] = useState("");
  const totalWeight = useMemo(() => rubric.reduce((sum, item) => sum + item.value, 0), [rubric]);

  useEffect(() => { if (sessionStorage.getItem("sprintsight-auth-role") === "student") router.replace("/"); else setIsAuthorized(true); }, [router]);
  const updateRubricWeight = (id: RubricWeight["id"], value: number) => setRubric((prev) => prev.map((item) => item.id === id ? { ...item, value: clamp(value, 0, 100) } : item));
  const updateApiField = <K extends keyof ApiConnectionSettings>(field: K, value: ApiConnectionSettings[K]) => setApiConnections((prev) => ({ ...prev, [field]: value }));
  const handleTestConnection = (target: "github" | "jira") => target === "github" ? updateApiField("githubConnected", Boolean(apiConnections.githubToken.trim())) : updateApiField("jiraConnected", Boolean(apiConnections.jiraToken.trim() && apiConnections.jiraDomain.trim()));
  if (!isAuthorized) return null;
  return <div className="space-y-5 p-8"><SettingsHeader /><RubricSettings rubric={rubric} totalWeight={totalWeight} onChange={updateRubricWeight} /><LlmSettings models={INITIAL_SETTINGS.llmModels} selectedModelId={selectedModelId} params={llmParams} onModelChange={setSelectedModelId} onParamsChange={setLlmParams} /><ApiConnectionsSettings settings={apiConnections} onChange={updateApiField} onTest={handleTestConnection} /><div className="flex items-center justify-end gap-3">{saveMessage && <p className="text-sm text-emerald-600">{saveMessage}</p>}<button type="button" onClick={() => setSaveMessage(`Settings saved at ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`)} className="h-10 rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white hover:bg-blue-950">Save Settings</button></div></div>;
}
