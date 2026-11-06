/// <reference types="vitest/globals" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  API_BASE_URL,
  ApiError,
  FORBIDDEN_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  NOT_SIGNED_IN_MESSAGE,
  SERVER_ERROR_MESSAGE,
  apiRequest,
  buildAuthHeaders,
  getErrorMessage,
  parseErrorBody,
} from "@/lib/api/client";
import { getSession, setSession } from "@/lib/auth/session";

const signedIn = {
  token: "token-123",
  user: { id: "u1", role: "instructor" as const, email: "prof@example.com", fullName: "Prof" },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestHeaders(fetchMock: ReturnType<typeof mockFetch>) {
  const init = fetchMock.mock.calls[0][1] ?? {};
  return new Headers(init.headers);
}

describe("parseErrorBody", () => {
  it("reads the app's { error: { code, message } } shape", () => {
    expect(
      parseErrorBody({ error: { code: "http_409", message: "Email already exists." } }),
    ).toMatchObject({
      message: "Email already exists.",
      code: "http_409",
    });
  });

  it("maps FastAPI 422 validation arrays to field errors and a readable sentence", () => {
    const parsed = parseErrorBody({
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
        },
      ],
    });
    expect(parsed.fieldErrors).toEqual({ password: "String should have at least 8 characters" });
    expect(parsed.message).toBe("Password: String should have at least 8 characters");
    expect(parsed.message).not.toContain("{");
  });

  it("recovers a Python-repr list sent through the HTTPException handler", () => {
    const parsed = parseErrorBody({
      error: {
        code: "http_422",
        message: "['Row 2: duplicate student_id 7.', \"Row 3: invalid student's email.\"]",
      },
    });
    expect(parsed.details).toEqual([
      "Row 2: duplicate student_id 7.",
      "Row 3: invalid student's email.",
    ]);
    expect(parsed.message).toBe("2 problems were found: Row 2: duplicate student_id 7.");
  });

  it("recovers the message from a Python-repr dict", () => {
    const parsed = parseErrorBody({
      error: {
        message:
          "{'message': 'CSV headers must be student_name, student_id, and student_email.', 'headers': ['a']}",
      },
    });
    expect(parsed.message).toBe("CSV headers must be student_name, student_id, and student_email.");
  });

  it("handles plain string detail, nested detail objects and unknown bodies", () => {
    expect(parseErrorBody({ detail: "Course not found." }).message).toBe("Course not found.");
    expect(parseErrorBody({ detail: { message: "Nested." } }).message).toBe("Nested.");
    expect(parseErrorBody("<html>Bad Gateway</html>").message).toBeNull();
    expect(parseErrorBody(null).message).toBeNull();
  });
});

describe("apiRequest", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the session's bearer token and parses JSON", async () => {
    setSession(signedIn);
    const fetchMock = mockFetch(jsonResponse({ ok: true }));

    await expect(apiRequest("/courses")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/courses`);
    expect(requestHeaders(fetchMock).get("Authorization")).toBe("Bearer token-123");
  });

  it("omits the token for public endpoints and keeps an explicit Authorization header", async () => {
    const fetchMock = mockFetch(jsonResponse({}));
    await apiRequest("/auth/login", { method: "POST", auth: false, body: "{}" });
    expect(requestHeaders(fetchMock).has("Authorization")).toBe(false);
    expect(requestHeaders(fetchMock).get("Content-Type")).toBe("application/json");

    const meFetch = mockFetch(jsonResponse({}));
    await apiRequest("/auth/me", { auth: false, headers: { Authorization: "Bearer fresh" } });
    expect(requestHeaders(meFetch).get("Authorization")).toBe("Bearer fresh");
  });

  it("rejects before calling the network when signed out", async () => {
    const fetchMock = mockFetch(jsonResponse({}));
    await expect(apiRequest("/courses")).rejects.toMatchObject({
      status: 401,
      message: NOT_SIGNED_IN_MESSAGE,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("turns a 422 into an ApiError with field errors instead of raw JSON", async () => {
    setSession(signedIn);
    mockFetch(
      jsonResponse(
        {
          detail: [{ loc: ["body", "password"], msg: "String should have at least 8 characters" }],
        },
        422,
      ),
    );

    const error = await apiRequest("/users/u1/reset-password", {
      method: "POST",
      body: "{}",
    }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      message: "Password: String should have at least 8 characters",
      fieldErrors: { password: "String should have at least 8 characters" },
    });
  });

  it("uses friendly copy for HTML 5xx pages, empty 403s and network failures", async () => {
    setSession(signedIn);

    mockFetch(new Response("<html>502 Bad Gateway</html>", { status: 502 }));
    await expect(apiRequest("/courses")).rejects.toMatchObject({
      status: 502,
      message: SERVER_ERROR_MESSAGE,
    });

    mockFetch(new Response("", { status: 403 }));
    await expect(apiRequest("/courses")).rejects.toMatchObject({
      status: 403,
      message: FORBIDDEN_MESSAGE,
    });

    mockFetch(new TypeError("Failed to fetch"));
    await expect(apiRequest("/courses")).rejects.toMatchObject({
      status: 0,
      message: NETWORK_ERROR_MESSAGE,
    });
  });

  it("signs out on a 401 from an authenticated request", async () => {
    setSession(signedIn);
    mockFetch(jsonResponse({ error: { code: "http_401", message: "Token expired." } }, 401));
    const location = { href: "/dashboard" };
    vi.stubGlobal("location", location);

    await expect(apiRequest("/courses")).rejects.toMatchObject({
      status: 401,
      message: "Token expired.",
    });
    expect(getSession()).toBeNull();
    expect(location.href).toBe("/login");
  });

  it("returns blobs for downloads and passes absolute URLs through", async () => {
    setSession(signedIn);
    const fetchMock = mockFetch(new Response("file-bytes", { status: 200 }));

    const blob = await apiRequest<Blob>("http://files.example.com/export.csv", {
      responseType: "blob",
    });
    expect(await blob.text()).toBe("file-bytes");
    expect(fetchMock.mock.calls[0][0]).toBe("http://files.example.com/export.csv");
  });

  it("returns null for 204 responses", async () => {
    setSession(signedIn);
    mockFetch(new Response(null, { status: 204 }));
    await expect(apiRequest("/notifications/1/read", { method: "PATCH" })).resolves.toBeNull();
  });
});

describe("getErrorMessage and buildAuthHeaders", () => {
  beforeEach(() => window.localStorage.clear());

  it("prefers ApiError copy, maps fetch TypeErrors, and falls back for unknown values", () => {
    expect(getErrorMessage(new ApiError("Readable.", { status: 400 }))).toBe("Readable.");
    expect(getErrorMessage(new TypeError("Failed to fetch"))).toBe(NETWORK_ERROR_MESSAGE);
    expect(getErrorMessage(new Error("Plain."))).toBe("Plain.");
    expect(getErrorMessage({ detail: [] }, "Fallback.")).toBe("Fallback.");
  });

  it("builds bearer headers for the event stream and throws when signed out", () => {
    expect(() => buildAuthHeaders()).toThrow(NOT_SIGNED_IN_MESSAGE);
    setSession(signedIn);
    expect(buildAuthHeaders().get("Authorization")).toBe("Bearer token-123");
  });
});
