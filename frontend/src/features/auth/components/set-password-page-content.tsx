"use client";

import { SetPasswordForm } from "@/features/auth/components/set-password-form";
import { useSetPassword } from "@/features/auth/hooks/use-password-actions";

export function SetPasswordPageContent() {
  const passwordAction = useSetPassword();

  return (
    <SetPasswordForm
      token={passwordAction.token}
      purpose={passwordAction.purpose}
      password={passwordAction.password}
      confirmPassword={passwordAction.confirmPassword}
      error={passwordAction.error}
      isLoading={passwordAction.isLoading}
      isComplete={passwordAction.isComplete}
      onPasswordChange={passwordAction.setPassword}
      onConfirmPasswordChange={passwordAction.setConfirmPassword}
      onSubmit={(event) => {
        event.preventDefault();
        void passwordAction.submit();
      }}
    />
  );
}
