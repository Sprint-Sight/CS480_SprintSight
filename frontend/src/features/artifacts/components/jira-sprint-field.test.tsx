/// <reference types="vitest/globals" />
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JiraSprintField } from "@/features/artifacts/components/jira-sprint-field";
import type { JiraSprint } from "@/features/artifacts/jira-api";

const BOARD_SPRINTS: JiraSprint[] = [
  { id: 1, name: "Sprint 1", state: "closed", start_date: null, end_date: null },
  { id: 2, name: "Sprint 2", state: "active", start_date: null, end_date: null },
];

describe("JiraSprintField", () => {
  it("shows a dropdown of board sprints, linked to its label, when Jira returns sprints", () => {
    render(
      <JiraSprintField sprintId="Sprint 2" sprints={BOARD_SPRINTS} onSprintIdChange={vi.fn()} />,
    );

    const select = screen.getByLabelText("Sprint");
    expect(select.tagName).toBe("SELECT");
    expect(screen.getByText("Sprints from your Jira board")).toBeInTheDocument();
    expect(screen.queryByText(/Enter the Jira sprint name/)).not.toBeInTheDocument();
  });

  it("falls back to a typeable sprint field with helper text when Jira returns no sprints", () => {
    const onSprintIdChange = vi.fn();
    render(<JiraSprintField sprintId="" sprints={[]} onSprintIdChange={onSprintIdChange} />);

    const input = screen.getByLabelText("Sprint");
    expect(input.tagName).toBe("INPUT");
    expect(screen.getByText(/Enter the Jira sprint name/)).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "Sprint 3" } });
    expect(onSprintIdChange).toHaveBeenCalledWith("Sprint 3");
  });
});
