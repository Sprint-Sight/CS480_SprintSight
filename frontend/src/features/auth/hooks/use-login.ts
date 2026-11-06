"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginUser, changePasswordOnFirstLogin, startSession } from "@/features/auth/login-api";
import { getErrorMessage } from "@/lib/api/client";

export function useLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  // Held in memory only: a temporary-password token must not become a usable
  // session (e.g. in another tab) before the password has been changed.
  const [pendingToken, setPendingToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function completeLogin(token: string) {
    const session = await startSession(token);
    router.replace(session.user?.role === "admin" ? "/admin" : "/");
  }

  async function submitLogin() {
    setError("");
    setIsLoading(true);

    try {
      const loginResponse = await loginUser(email, password);

      // If password must be changed on first login, show the form
      if (loginResponse.must_change_password) {
        setPendingToken(loginResponse.access_token);
        setMustChangePassword(true);
        return;
      }

      await completeLogin(loginResponse.access_token);
    } catch (loginError) {
      setError(getErrorMessage(loginError, "Invalid email or password."));
    } finally {
      setIsLoading(false);
    }
  }

  async function submitPasswordChange() {
    setError("");

    if (newPassword.length < 8) {
      setError("The new password must be at least 8 characters.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }

    if (!pendingToken) {
      setError("Your session has expired. Please log in again.");
      return;
    }

    setIsLoading(true);

    try {
      // Change password using the token from login
      await changePasswordOnFirstLogin(pendingToken, password, newPassword);

      // Log in with the new password to get a fresh session
      const loginResponse = await loginUser(email, newPassword);
      setPendingToken("");
      await completeLogin(loginResponse.access_token);
    } catch (changeError) {
      setError(getErrorMessage(changeError, "Unable to change password."));
    } finally {
      setIsLoading(false);
    }
  }

  return {
    email,
    setEmail,
    password,
    setPassword,
    error,
    isLoading,
    mustChangePassword,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    submitLogin,
    submitPasswordChange,
  };
}
