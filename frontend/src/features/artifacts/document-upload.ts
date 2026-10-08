import type { DocumentArtifact } from "@/features/artifacts/types";

const MAX_FILE_SIZE = 25 * 1024 * 1024;
const MAX_TOTAL_SIZE = 100 * 1024 * 1024;

const SUPPORTED_UPLOADS = {
  ".pdf": { mimeType: "application/pdf", label: "PDF" },
  ".docx": {
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    label: "DOCX",
  },
  ".pptx": {
    mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    label: "PPTX",
  },
} as const;

function getFileExtension(fileName: string): string {
  return fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
}

function isSupportedExtension(extension: string): extension is keyof typeof SUPPORTED_UPLOADS {
  return Object.prototype.hasOwnProperty.call(SUPPORTED_UPLOADS, extension);
}

export function getDocumentFileType(fileName: string): DocumentArtifact["fileType"] {
  const extension = getFileExtension(fileName);
  if (extension === ".doc") return "DOC";
  if (extension === ".txt") return "TXT";
  if (extension === ".md") return "MD";
  return isSupportedExtension(extension) ? SUPPORTED_UPLOADS[extension].label : "Document";
}

export async function validateDocumentFiles(files: File[]): Promise<void> {
  for (const file of files) {
    const extension = getFileExtension(file.name);
    if (!isSupportedExtension(extension)) {
      throw new Error(`${file.name} is not a supported format. Upload PDF, DOCX, or PPTX files.`);
    }
    const supportedUpload = SUPPORTED_UPLOADS[extension];
    const allowedMimeTypes = [
      supportedUpload.mimeType,
      "application/octet-stream",
      ...(extension === ".pdf" ? [] : ["application/zip", "application/x-zip-compressed"]),
    ];
    if (
      file.type &&
      !allowedMimeTypes.includes(file.type)
    ) {
      throw new Error(`${file.name} has an unexpected file type.`);
    }
    if (file.size > MAX_FILE_SIZE) {
      throw new Error(`${file.name} is larger than the 25 MB per-file limit.`);
    }

    const header = new Uint8Array(await file.slice(0, 5).arrayBuffer());
    const hasPdfSignature =
      extension === ".pdf" &&
      new TextDecoder().decode(header) === "%PDF-";
    const hasOfficeZipSignature =
      (extension === ".docx" || extension === ".pptx") &&
      header[0] === 0x50 &&
      header[1] === 0x4b;
    if (!hasPdfSignature && !hasOfficeZipSignature) {
      throw new Error(`${file.name} does not contain a valid ${supportedUpload.label} file signature.`);
    }
  }

  if (files.reduce((total, file) => total + file.size, 0) > MAX_TOTAL_SIZE) {
    throw new Error("The total upload size must be 100 MB or smaller.");
  }
}
