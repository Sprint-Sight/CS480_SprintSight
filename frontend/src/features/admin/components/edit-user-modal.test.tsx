/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { EditUserModal } from "@/features/admin/components/edit-user-modal";
import type { UserAccount } from "@/features/admin/types";

const user = {
  id: "u-1",
  fullName: "Ada Lovelace",
  email: "ada@example.edu",
  role: "student",
  status: "Active",
} as unknown as UserAccount;

async function submitAndConfirm() {
  fireEvent.click(screen.getByRole("button", { name: "Save Assignment" }));
  fireEvent.click(await screen.findByRole("button", { name: "Yes, Update User" }));
}

describe("EditUserModal save outcome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("closes only after a successful save", async () => {
    const onSave = vi.fn().mockResolvedValue(true);
    const onClose = vi.fn();
    renderComponent(<EditUserModal user={user} onClose={onClose} onSave={onSave} />);

    await submitAndConfirm();

    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(onSave).toHaveBeenCalledWith(user, {
      fullName: "Ada Lovelace",
      email: "ada@example.edu",
      role: "student",
    });
  });

  it("keeps the modal open and the edits intact when the save fails", async () => {
    const onSave = vi.fn().mockResolvedValue(false);
    const onClose = vi.fn();
    renderComponent(<EditUserModal user={user} onClose={onClose} onSave={onSave} />);

    await submitAndConfirm();

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save Assignment" })).not.toBeDisabled(),
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue("Ada Lovelace")).toBeInTheDocument();
  });
});
