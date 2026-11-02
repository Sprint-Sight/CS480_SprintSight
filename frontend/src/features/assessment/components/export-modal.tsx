"use client";

import { Download, FileText, X, Loader2, Check, AlertCircle } from "lucide-react";
import type { ExportPreviewData } from "@/features/assessment/assessment-export-api";

type ExportModalProps = {
  isOpen: boolean;
  onClose: () => void;
  previewData: ExportPreviewData | null;
  isLoading: boolean;
  isExporting: boolean;
  selectedFormat: "pdf" | "csv" | null;
  error: string | null;
  onExportPDF: () => void;
  onExportCSV: () => void;
};

export function ExportModal({
  isOpen,
  onClose,
  previewData,
  isLoading,
  isExporting,
  selectedFormat,
  error,
  onExportPDF,
  onExportCSV,
}: ExportModalProps) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        role="presentation"
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white shadow-lg">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-slate-900">Export Assessment Report</h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4">
            {isLoading && (
              <div className="flex flex-col items-center justify-center gap-3 py-8">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                <p className="text-sm text-slate-600">Loading preview...</p>
              </div>
            )}

            {error && !isExporting && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
                <div className="flex gap-3">
                  <AlertCircle className="h-5 w-5 flex-shrink-0 text-rose-600" />
                  <div>
                    <p className="text-sm font-medium text-rose-900">Export Error</p>
                    <p className="mt-1 text-sm text-rose-800">{error}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="mt-4 w-full rounded-lg bg-rose-100 px-3 py-2 text-sm font-medium text-rose-900 hover:bg-rose-200"
                >
                  Close
                </button>
              </div>
            )}

            {previewData && !isExporting && (
              <>
                <div className="space-y-4">
                  {/* Preview Stats */}
                  <div className="rounded-lg bg-blue-50 p-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs font-medium uppercase text-slate-600">
                          Records
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {previewData.recordCount}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium uppercase text-slate-600">
                          File Size
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {previewData.estimatedSize}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 border-t border-blue-100 pt-3">
                      <p className="text-xs text-slate-600">
                        Estimated generation time: {previewData.estimatedDuration}
                      </p>
                    </div>
                  </div>

                  {/* Format Selection */}
                  <div>
                    <p className="mb-3 text-sm font-medium text-slate-900">Select Format</p>
                    <div className="grid grid-cols-2 gap-3">
                      {/* PDF Button */}
                      <button
                        type="button"
                        onClick={onExportPDF}
                        disabled={isExporting}
                        className="rounded-lg border-2 border-slate-200 px-4 py-3 transition-all hover:border-blue-500 hover:bg-blue-50 disabled:opacity-50"
                      >
                        <FileText className="mx-auto h-6 w-6 text-blue-600" />
                        <p className="mt-2 text-sm font-medium text-slate-900">PDF</p>
                        <p className="text-xs text-slate-600">With watermark</p>
                      </button>

                      {/* CSV Button */}
                      <button
                        type="button"
                        onClick={onExportCSV}
                        disabled={isExporting}
                        className="rounded-lg border-2 border-slate-200 px-4 py-3 transition-all hover:border-green-500 hover:bg-green-50 disabled:opacity-50"
                      >
                        <FileText className="mx-auto h-6 w-6 text-green-600" />
                        <p className="mt-2 text-sm font-medium text-slate-900">CSV</p>
                        <p className="text-xs text-slate-600">Spreadsheet format</p>
                      </button>
                    </div>
                  </div>

                  {/* Info */}
                  <div className="rounded-lg bg-amber-50 p-3">
                    <p className="text-xs text-amber-900">
                      ℹ️ Download links expire in 1 hour. Files include instructor watermark.
                    </p>
                  </div>
                </div>
              </>
            )}

            {isExporting && (
              <div className="flex flex-col items-center justify-center gap-3 py-8">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                <p className="text-sm text-slate-600">
                  Generating {selectedFormat?.toUpperCase()}...
                </p>
              </div>
            )}

            {/* Success State */}
            {/* This is shown after export completes, but we close modal after 2s */}
          </div>
        </div>
      </div>
    </>
  );
}
