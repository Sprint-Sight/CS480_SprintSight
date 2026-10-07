import { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";

/**
 * Custom render function for testing React components.
 * Wraps components in required providers (if any are added in future).
 */
export function renderComponent(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, options);
}

/**
 * Mock sessionStorage for testing auth state and role-based features.
 */
export function mockSessionStorage(data: Record<string, string>) {
  const store: Record<string, string> = data;
  Object.defineProperty(window, "sessionStorage", {
    value: {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      clear: () => {
        Object.keys(store).forEach((key) => delete store[key]);
      },
    },
    writable: true,
  });
  return store;
}

/**
 * Mock API responses for testing data fetching.
 */
export function mockFetch(responses: Record<string, { ok: boolean; data?: unknown; error?: string }>) {
  global.fetch = vi.fn((input: string | URL | Request, _init?: RequestInit) => {
    let url: string;
    if (typeof input === "string") {
      url = input;
    } else if (input instanceof URL) {
      url = input.toString();
    } else {
      url = input.url;
    }

    const path = new URL(url).pathname;
    const matchedKey = Object.keys(responses).find(
      (key) => path.includes(key) || url.includes(key)
    );
    const response = matchedKey ? responses[matchedKey] : { ok: false, error: "Not mocked" };

    return Promise.resolve(
      new Response(JSON.stringify(response.data || { error: response.error }), {
        status: response.ok ? 200 : 404,
        headers: { "Content-Type": "application/json" },
      })
    );
  });
}

/**
 * Reset all mocks after tests.
 */
export function resetMocks() {
  vi.clearAllMocks();
}
