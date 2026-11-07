/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { EmptyState } from "@/components/ui/empty-state";

describe("EmptyState", () => {
  it("renders the title, description and action", () => {
    renderComponent(
      <EmptyState title="No projects yet" description="Create one to start." action={<button type="button">New project</button>} />,
    );
    expect(screen.getByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    expect(screen.getByText("Create one to start.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New project" })).toBeInTheDocument();
  });

  it("omits the description and action wrappers when they are not provided", () => {
    const { container } = renderComponent(<EmptyState title="Nothing here" />);
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });
});
