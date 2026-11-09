import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadBlob } from "@/features/artifacts/download-blob";

describe("downloadBlob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    URL.createObjectURL = vi.fn(() => "blob:test-url");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("clicks an attached download link and releases the URL only after a delay", async () => {
    let anchorAttachedDuringClick = false;
    let clickedHref = "";
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      anchorAttachedDuringClick = document.body.contains(this);
      clickedHref = this.href;
      expect(this.download).toBe("report.pdf");
    });

    downloadBlob(new Blob(["pdf"]), "report.pdf");

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(anchorAttachedDuringClick).toBe(true);
    expect(clickedHref).toBe("blob:test-url");
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1000);

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-url");
    expect(document.querySelector('a[download="report.pdf"]')).toBeNull();
  });
});
