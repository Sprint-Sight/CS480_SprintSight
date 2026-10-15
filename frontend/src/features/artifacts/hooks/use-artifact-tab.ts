"use client";

import { useCallback, useEffect, useState } from "react";

import type { ArtifactTab } from "@/features/artifacts/types";

const VALID_TABS: ArtifactTab[] = ["github", "jira", "documents", "communication", "peer-evaluation"];

export function parseArtifactTab(value: string | null): ArtifactTab | null {
  return VALID_TABS.find((tab) => tab === value) ?? null;
}

export function useArtifactTab(defaultTab: ArtifactTab = "github") {
  const [activeTab, setActiveTabState] = useState<ArtifactTab>(defaultTab);

  useEffect(() => {
    const fromUrl = parseArtifactTab(new URLSearchParams(window.location.search).get("tab"));
    if (fromUrl) setActiveTabState(fromUrl);
  }, []);

  const setActiveTab = useCallback((tab: ArtifactTab) => {
    setActiveTabState(tab);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    window.history.replaceState(window.history.state, "", url);
  }, []);

  return { activeTab, setActiveTab };
}
