"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  loginUser,
  fetchUserProfile,
  changePasswordOnFirstLogin,
} from "@/features/auth/login-api";

export function useLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function submitLogin() {
    setError("");
    setIsLoading(true);

    try {
      const loginResponse = await loginUser(email, password);

      // Store JWT token in both session and local storage
      sessionStorage.setItem("sprintsight-access-token", loginResponse.access_token);
      localStorage.setItem("sprintsight-access-token", loginResponse.access_token);

      // If password must be changed on first login, show the form
      if (loginResponse.must_change_password) {
        setMustChangePassword(true);
        setError("");
        return;
      }

      // Fetch user profile to determine role and redirect
      const user = await fetchUserProfile(loginResponse.access_token);

      // Store user details in session storage
      sessionStorage.setItem("sprintsight-auth-role", user.role);
      sessionStorage.setItem("sprintsight-auth-email", user.email);
      sessionStorage.setItem("sprintsight-auth-name", user.full_name);

      // Redirect based on user role
      if (user.role === "admin") {
        router.replace("/admin");
      } else {
        router.replace("/");
      }
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "An unexpected error occurred. Please try again.",
      );

      // Clear tokens if login fails
      sessionStorage.removeItem("sprintsight-access-token");
      localStorage.removeItem("sprintsight-access-token");
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

    const token = sessionStorage.getItem("sprintsight-access-token");
    if (!token) {
      setError("Your session has expired. Please log in again.");
      return;
    }

    setIsLoading(true);

    try {
      // Change password using the token from login
      await changePasswordOnFirstLogin(token, password, newPassword);

      // Log in with the new password to get a fresh session
      const loginResponse = await loginUser(email, newPassword);

      // Update token with refreshed one
      sessionStorage.setItem("sprintsight-access-token", loginResponse.access_token);
      localStorage.setItem("sprintsight-access-token", loginResponse.access_token);

      // Fetch user profile to get role and redirect
      const user = await fetchUserProfile(loginResponse.access_token);

      sessionStorage.setItem("sprintsight-auth-role", user.role);
      sessionStorage.setItem("sprintsight-auth-email", user.email);
      sessionStorage.setItem("sprintsight-auth-name", user.full_name);

      // Redirect based on role
      if (user.role === "admin") {
        router.replace("/admin");
      } else {
        router.replace("/");
      }
    } catch (changeError) {
      setError(
        changeError instanceof Error
          ? changeError.message
          : "Unable to change password.",
      );
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
