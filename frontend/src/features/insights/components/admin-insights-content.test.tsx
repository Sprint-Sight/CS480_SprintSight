/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useRequireAdmin: vi.fn(), useInsightsHealth: vi.fn() }));
vi.mock("@/features/auth/hooks/use-require-admin", () => ({ useRequireAdmin: mocks.useRequireAdmin }));
vi.mock("@/features/insights/hooks/use-insights", () => ({
  useInsightsHealth: mocks.useInsightsHealth,
}));
vi.mock("@/features/insights/components/health-panel", () => ({
  HealthPanel: () => <p>health panel</p>,
}));

import { AdminInsightsContent } from "@/features/insights/components/admin-insights-content";

describe("AdminInsightsContent", () => {
  beforeEach(() => vi.clearAllMocks());

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
});
