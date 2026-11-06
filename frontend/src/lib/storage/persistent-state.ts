import { useEffect, useState } from "react";

/** Returns `fallback` when storage is missing, blocked, corrupt, or fails validation. */
export function readPersistentState<T>(key: string, fallback: T, validate: (value: unknown) => value is T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return validate(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

/** Returns false when the write is blocked (private mode) or over quota; the app keeps working. */
export function writePersistentState<T>(key: string, value: T): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    console.warn(`Could not persist ${key}:`, error);
    return false;
  }
}

export function usePersistentState<T>(key: string, defaultValue: T, validate: (value: unknown) => value is T) {
  const [value, setValue] = useState<T>(() => readPersistentState(key, defaultValue, validate));

  useEffect(() => {
    writePersistentState(key, value);
  }, [key, value]);

  return [value, setValue] as const;
}

export function isString(value: unknown): value is string {
  return typeof value === "string";
}
