/**
 * Holds only the user's UI selection (project, course, sprint). Ingestion data is
 * never stored here; it comes from the query cache.
 */
import { readPersistentState, writePersistentState } from "@/lib/storage/persistent-state";

export const SCOPE_STORAGE_KEY = "sprintsight-scope-v2";
export const SEMESTER_STORAGE_KEY = "sprintsight-semester-v2";
const LEGACY_INGESTION_KEY = "sprintsight-ingestion-state-v1";
export const INGESTION_SCOPE_EVENT = "sprintsight-ingestion-updated";

export type IngestionScope = {
  selectedProjectId: string;
  selectedCourseId: string;
  selectedSprintId: string;
};

const DEFAULT_SCOPE: IngestionScope = {
  selectedProjectId: "",
  selectedCourseId: "",
  selectedSprintId: "sprint-1",
};

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

/** Copies the selection from the retired ingestion blob once, then removes that key. */
export function migrateLegacyScope() {
  if (typeof window === "undefined") return;
  try {
    const legacyRaw = window.localStorage.getItem(LEGACY_INGESTION_KEY);
    if (legacyRaw === null) return;
    if (window.localStorage.getItem(SCOPE_STORAGE_KEY) === null) {
      const legacy = (JSON.parse(legacyRaw) ?? {}) as Record<string, unknown>;
      const migrated: IngestionScope = {
        selectedProjectId: asString(legacy.selectedProjectId),
        selectedCourseId: asString(legacy.selectedCourseId),
        selectedSprintId: asString(legacy.selectedSprintId) || DEFAULT_SCOPE.selectedSprintId,
      };
      window.localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify(migrated));
    }
    window.localStorage.removeItem(LEGACY_INGESTION_KEY);
  } catch {
    // Storage blocked or corrupt legacy value: the user simply starts with no selection.
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readScope(): IngestionScope {
  if (typeof window === "undefined") return DEFAULT_SCOPE;
  migrateLegacyScope();
  const parsed = readPersistentState<Record<string, unknown> | null>(SCOPE_STORAGE_KEY, null, (value): value is Record<string, unknown> | null => value === null || isRecord(value));
  return {
    selectedProjectId: asString(parsed?.selectedProjectId),
    selectedCourseId: asString(parsed?.selectedCourseId),
    selectedSprintId: asString(parsed?.selectedSprintId) || DEFAULT_SCOPE.selectedSprintId,
  };
}

export function writeScope(patch: Partial<IngestionScope>) {
  if (typeof window === "undefined") return;
  const next = { ...readScope(), ...patch };
  if (!writePersistentState(SCOPE_STORAGE_KEY, next)) return;
  window.dispatchEvent(new CustomEvent(INGESTION_SCOPE_EVENT));
}

export function subscribeScope(listener: () => void) {
  window.addEventListener(INGESTION_SCOPE_EVENT, listener);
  return () => window.removeEventListener(INGESTION_SCOPE_EVENT, listener);
}
