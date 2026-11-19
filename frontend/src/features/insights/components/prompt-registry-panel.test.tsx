/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PromptRegistryPanel } from "@/features/insights/components/prompt-registry-panel";
import type { PromptRegistry } from "@/features/insights/types";

const registry: PromptRegistry = {
  available: true,
  notice: "Prompts are read from MLflow.",
  prompts: [{ name: "Evaluate_Scope", production: 2, challenger: null, latest: 3 }],
};

describe("PromptRegistryPanel", () => {
  it("shows a loading message without rendering the table", () => {
    render(
      <PromptRegistryPanel
        registry={undefined}
        isLoading
        isError={false}
        onOpenVersion={vi.fn()}
      />,
    );
    expect(screen.getByText("Loading prompt registry…")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error message when the registry could not be loaded", () => {
    render(
      <PromptRegistryPanel
        registry={undefined}
        isLoading={false}
        isError
        onOpenVersion={vi.fn()}
      />,
    );
    expect(screen.getByText("Could not load the prompt registry.")).toBeInTheDocument();
  });

  it("calls onOpenVersion with the clicked prompt, role and version", () => {
    const onOpenVersion = vi.fn();
    render(
      <PromptRegistryPanel
        registry={registry}
        isLoading={false}
        isError={false}
        onOpenVersion={onOpenVersion}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "View Evaluate_Scope latest version 3" }));
    expect(onOpenVersion).toHaveBeenCalledWith({
      name: "Evaluate_Scope",
      version: 3,
      role: "latest",
    });
  });

  it("renders a dash instead of a button when a role has no version", () => {
    render(
      <PromptRegistryPanel
        registry={registry}
        isLoading={false}
        isError={false}
        onOpenVersion={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /challenger/ })).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
