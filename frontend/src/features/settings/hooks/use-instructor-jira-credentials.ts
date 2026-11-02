"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getInstructorJiraCredentials,
  saveInstructorJiraCredentials,
} from "@/features/settings/settings-api";
import { getDefaultJiraEmail } from "@/features/projects/components/projects-api";

export function useInstructorJiraCredentials(enabled: boolean) {
  const [jiraEmail, setJiraEmail] = useState("");
  const [savedJiraEmail, setSavedJiraEmail] = useState("");
  const [jiraApiToken, setJiraApiToken] = useState("");
  const [hasSavedToken, setHasSavedToken] = useState(false);
  const [hasSavedSettings, setHasSavedSettings] = useState(false);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) return;

    let isCurrent = true;
    setIsLoading(true);
    setError("");
    getInstructorJiraCredentials()
      .then((credentials) => {
        if (!isCurrent) return;
        const email = credentials.jira_email || getDefaultJiraEmail();
        setJiraEmail(email);
        setSavedJiraEmail(email);
        setHasSavedToken(credentials.jira_token_configured);
        setHasSavedSettings(credentials.is_saved);
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load Jira credentials.");
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [enabled]);

  const saveCredentials = useCallback(async (): Promise<boolean> => {
    const normalizedEmail = jiraEmail.trim();
    const normalizedToken = jiraApiToken.trim();
    if (!normalizedEmail) {
      setError("Enter the Jira account email before saving.");
      return false;
    }

    setIsSaving(true);
    setError("");
    try {
      const credentials = await saveInstructorJiraCredentials(normalizedEmail, normalizedToken || undefined);
      setJiraEmail(credentials.jira_email);
      setSavedJiraEmail(credentials.jira_email);
      setJiraApiToken("");
      setHasSavedToken(credentials.jira_token_configured);
      setHasSavedSettings(credentials.is_saved);
      return true;
    } catch (saveError: unknown) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save Jira credentials.");
      return false;
    } finally {
      setIsSaving(false);
    }
  }, [jiraApiToken, jiraEmail]);

  return {
    jiraEmail,
    setJiraEmail,
    jiraApiToken,
    setJiraApiToken,
    hasSavedToken,
    hasSavedSettings,
    isLoading,
    isSaving,
    error,
    hasUnsavedChanges:
      !hasSavedSettings || jiraEmail.trim() !== savedJiraEmail || Boolean(jiraApiToken.trim()),
    saveCredentials,
  };
}
