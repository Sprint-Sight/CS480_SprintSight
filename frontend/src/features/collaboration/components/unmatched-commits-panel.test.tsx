import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UnmatchedCommitsPanel } from "@/features/collaboration/components/unmatched-commits-panel";

describe("UnmatchedCommitsPanel", () => {
  it("summarizes unattributed commits and reveals their details on demand", () => {
    const { container } = render(
      <UnmatchedCommitsPanel
        commits={[
          {
            sha: "abcdef123456",
            author: "Unknown Git author",
            timestamp: "2026-10-29T10:00:00Z",
            linesAdded: 6,
            linesDeleted: 2,
          },
        ]}
      />,
    );

    expect(screen.getByText("1 unmatched commit")).toBeTruthy();
    expect(container.querySelector("details")?.open).toBe(false);

    fireEvent.click(screen.getByText(/View details/));

    expect(container.querySelector("details")?.open).toBe(true);
    expect(screen.getByText("Unknown Git author")).toBeTruthy();
    expect(screen.getByText("abcdef1234")).toBeTruthy();
    expect(screen.getByText(/\+6 \/ -2/)).toBeTruthy();
  });
});
