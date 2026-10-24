/// <reference types="vitest/globals" />
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { parseArtifactTab, useArtifactTab } from "@/features/artifacts/hooks/use-artifact-tab";

describe("useArtifactTab", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  it("rejects unknown tab values", () => {
    expect(parseArtifactTab("jira")).toBe("jira");
    expect(parseArtifactTab("bogus")).toBeNull();
    expect(parseArtifactTab(null)).toBeNull();
  });

  it("restores the tab from the URL on mount", () => {
    window.history.replaceState(null, "", "/?tab=documents");
    const { result } = renderHook(() => useArtifactTab());
    expect(result.current.activeTab).toBe("documents");
  });

  it("writes the selected tab to the URL", () => {
    const { result } = renderHook(() => useArtifactTab());
    act(() => result.current.setActiveTab("jira"));
    expect(result.current.activeTab).toBe("jira");
    expect(window.location.search).toBe("?tab=jira");
  });
});
