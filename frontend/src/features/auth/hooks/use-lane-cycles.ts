"use client";

// IDLE FEATURE: AUTH SHOWCASE (off by default). Used only by the auth showcase; see
// src/features/auth/auth-feature-flags.ts.

import { useCallback, useState } from "react";

/** Counts how many trips each board lane's card has finished, so it can show a new ticket. */
export function useLaneCycles(laneCount: number) {
  const [laneCycles, setLaneCycles] = useState<number[]>(() => Array(laneCount).fill(0));

  const advanceLane = useCallback((lane: number) => {
    setLaneCycles((current) => current.map((cycle, index) => (index === lane ? cycle + 1 : cycle)));
  }, []);

  return { laneCycles, advanceLane };
}
