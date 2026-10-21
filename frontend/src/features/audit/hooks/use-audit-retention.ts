"use client";

import { useCallback, useState } from "react";
import { getAuditRetentionConfig, updateAuditRetentionConfig, type AuditRetentionConfig, type AuditRetentionConfigUpdate } from "@/features/audit/audit-api";

interface AuditRetentionState {
  config: AuditRetentionConfig | null;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  saveError: string | null;
  loadConfig: () => Promise<void>;
  saveConfig: (payload: AuditRetentionConfigUpdate) => Promise<AuditRetentionConfig>;
  clearErrors: () => void;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "An error occurred.";
}

export function useAuditRetention(): AuditRetentionState {
  const [config, setConfig] = useState<AuditRetentionConfig | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await getAuditRetentionConfig();
      setConfig(result);
    } catch (err) {
      setError(getErrorMessage(err));
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const saveConfig = useCallback(async (payload: AuditRetentionConfigUpdate): Promise<AuditRetentionConfig> => {
    setIsSaving(true);
    setSaveError(null);

    try {
      const result = await updateAuditRetentionConfig(payload);
      setConfig(result);
      return result;
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      setSaveError(errorMessage);
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, []);

  const clearErrors = useCallback(() => {
    setError(null);
    setSaveError(null);
  }, []);

  return {
    config,
    isLoading,
    isSaving,
    error,
    saveError,
    loadConfig,
    saveConfig,
    clearErrors,
  };
}
