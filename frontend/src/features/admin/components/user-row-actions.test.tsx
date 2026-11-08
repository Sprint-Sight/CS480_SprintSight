/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { UserRowActions } from "@/features/admin/components/user-row-actions";

function renderActions(overrides: Partial<Parameters<typeof UserRowActions>[0]> = {}) {
  const handlers = {
    onEdit: vi.fn(),
    onResetPassword: vi.fn(),
    onDeactivate: vi.fn(),
    onActivate: vi.fn(),
  };
  renderComponent(
    <UserRowActions
      userName="Ada Lovelace"
      isActive
      isSelf={false}
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe("UserRowActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("labels each desktop icon button with the action and user name", () => {
    const handlers = renderActions();

    fireEvent.click(screen.getByRole("button", { name: "Edit role / user details: Ada Lovelace" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset password: Ada Lovelace" }));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate user: Ada Lovelace" }));

    expect(handlers.onEdit).toHaveBeenCalledOnce();
    expect(handlers.onResetPassword).toHaveBeenCalledOnce();
    expect(handlers.onDeactivate).toHaveBeenCalledOnce();
  });

  it("disables deactivate for the signed-in admin's own row", () => {
    renderActions({ isSelf: true });

    expect(screen.getByRole("button", { name: "Deactivate user: Ada Lovelace" })).toBeDisabled();
  });

  it("offers activate instead of deactivate for inactive users", () => {
    const handlers = renderActions({ isActive: false });

    fireEvent.click(screen.getByRole("button", { name: "Activate user: Ada Lovelace" }));

    expect(screen.queryByRole("button", { name: "Deactivate user: Ada Lovelace" })).not.toBeInTheDocument();
    expect(handlers.onActivate).toHaveBeenCalledOnce();
  });

  it("opens the phone menu, runs the chosen action, and closes the menu", () => {
    const handlers = renderActions();
    const toggle = screen.getByRole("button", { name: "More actions for Ada Lovelace" });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));

    expect(handlers.onResetPassword).toHaveBeenCalledOnce();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Reset password" })).not.toBeInTheDocument();
  });
});
