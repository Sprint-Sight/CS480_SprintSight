/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { LoginForm } from "@/features/auth/components/login-form";

function renderLogin(error = "") {
  renderComponent(
    <LoginForm
      email=""
      password=""
      error={error}
      isLoading={false}
      onEmailChange={vi.fn()}
      onPasswordChange={vi.fn()}
      onSubmit={vi.fn()}
    />,
  );
}

describe("LoginForm accessibility", () => {
  it("connects labels to inputs and sets password-manager autocomplete hints", () => {
    renderLogin();

    const email = screen.getByLabelText("Email Address");
    const password = screen.getByLabelText("Password");

    expect(email).toHaveAttribute("name", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    expect(password).toHaveAttribute("name", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("announces the error and links it to both inputs", () => {
    renderLogin("Invalid credentials");

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Invalid credentials");

    const email = screen.getByLabelText("Email Address");
    const password = screen.getByLabelText("Password");
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAttribute("aria-describedby", alert.id);
    expect(password).toHaveAttribute("aria-describedby", alert.id);
  });

  it("leaves inputs unmarked when there is no error", () => {
    renderLogin();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email Address")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Email Address")).not.toHaveAttribute("aria-describedby");
  });
});
