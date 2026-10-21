"use client";

import { useEffect, useState } from "react";

import {
  completePasswordAction,
  requestPasswordReset,
  type PasswordPurpose,
} from "@/features/auth/auth-api";

export function useForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  async function submit() {
    setError("");
    setIsLoading(true);
    try {
      await requestPasswordReset(email);
      setIsSubmitted(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to request a password reset. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return { email, setEmail, error, isLoading, isSubmitted, submit };
}

const INVALID_LINK_MESSAGE = "This password link is invalid. Request a new email and try again.";

export function useSetPassword() {
  const [token, setToken] = useState("");
  const [purpose, setPurpose] = useState<PasswordPurpose | "">("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedPurpose = query.get("purpose");
    const requestedToken = query.get("token");
    if (
      requestedToken &&
      (requestedPurpose === "first-time-password" || requestedPurpose === "password-reset")
    ) {
      setToken(requestedToken);
      setPurpose(requestedPurpose);
    } else {
      setError(INVALID_LINK_MESSAGE);
    }
  }, []);

  async function submit() {
    setError("");
    if (password.length < 8) {
      setError("Your password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    if (!purpose || !token) {
      setError(INVALID_LINK_MESSAGE);
      return;
    }

    setIsLoading(true);
    try {
      await completePasswordAction(purpose, token, password);
      setIsComplete(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to update your password. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return {
    token,
    purpose,
    password,
    setPassword,
    confirmPassword,
    setConfirmPassword,
    error,
    isLoading,
    isComplete,
    submit,
  };
}
