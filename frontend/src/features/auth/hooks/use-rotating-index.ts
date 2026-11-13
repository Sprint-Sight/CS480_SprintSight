"use client";

// IDLE FEATURE: AUTH SHOWCASE (off by default). Used only by the auth showcase; see
// src/features/auth/auth-feature-flags.ts.

import { useEffect, useState } from "react";

import { useMediaQuery } from "@/hooks/use-media-query";

export const ROTATION_INTERVAL_MS = 5000;

/**
 * Cycles 0..length-1 every `intervalMs`. Stays on 0 when the user prefers reduced motion,
 * and clears its timer on unmount.
 */
export function useRotatingIndex(length: number, intervalMs = ROTATION_INTERVAL_MS): number {
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion || length < 2) {
      setIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % length);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [prefersReducedMotion, length, intervalMs]);

  return index;
}
