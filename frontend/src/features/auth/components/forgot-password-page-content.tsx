"use client";

import { ForgotPasswordForm } from "@/features/auth/components/forgot-password-form";
import { useForgotPassword } from "@/features/auth/hooks/use-password-actions";

export function ForgotPasswordPageContent() {
  const passwordReset = useForgotPassword();

  return (
    <ForgotPasswordForm
      email={passwordReset.email}
      error={passwordReset.error}
      isLoading={passwordReset.isLoading}
      isSubmitted={passwordReset.isSubmitted}
      onEmailChange={passwordReset.setEmail}
      onSubmit={(event) => {
        event.preventDefault();
        void passwordReset.submit();
      }}
    />
  );
}
