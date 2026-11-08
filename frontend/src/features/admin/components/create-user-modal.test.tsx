/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { CreateUserModal } from "@/features/admin/components/create-user-modal";

describe("CreateUserModal labels", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("associates each field label with its input", () => {
    renderComponent(
      <CreateUserModal isOpen onClose={vi.fn()} onCreate={vi.fn().mockResolvedValue(true)} />,
    );

    expect(screen.getByLabelText("Full Name")).toHaveAttribute("autocomplete", "name");
    expect(screen.getByLabelText("Email Address")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Email Address")).toHaveAttribute("name", "email");
  });

  it("gives the close button an accessible name", () => {
    renderComponent(
      <CreateUserModal isOpen onClose={vi.fn()} onCreate={vi.fn().mockResolvedValue(true)} />,
    );

    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
