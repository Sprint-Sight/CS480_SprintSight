"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { restoreSession } from "@/features/auth/login-api";

/**
 * Restores the session and sends anyone who is not an admin to /login.
 * Returns true once the user is confirmed as an admin; render nothing until then.
 */
export function useRequireAdmin(): boolean {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let current = true;
    void restoreSession().then((restored) => {
      if (!current) return;
      if (restored?.user?.role !== "admin") router.replace("/login");
      else setAllowed(true);
    });
    return () => {
      current = false;
    };
  }, [router]);

  return allowed;
}
