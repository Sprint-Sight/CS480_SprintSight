"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { INITIAL_SETTINGS } from "@/features/settings/data";
import type { RubricWeight } from "@/features/settings/types";
import { SettingsHeader } from "@/features/settings/components/settings-header";
import { RubricSettings } from "@/features/settings/components/rubric-settings";
import { LlmSettings } from "@/features/settings/components/llm-settings";
import { ApiConnectionsSettings } from "@/features/settings/components/api-connections-settings";
import { useModelSelection } from "@/features/settings/hooks/use-model-selection";
import { useInstructorJiraCredentials } from "@/features/settings/hooks/use-instructor-jira-credentials";

function clamp(value: number, min: number, max: number) { return Math.max(min, Math.min(max, value)); }

export default function SettingsPageContent() {
  const router = useRouter();
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [rubric, setRubric] = useState(INITIAL_SETTINGS.rubric);
  const [saveMessage, setSaveMessage] = useState("");
  const modelSelection = useModelSelection(isAuthorized);
  const jiraCredentials = useInstructorJiraCredentials(isAuthorized);
  const totalWeight = useMemo(() => rubric.reduce((sum, item) => sum + item.value, 0), [rubric]);

  useEffect(() => { if (sessionStorage.getItem("sprintsight-auth-role") === "student") router.replace("/"); else setIsAuthorized(true); }, [router]);
  const updateRubricWeight = (id: RubricWeight["id"], value: number) => setRubric((prev) => prev.map((item) => item.id === id ? { ...item, value: clamp(value, 0, 100) } : item));
  if (!isAuthorized) return null;
  const saveSettings = async () => {
    setSaveMessage("");
    const [modelSaved, jiraEmailSaved] = await Promise.all([
      modelSelection.saveSelection(),
      jiraCredentials.hasUnsavedChanges
        ? jiraCredentials.saveCredentials()
        : Promise.resolve(true),
    ]);
    if (modelSaved && jiraEmailSaved) {
      setSaveMessage(`Settings saved at ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`);
    }
  };
  const updateSelectedModel = (modelId: string) => {
    modelSelection.selectModel(modelId);
    setSaveMessage("");
  };
  const isModelSelectionUnavailable = modelSelection.isLoading || modelSelection.isSaving || modelSelection.models.length === 0;
  const canSaveModelSelection = modelSelection.models.some((model) => model.id === modelSelection.selectedModelId);
  const isSavingSettings = isModelSelectionUnavailable || jiraCredentials.isLoading || jiraCredentials.isSaving;
  return (
    <div className="space-y-5 p-8">
      <SettingsHeader />
      <LlmSettings
        models={modelSelection.models}
        selectedModelId={modelSelection.selectedModelId}
        isDisabled={isModelSelectionUnavailable}
        onModelChange={updateSelectedModel}
      />
      {modelSelection.isLoading && <p role="status" className="text-sm text-slate-600">Loading AI models...</p>}
      {modelSelection.error && <p role="alert" className="text-sm text-red-700">{modelSelection.error}</p>}
      <div className="grid min-w-0 grid-cols-1 items-stretch gap-5 lg:grid-cols-2">
        <RubricSettings rubric={rubric} totalWeight={totalWeight} onChange={updateRubricWeight} />
        <ApiConnectionsSettings
          jiraEmail={jiraCredentials.jiraEmail}
          hasSavedToken={jiraCredentials.hasSavedToken}
          isLoading={jiraCredentials.isLoading}
          error={jiraCredentials.error}
          onJiraEmailChange={jiraCredentials.setJiraEmail}
        />
      </div>
      <div className="flex items-center justify-end gap-3">
        {saveMessage && <p role="status" className="text-sm text-emerald-600">{saveMessage}</p>}
        <button
          type="button"
          onClick={saveSettings}
          disabled={isSavingSettings || !canSaveModelSelection}
          className="h-10 rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {modelSelection.isSaving ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}
