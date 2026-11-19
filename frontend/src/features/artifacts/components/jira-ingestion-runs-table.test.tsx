/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JiraIngestionRunsTable } from "@/features/artifacts/components/jira-ingestion-runs-table";
import type { JiraIngestionRun } from "@/features/artifacts/types";

const run: JiraIngestionRun = {
  run_id: "run-1",
  course_id: "course-1",
  project_id: "project-1",
  sprint_id: "Sprint 3",
  jira_project_key: "KIWI",
  jql: "project = KIWI",
  issue_count: 12,
  captured_at: "2026-11-10T09:00:00Z",
  processed_at: "2026-11-10T09:01:00Z",
  processing_status: "completed",
  normalization_version: "1",
  processing_error: null,
};

describe("JiraIngestionRunsTable", () => {
  it("asks the container to delete a run (the container confirms first)", () => {
    const onDeleteRun = vi.fn();
    render(<JiraIngestionRunsTable runs={[run]} onLoadCleanedRun={vi.fn()} onDeleteRun={onDeleteRun} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onDeleteRun).toHaveBeenCalledWith(run);
  });

  it("disables Delete while a deletion is in progress", () => {
    render(
      <JiraIngestionRunsTable runs={[run]} onLoadCleanedRun={vi.fn()} onDeleteRun={vi.fn()} isDeleting />,
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByText("Processed")).toBeInTheDocument();
  });
});
