"use client";

import { AUTH_SHOWCASE_ENABLED } from "@/features/auth/auth-feature-flags";
import { useLogin } from "@/features/auth/hooks/use-login";
import { LoginForm } from "@/features/auth/components/login-form";
import { InitialPasswordChangeForm } from "@/features/auth/components/initial-password-change-form";

export function LoginPageContent() {
  const login = useLogin();

  if (login.mustChangePassword) {
    return (
      <InitialPasswordChangeForm
        newPassword={login.newPassword}
        confirmPassword={login.confirmPassword}
        error={login.error}
        isLoading={login.isLoading}
        onNewPasswordChange={login.setNewPassword}
        onConfirmPasswordChange={login.setConfirmPassword}
        onSubmit={(event) => {
          event.preventDefault();
          void login.submitPasswordChange();
        }}
      />
    );
  }

  return (
    <LoginForm
      showWelcomeHeading={AUTH_SHOWCASE_ENABLED}
      email={login.email}
      password={login.password}
      error={login.error}
      isLoading={login.isLoading}
      onEmailChange={login.setEmail}
      onPasswordChange={login.setPassword}
      onSubmit={(event) => {
        event.preventDefault();
        void login.submitLogin();
      }}
    />
  );
}
