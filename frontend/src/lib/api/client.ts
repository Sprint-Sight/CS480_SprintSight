import { getSessionToken, signOut } from "@/lib/auth/session";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export const NETWORK_ERROR_MESSAGE =
  "Can't reach SprintSight. Check your connection and try again.";
export const SERVER_ERROR_MESSAGE =
  "Something went wrong on our side. Please try again in a moment.";
export const FORBIDDEN_MESSAGE = "You don't have permission to do that.";
export const NOT_FOUND_MESSAGE = "We couldn't find what you were looking for.";
export const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please sign in again.";
export const NOT_SIGNED_IN_MESSAGE = "You are not signed in. Please log in again.";
export const GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again.";

export type ApiRequestOptions = Omit<RequestInit, "signal"> & {
  /** Attach the session's bearer token (default true). Public auth endpoints pass false. */
  auth?: boolean;
  /** "blob" for file downloads; JSON (or text) otherwise. */
  responseType?: "json" | "blob";
  signal?: AbortSignal;
};

type ApiErrorInit = {
  status: number;
  code?: string;
  fieldErrors?: Record<string, string>;
  details?: string[];
};

/** Every failed request surfaces as an ApiError with a message that is safe to show users. */
export class ApiError extends Error {
  /** HTTP status, or 0 when the request never reached the server. */
  readonly status: number;
  readonly code: string;
  /** Field name -> message, from FastAPI 422 validation errors. */
  readonly fieldErrors: Record<string, string>;
  /** Individual problems (e.g. CSV row errors) when the backend sends a list. */
  readonly details: string[];

  constructor(message: string, { status, code, fieldErrors = {}, details = [] }: ApiErrorInit) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code ?? (status === 0 ? "network_error" : `http_${status}`);
    this.fieldErrors = fieldErrors;
    this.details = details;
  }
}

export type ParsedErrorBody = {
  message: string | null;
  code: string | null;
  fieldErrors: Record<string, string>;
  details: string[];
};

type ValidationIssue = { loc?: unknown; msg?: unknown };

function humanizeField(field: string) {
  return field.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

/**
 * The backend's HTTPException handler runs `str(detail)`, so a list or dict detail
 * arrives as a Python repr such as "['Row 2: ...', 'Row 3: ...']". Recover the items.
 */
function parsePythonReprList(text: string): string[] | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return null;
  const items = [...trimmed.slice(1, -1).matchAll(/'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g)].map(
    (match) => (match[1] ?? match[2]).replace(/\\(['"\\])/g, "$1"),
  );
  return items.length > 0 ? items : null;
}

function parsePythonReprMessage(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return null;
  const match = trimmed.match(/['"]message['"]:\s*(['"])((?:\\[\s\S]|(?!\1)[\s\S])*)\1/);
  return match ? match[2].replace(/\\(['"\\])/g, "$1") : null;
}

function summarizeList(items: string[]) {
  return items.length === 1 ? items[0] : `${items.length} problems were found: ${items[0]}`;
}

/**
 * Normalises any backend error body: the app's `{ error: { code, message } }`, a
 * string `detail`, FastAPI's 422 `{ detail: [{ loc, msg }] }`, or a Python-repr
 * list/dict inside `error.message`. Never returns raw JSON.
 */
export function parseErrorBody(body: unknown): ParsedErrorBody {
  const result: ParsedErrorBody = { message: null, code: null, fieldErrors: {}, details: [] };
  if (!body || typeof body !== "object") return result;
  const payload = body as {
    detail?: unknown;
    message?: unknown;
    error?: { code?: unknown; message?: unknown };
  };

  if (typeof payload.error?.code === "string") result.code = payload.error.code;

  if (typeof payload.error?.message === "string" && payload.error.message.trim()) {
    const raw = payload.error.message;
    const listItems = parsePythonReprList(raw);
    if (listItems) {
      result.details = listItems;
      result.message = summarizeList(listItems);
    } else {
      result.message = parsePythonReprMessage(raw) ?? raw;
    }
    return result;
  }

  if (typeof payload.detail === "string" && payload.detail.trim()) {
    result.message = payload.detail;
    return result;
  }

  if (Array.isArray(payload.detail)) {
    payload.detail.forEach((item) => {
      if (typeof item === "string") {
        result.details.push(item);
        return;
      }
      const issue = item as ValidationIssue;
      if (typeof issue?.msg !== "string") return;
      const message = issue.msg.replace(/^Value error,\s*/i, "");
      const location = Array.isArray(issue.loc) ? issue.loc.filter((part) => part !== "body") : [];
      const field = location.at(-1);
      if (typeof field === "string") {
        result.fieldErrors[field] = message;
        result.details.push(`${humanizeField(field)}: ${message}`);
      } else {
        result.details.push(message);
      }
    });
    if (result.details.length > 0) result.message = result.details.join(" ");
    return result;
  }

  if (payload.detail && typeof payload.detail === "object") {
    const nested = (payload.detail as { message?: unknown }).message;
    if (typeof nested === "string" && nested.trim()) result.message = nested;
    return result;
  }

  if (typeof payload.message === "string" && payload.message.trim())
    result.message = payload.message;
  return result;
}

function messageForStatus(status: number, parsedMessage: string | null) {
  if (parsedMessage) return parsedMessage;
  if (status >= 500) return SERVER_ERROR_MESSAGE;
  if (status === 401) return SESSION_EXPIRED_MESSAGE;
  if (status === 403) return FORBIDDEN_MESSAGE;
  if (status === 404) return NOT_FOUND_MESSAGE;
  return GENERIC_ERROR_MESSAGE;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Readable message for anything thrown by a request or by app code. */
export function getErrorMessage(error: unknown, fallback = GENERIC_ERROR_MESSAGE): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError && /fetch|network/i.test(error.message))
    return NETWORK_ERROR_MESSAGE;
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

/**
 * Headers carrying the session's bearer token, for requests that cannot go through
 * apiRequest (e.g. the assessment progress event stream). Throws when signed out.
 */
export function buildAuthHeaders(headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  const token = getSessionToken();
  if (!token) throw new ApiError(NOT_SIGNED_IN_MESSAGE, { status: 401, code: "not_signed_in" });
  if (!result.has("Authorization")) result.set("Authorization", `Bearer ${token}`);
  return result;
}

function resolveUrl(path: string) {
  return /^https?:\/\//i.test(path) ? path : `${API_BASE_URL}${path}`;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { auth = true, responseType = "json", ...init } = options;
  const headers = auth ? buildAuthHeaders(init.headers) : new Headers(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(resolveUrl(path), {
      ...init,
      cache: init.method && init.method !== "GET" ? init.cache : (init.cache ?? "no-store"),
      headers,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(NETWORK_ERROR_MESSAGE, { status: 0 });
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let payload: unknown = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null; // HTML error pages and plain text are never shown to users.
    }
    const parsed = parseErrorBody(payload);

    if (response.status === 401 && auth && typeof window !== "undefined") {
      signOut();
      window.location.href = "/login";
    }

    throw new ApiError(messageForStatus(response.status, parsed.message), {
      status: response.status,
      code: parsed.code ?? undefined,
      fieldErrors: parsed.fieldErrors,
      details: parsed.details,
    });
  }

  if (response.status === 204) return null as T;
  if (responseType === "blob") return (await response.blob()) as T;

  const text = await response.text();
  if (!text) return null as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as T;
  }
}
