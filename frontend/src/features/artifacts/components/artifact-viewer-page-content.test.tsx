/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderComponent } from "@/test-utils";
import type { JiraIngestionRun } from "@/features/artifacts/types";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

const mocks = vi.hoisted(() => ({
  fetchJiraRuns: vi.fn(),
  fetchJiraSprints: vi.fn(),
  apiRequest: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({
  useSession: () => ({ user: { role: "instructor", fullName: "Sample Instructor" } }),
}));
vi.mock("@/features/artifacts/hooks/use-artifact-tab", () => ({
  useArtifactTab: () => ({ activeTab: "jira", setActiveTab: vi.fn() }),
}));
vi.mock("@/features/artifacts/hooks/use-artifact-project-scope", () => ({
  useArtifactProjectScope: () => ({
    projectOptions: [{ id: PROJECT_ID, courseId: "course-1", name: "Team Kiwi" }],
    selectedProjectId: PROJECT_ID,
    isLoadingProjects: false,
    projectLoadError: "",
  }),
}));
vi.mock("@/features/artifacts/git-runs-api", () => ({
  fetchProjectGitRuns: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/features/artifacts/jira-api", () => ({
  fetchJiraRuns: mocks.fetchJiraRuns,
  fetchJiraSprints: mocks.fetchJiraSprints,
  deleteJiraRun: vi.fn(),
}));
vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: mocks.apiRequest,
}));

import ArtifactViewerPageContent from "@/features/artifacts/components/artifact-viewer-page-content";

const pendingRun: JiraIngestionRun = {
  run_id: "run-1",
  course_id: "course-1",
  project_id: PROJECT_ID,
  sprint_id: "Sprint 3",
  jira_project_key: "KIWI",
  jql: "project = KIWI",
  issue_count: 12,
  captured_at: "2026-11-10T09:00:00Z",
  processed_at: null,
  processing_status: "pending",
  normalization_version: null,
  processing_error: null,
};

describe("ArtifactViewerPageContent Jira tab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.apiRequest.mockResolvedValue([]); // documents list
    mocks.fetchJiraRuns.mockResolvedValue([pendingRun]);
  });

  it("loads the project's Jira runs when an instructor opens the page", async () => {
    mocks.fetchJiraSprints.mockResolvedValue([]);
    renderComponent(<ArtifactViewerPageContent />);

    await waitFor(() =>
      expect(mocks.fetchJiraRuns).toHaveBeenCalledWith(PROJECT_ID, expect.any(AbortSignal)),
    );
    expect(await screen.findByRole("cell", { name: "Sprint 3" })).toBeInTheDocument();
    // No sprints from the Jira board: the sprint falls back to the typed field, prefilled from the run.
    expect(await screen.findByLabelText("Sprint")).toHaveValue("Sprint 3");
  });

  it("asks Jira for the board's sprints and preselects the active one", async () => {
    mocks.fetchJiraSprints.mockResolvedValue([
      { id: 1, name: "Sprint 3", state: "closed", start_date: null, end_date: null },
      { id: 2, name: "Sprint 4", state: "active", start_date: null, end_date: null },
    ]);
    renderComponent(<ArtifactViewerPageContent />);

    await waitFor(() =>
      expect(mocks.fetchJiraSprints).toHaveBeenCalledWith(PROJECT_ID, expect.any(AbortSignal)),
    );
    const field = await screen.findByRole("combobox", { name: "Sprint" });
    await waitFor(() => expect(field).toHaveValue("Sprint 4"));
  });
});
