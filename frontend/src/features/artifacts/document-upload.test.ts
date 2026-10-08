import { describe, expect, it } from "vitest";

import { getDocumentFileType, validateDocumentFiles } from "@/features/artifacts/document-upload";

describe("document upload", () => {
  it.each([
    ["report.pdf", "application/pdf", [0x25, 0x50, 0x44, 0x46, 0x2d]],
    [
      "report.docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      [0x50, 0x4b, 0x03, 0x04, 0x00],
    ],
    [
      "slides.pptx",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      [0x50, 0x4b, 0x03, 0x04, 0x00],
    ],
  ])("accepts valid %s files", async (name, mimeType, signature) => {
    const file = new File([new Uint8Array(signature)], name, { type: mimeType });

    await expect(validateDocumentFiles([file])).resolves.toBeUndefined();
  });

  it("rejects unsupported formats and invalid file signatures", async () => {
    const textFile = new File(["text"], "notes.txt", { type: "text/plain" });
    const invalidPdf = new File(["not a pdf"], "report.pdf", { type: "application/pdf" });

    await expect(validateDocumentFiles([textFile])).rejects.toThrow("Upload PDF, DOCX, or PPTX");
    await expect(validateDocumentFiles([invalidPdf])).rejects.toThrow("valid PDF file signature");
  });

  it("uses the document filename to display its type", () => {
    expect(getDocumentFileType("PRESENTATION.PPTX")).toBe("PPTX");
    expect(getDocumentFileType("notes.docx")).toBe("DOCX");
    expect(getDocumentFileType("unknown.bin")).toBe("Document");
  });
});
