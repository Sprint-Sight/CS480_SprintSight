import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadExportedFile } from "@/features/assessment/assessment-export-api";
import { API_BASE_URL, ApiError, apiRequest } from "@/lib/api/client";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

describe("downloadExportedFile", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(apiRequest).mockReset();
    URL.createObjectURL = vi.fn(() => "blob:export-url");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("starts the download and releases the URL only after a delay (Safari/Firefox safe)", async () => {
    vi.mocked(apiRequest).mockResolvedValue(new Blob(["csv"]));
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe("report.csv");
      expect(document.body.contains(this)).toBe(true);
    });

    await downloadExportedFile("/exports/abc.csv", "report.csv");

    const baseUrl = API_BASE_URL.replace(/\/api\/v1$/, "");
    expect(apiRequest).toHaveBeenCalledWith(`${baseUrl}/exports/abc.csv`, { responseType: "blob" });
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1000);

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export-url");
  });

  it("explains an expired link instead of showing the raw error", async () => {
    vi.mocked(apiRequest).mockRejectedValue(new ApiError("Not found.", { status: 404 }));

    await expect(downloadExportedFile("/exports/old.pdf", "old.pdf")).rejects.toThrow(
      "Failed to download file. The download link may have expired.",
    );
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
