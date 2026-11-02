"use client";

import { useEffect, useState } from "react";

import {
  getModelCatalog,
  getModelSelection,
  saveModelSelection,
} from "@/features/settings/settings-api";
import type { LlmModelOption } from "@/features/settings/types";

export function useModelSelection(enabled: boolean) {
  const [models, setModels] = useState<LlmModelOption[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) return;

    let isCurrent = true;
    setIsLoading(true);
    setError("");

    Promise.all([getModelCatalog(), getModelSelection()])
      .then(([catalog, selection]) => {
        if (!isCurrent) return;
        setModels(catalog.models);
        const selectedId = selection.model_id || catalog.default_model_id;
        setSelectedModelId(selectedId);
        if (!catalog.models.some((model) => model.id === selectedId)) {
          setError("The configured model is not in the available catalogue. Select an available model before saving.");
        }
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load AI models.");
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [enabled]);

  const saveSelection = async (): Promise<boolean> => {
    if (!models.some((model) => model.id === selectedModelId)) {
      setError("Select an available AI model before saving.");
      return false;
    }
    setIsSaving(true);
    setError("");
    try {
      const selection = await saveModelSelection(selectedModelId);
      setSelectedModelId(selection.model_id);
      return true;
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "Unable to save the AI model selection.";
      setError(message);
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const selectModel = (modelId: string) => {
    setSelectedModelId(modelId);
    setError("");
  };

  return {
    models,
    selectedModelId,
    selectModel,
    isLoading,
    isSaving,
    error,
    saveSelection,
  };
}
