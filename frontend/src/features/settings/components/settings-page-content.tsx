"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { SettingsHeader } from "@/features/settings/components/settings-header";
import { RubricSettings } from "@/features/settings/components/rubric-settings";
import { LlmSettings } from "@/features/settings/components/llm-settings";
import { ApiConnectionsSettings } from "@/features/settings/components/api-connections-settings";
import { useModelSelection } from "@/features/settings/hooks/use-model-selection";
import { useInstructorJiraCredentials } from "@/features/settings/hooks/use-instructor-jira-credentials";
import { useRubricWeights } from "@/features/settings/hooks/use-rubric-weights";
import { useSession } from "@/lib/auth/session";

export default function SettingsPageContent() {
  const router = useRouter();
  const session = useSession();
  const isStudent = session?.user?.role === "student";
  const isAuthorized = Boolean(session?.user) && !isStudent;
  const [saveMessage, setSaveMessage] = useState("");
  const modelSelection = useModelSelection(isAuthorized);
  const jiraCredentials = useInstructorJiraCredentials(isAuthorized);
  const rubricWeights = useRubricWeights(isAuthorized);

  useEffect(() => {
    if (isStudent) router.replace("/");
  }, [isStudent, router]);
  if (!isAuthorized) return null;
  const saveSettings = async () => {
    setSaveMessage("");
    const [modelSaved, jiraEmailSaved, rubricSaved] = await Promise.all([
      modelSelection.saveSelection(),
      jiraCredentials.hasUnsavedChanges
        ? jiraCredentials.saveCredentials()
        : Promise.resolve(true),
      rubricWeights.saveWeights(),
    ]);
    if (modelSaved && jiraEmailSaved && rubricSaved) {
      setSaveMessage(`Settings saved at ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`);
    }
  };
  const updateSelectedModel = (modelId: string) => {
    modelSelection.selectModel(modelId);
    setSaveMessage("");
  };
  const isModelSelectionUnavailable = modelSelection.isLoading || modelSelection.isSaving || modelSelection.models.length === 0;
  const canSaveModelSelection = modelSelection.models.some((model) => model.id === modelSelection.selectedModelId);
  const isSavingSettings = modelSelection.isSaving || jiraCredentials.isSaving || rubricWeights.isSaving;
  const isRubricBlockingSave = rubricWeights.isLoading || (rubricWeights.hasUnsavedChanges && !rubricWeights.isValidTotal);
  const isSaveUnavailable = isModelSelectionUnavailable || jiraCredentials.isLoading || isRubricBlockingSave;
  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-stretch justify-between gap-4">
        <SettingsHeader />
        <div className="flex flex-wrap items-stretch justify-end gap-3">
          {saveMessage && <p role="status" className="text-sm text-emerald-600">{saveMessage}</p>}
          <button
            type="button"
            onClick={saveSettings}
            disabled={isSaveUnavailable || isSavingSettings || !canSaveModelSelection}
            className="min-h-16 self-stretch rounded-xl bg-blue-900 px-6 text-sm font-semibold text-white hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSavingSettings ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </div>
      <LlmSettings
        models={modelSelection.models}
        selectedModelId={modelSelection.selectedModelId}
        isDisabled={isModelSelectionUnavailable}
        onModelChange={updateSelectedModel}
      />
      {modelSelection.isLoading && <p role="status" className="text-sm text-slate-600">Loading AI models...</p>}
      {modelSelection.error && <p role="alert" className="text-sm text-red-700">{modelSelection.error}</p>}
      <div className="grid min-w-0 grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <RubricSettings
          rubric={rubricWeights.rubric}
          totalWeight={rubricWeights.totalWeight}
          isValidTotal={rubricWeights.isValidTotal}
          hasUnsavedChanges={rubricWeights.hasUnsavedChanges}
          courses={rubricWeights.courses}
          selectedCourseId={rubricWeights.selectedCourseId}
          isDisabled={rubricWeights.isLoading || rubricWeights.isSaving || !rubricWeights.selectedCourseId}
          isLoading={rubricWeights.isLoading}
          error={rubricWeights.error}
          onCourseChange={(courseId) => {
            rubricWeights.selectCourse(courseId);
            setSaveMessage("");
          }}
          onChange={(id, value) => {
            rubricWeights.updateWeight(id, value);
            setSaveMessage("");
          }}
        />
        <ApiConnectionsSettings
          jiraEmail={jiraCredentials.jiraEmail}
          hasSavedToken={jiraCredentials.hasSavedToken}
          isLoading={jiraCredentials.isLoading}
          error={jiraCredentials.error}
          onJiraEmailChange={jiraCredentials.setJiraEmail}
        />
      </div>
    </div>
  );
}
