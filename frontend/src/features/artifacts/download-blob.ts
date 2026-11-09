// Safari and Firefox can cancel a download when its object URL is revoked synchronously after click().
const OBJECT_URL_RELEASE_DELAY_MS = 1000;

export function downloadBlob(blob: Blob, fileName: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  anchor.hidden = true;
  document.body.appendChild(anchor);
  anchor.click();
  window.setTimeout(() => {
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  }, OBJECT_URL_RELEASE_DELAY_MS);
}
