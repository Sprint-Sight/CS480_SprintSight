/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { LoginForm } from "@/features/auth/components/login-form";

function renderLogin(error = "", showWelcomeHeading = false) {
  renderComponent(
    <LoginForm
      showWelcomeHeading={showWelcomeHeading}
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

describe("LoginForm layout", () => {
  it("shows the logo and tagline by default (showcase flag off)", () => {
    renderLogin();
    expect(screen.getByAltText("SprintSight Logo")).toBeInTheDocument();
    expect(screen.getByText("AI-Powered Continuous Sprint Assessment")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome to SprintSight" })).not.toBeInTheDocument();
  });

  it("shows the idle showcase welcome heading instead of the logo when asked", () => {
    renderLogin("", true);
    const heading = screen.getByRole("heading", { level: 1, name: "Welcome to SprintSight" });
    expect(heading.closest("header")!.getAttribute("class")).toContain("text-center");
    expect(screen.getByTestId("login-welcome-brand")).toHaveTextContent("SprintSight");
    expect(screen.queryByAltText("SprintSight Logo")).not.toBeInTheDocument();
  });

  it("leaves the background to the auth shell so the theme shows behind the card", () => {
    renderLogin();
    const card = screen.getByRole("button", { name: /sign in/i }).closest("form")!.parentElement!;
    expect(card.getAttribute("class")).toContain("bg-white");
    expect(card.parentElement!.getAttribute("class")).not.toContain("bg-slate-50");
  });
});

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
