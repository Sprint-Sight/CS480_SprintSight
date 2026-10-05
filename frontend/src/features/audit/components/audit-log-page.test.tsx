/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { AuditLogPage } from "@/features/audit/components/audit-log-page";

describe("AuditLogPage - Critical User Workflow: Role-Based Access", () => {
  const mockRefresh = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render audit log page for instructor with back link to dashboard", () => {
    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("Audit Log")).toBeInTheDocument();
    const backLink = screen.getByText(/Back to Dashboard/);
    expect(backLink).toBeInTheDocument();
    expect(backLink.closest("a")).toHaveAttribute("href", "/");
  });

  it("should render audit log page for admin with back link to user directory", () => {
    renderComponent(
      <AuditLogPage
        role="admin"
        actions={[]}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("Audit Log")).toBeInTheDocument();
    const backLink = screen.getByText(/Back to User Directory/);
    expect(backLink).toBeInTheDocument();
    expect(backLink.closest("a")).toHaveAttribute("href", "/admin");
  });

  it("should display action audit table with records", () => {
    const mockActions = [
      {
        audit_id: "1",
        actor_id: "instructor-1",
        actor_role: "instructor" as const,
        action: "generate_assessment",
        target_type: "sprint",
        target_id: "sprint-1",
        details: { team_id: "team-1" },
        created_at: "2024-10-01T10:00:00Z",
      },
    ];

    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={mockActions}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("Action History")).toBeInTheDocument();
    expect(screen.getByText("generate_assessment")).toBeInTheDocument();
    expect(screen.getByText("ID: instructor-1")).toBeInTheDocument();
  });

  it("should display override audit table with records", () => {
    const mockOverrides = [
      {
        override_id: "1",
        timestamp: "2024-10-01T10:00:00Z",
        instructor_id: "instructor-1",
        student_id: "student-1",
        report_id: "report-1",
        original_score: 80,
        new_score: 85,
        reason_comment: "Calculation error corrected",
      },
    ];

    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={mockOverrides}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("Score Overrides")).toBeInTheDocument();
    expect(screen.getByText("Calculation error corrected")).toBeInTheDocument();
    // The percentage is split across multiple elements, so check the table cell contains both values
    const tableCell = screen.getByText((content, element) => {
      return element?.tagName.toLowerCase() === "td" && element?.textContent?.includes("80") && element?.textContent?.includes("85");
    });
    expect(tableCell).toBeInTheDocument();
  });

  it("should display empty state when no records are available", () => {
    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("No action records are available.")).toBeInTheDocument();
    expect(screen.getByText("No score overrides are available.")).toBeInTheDocument();
  });

  it("should display error state when loading fails", () => {
    const errorMsg = "Failed to load audit records";
    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={[]}
        actionsError={errorMsg}
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText(errorMsg)).toBeInTheDocument();
  });

  it("should display loading state", () => {
    renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={true}
        onRefresh={mockRefresh}
      />
    );

    expect(screen.getByText("Loading action history...")).toBeInTheDocument();
    expect(screen.getByText("Loading score overrides...")).toBeInTheDocument();
  });

  it("should call onRefresh when refresh button is clicked", () => {
    const { container } = renderComponent(
      <AuditLogPage
        role="instructor"
        actions={[]}
        overrides={[]}
        actionsError=""
        overridesError=""
        isLoading={false}
        onRefresh={mockRefresh}
      />
    );

    const refreshButton = container.querySelector("button[type='button']") as HTMLButtonElement | null;
    if (refreshButton) {
      refreshButton.click();
      expect(mockRefresh).toHaveBeenCalled();
    }
  });
});
