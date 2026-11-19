/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useRequireAdmin: vi.fn(),
  useInsightsHealth: vi.fn(),
  usePromptRegistry: vi.fn(),
  usePromptVersion: vi.fn(),
}));
vi.mock("@/features/auth/hooks/use-require-admin", () => ({ useRequireAdmin: mocks.useRequireAdmin }));
vi.mock("@/features/insights/hooks/use-insights", () => ({
  useInsightsHealth: mocks.useInsightsHealth,
  usePromptRegistry: mocks.usePromptRegistry,
  usePromptVersion: mocks.usePromptVersion,
}));
vi.mock("@/features/insights/components/health-panel", () => ({
  HealthPanel: () => <p>health panel</p>,
}));
vi.mock("@/features/insights/components/prompt-registry-panel", () => ({
  PromptRegistryPanel: ({ onOpenVersion }: { onOpenVersion: (s: unknown) => void }) => (
    <button
      onClick={() => onOpenVersion({ name: "Evaluate_Scope", version: 2, role: "production" })}
    >
      open version
    </button>
  ),
}));
vi.mock("@/features/insights/components/prompt-version-dialog", () => ({
  PromptVersionDialog: ({ name, version }: { name: string; version: number }) => (
    <p>
      version dialog {name} v{version}
    </p>
  ),
}));

import { AdminInsightsContent } from "@/features/insights/components/admin-insights-content";

describe("AdminInsightsContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.usePromptRegistry.mockReturnValue({ isLoading: false, isError: false, data: undefined });
    mocks.usePromptVersion.mockReturnValue({ isLoading: false, isError: false, data: undefined });
  });

  it("renders nothing and does not fetch health until the admin check passes", () => {
    mocks.useRequireAdmin.mockReturnValue(false);
    mocks.useInsightsHealth.mockReturnValue({ isLoading: false, data: undefined, error: null });
    const { container } = render(<AdminInsightsContent />);
    expect(container).toBeEmptyDOMElement();
    expect(mocks.useInsightsHealth).toHaveBeenCalledWith(false);
  });

  it("shows the health panel for an admin", () => {
    mocks.useRequireAdmin.mockReturnValue(true);
    mocks.useInsightsHealth.mockReturnValue({ isLoading: false, data: { ok: true }, error: null });
    render(<AdminInsightsContent />);
    expect(screen.getByRole("heading", { name: "Evaluation insights" })).toBeInTheDocument();
    expect(screen.getByText("health panel")).toBeInTheDocument();
    expect(mocks.useInsightsHealth).toHaveBeenCalledWith(true);
  });

  it("shows a loading line while health is being checked", () => {
    mocks.useRequireAdmin.mockReturnValue(true);
    mocks.useInsightsHealth.mockReturnValue({ isLoading: true, data: undefined, error: null });
    render(<AdminInsightsContent />);
    expect(screen.getByText("Checking pipeline…")).toBeInTheDocument();
  });

  it("requests the prompt registry only after the admin check passes", () => {
    mocks.useRequireAdmin.mockReturnValue(false);
    mocks.useInsightsHealth.mockReturnValue({ isLoading: false, data: undefined, error: null });
    render(<AdminInsightsContent />);
    expect(mocks.usePromptRegistry).toHaveBeenCalledWith(false);
  });

  it("fetches a prompt version only once a version is opened", () => {
    mocks.useRequireAdmin.mockReturnValue(true);
    mocks.useInsightsHealth.mockReturnValue({ isLoading: false, data: { ok: true }, error: null });
    render(<AdminInsightsContent />);
    expect(mocks.usePromptVersion).toHaveBeenLastCalledWith("", 0, false);
    expect(screen.queryByText(/version dialog/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "open version" }));
    expect(mocks.usePromptVersion).toHaveBeenLastCalledWith("Evaluate_Scope", 2, true);
    expect(screen.getByText("version dialog Evaluate_Scope v2")).toBeInTheDocument();
  });
});
