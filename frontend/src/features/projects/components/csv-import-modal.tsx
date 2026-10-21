"use client";

import React, { useState, useRef, useEffect } from "react";
import { Upload, X, AlertCircle, CheckCircle2, FileText } from "lucide-react";
import type { ParsedStudentRow, StudentImportResult, StudentImportError } from "@/features/projects/hooks/use-student-import";

type ImportStep = "upload" | "preview" | "importing" | "success" | "error";

interface CSVImportModalProps {
  isOpen: boolean;
  courseId: string;
  courseName: string;
  onClose: () => void;
  onValidatePreview: (file: File) => Promise<ParsedStudentRow[]>;
  onSubmit: (courseId: string) => Promise<StudentImportResult>;
  isLoading: boolean;
  error: StudentImportError | null;
  parsedRows: ParsedStudentRow[];
}

export function CSVImportModal({
  isOpen,
  courseId,
  courseName,
  onClose,
  onValidatePreview,
  onSubmit,
  isLoading,
  error,
  parsedRows,
}: CSVImportModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<ImportStep>("upload");
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<StudentImportResult | null>(null);
  const [parseError, setParseError] = useState<StudentImportError | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setStep("upload");
      setSelectedFile(null);
      setParseError(null);
      setImportResult(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const validRowCount = parsedRows.filter((r) => r.valid).length;
  const invalidRowCount = parsedRows.filter((r) => !r.valid).length;

  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files?.[0]) {
      await handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      void handleFile(e.target.files[0]);
    }
  };

  const handleFile = async (file: File) => {
    setSelectedFile(file);
    setParseError(null);
    setStep("preview");

    try {
      await onValidatePreview(file);
    } catch (err) {
      const importError = err as StudentImportError;
      setParseError(importError);
      setStep("error");
    }
  };

  const handleStartImport = async () => {
    setStep("importing");
    try {
      const result = await onSubmit(courseId);
      setImportResult(result);
      setStep("success");
    } catch (err) {
      const importError = err as StudentImportError;
      setParseError(importError);
      setStep("error");
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setParseError(null);
    setStep("upload");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Bulk Import Students</h2>
            <p className="text-sm text-slate-500">Course: {courseName}</p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isLoading}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4">
          {step === "upload" && (
            <div className="space-y-4">
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`rounded-xl border-2 border-dashed px-6 py-12 text-center transition ${
                  dragActive ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-slate-50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileInputChange}
                  className="hidden"
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  className="mx-auto mb-3 inline-flex items-center justify-center rounded-lg bg-blue-100 p-3 text-blue-700 transition hover:bg-blue-200 disabled:opacity-50"
                >
                  <Upload className="h-6 w-6" />
                </button>
                <p className="font-medium text-slate-900">Drag and drop your CSV file here</p>
                <p className="text-sm text-slate-500">or click to browse your computer</p>
                <p className="mt-2 text-xs text-slate-400">CSV must include columns: student_name, student_id, student_email</p>
              </div>

              <div className="rounded-lg bg-blue-50 p-4">
                <h3 className="mb-2 text-sm font-medium text-blue-900">CSV Format Requirements</h3>
                <ul className="space-y-1 text-sm text-blue-800">
                  <li>• Required columns: <code className="font-mono bg-blue-100 px-2 py-1 rounded">student_name</code>, <code className="font-mono bg-blue-100 px-2 py-1 rounded">student_id</code>, <code className="font-mono bg-blue-100 px-2 py-1 rounded">student_email</code></li>
                  <li>• student_id must be a positive integer</li>
                  <li>• Each student_id and student_email must be unique within the file</li>
                  <li>• Maximum 5000 rows, 10 MB file size</li>
                  <li>• File must be UTF-8 encoded</li>
                </ul>
              </div>
            </div>
          )}

          {step === "preview" && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-lg bg-slate-50 p-4">
                <FileText className="h-5 w-5 text-slate-400" />
                <div className="flex-1">
                  <p className="font-medium text-slate-900">{selectedFile?.name}</p>
                  <p className="text-sm text-slate-500">{((selectedFile?.size || 0) / 1024).toFixed(2)} KB</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-slate-200 bg-white p-3 text-center">
                  <p className="text-2xl font-bold text-slate-900">{validRowCount}</p>
                  <p className="text-sm text-slate-600">Valid rows</p>
                </div>
                {invalidRowCount > 0 && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-center">
                    <p className="text-2xl font-bold text-amber-900">{invalidRowCount}</p>
                    <p className="text-sm text-amber-700">Invalid rows</p>
                  </div>
                )}
              </div>

              {invalidRowCount > 0 && (
                <div className="max-h-48 overflow-y-auto rounded-lg border border-amber-200 bg-amber-50 p-4">
                  <h3 className="mb-3 flex items-center gap-2 font-medium text-amber-900">
                    <AlertCircle className="h-4 w-4" />
                    Issues Found
                  </h3>
                  <ul className="space-y-2 text-sm text-amber-800">
                    {parsedRows
                      .filter((r) => !r.valid)
                      .map((row) => (
                        <li key={`error-${row.rowNumber}`}>
                          <strong>Row {row.rowNumber}:</strong> {row.errorMessage}
                        </li>
                      ))}
                  </ul>
                </div>
              )}

              <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-slate-700">Row</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-700">Name</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-700">ID</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-700">Email</th>
                      <th className="px-3 py-2 text-center font-medium text-slate-700">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedRows.map((row) => (
                      <tr
                        key={`row-${row.rowNumber}`}
                        className={row.valid ? "border-b border-slate-100" : "border-b border-amber-100 bg-amber-50"}
                      >
                        <td className="px-3 py-2 text-slate-600">{row.rowNumber}</td>
                        <td className="px-3 py-2 text-slate-900">{row.name}</td>
                        <td className="px-3 py-2 font-mono text-slate-600">{row.studentId}</td>
                        <td className="px-3 py-2 text-slate-600">{row.email}</td>
                        <td className="px-3 py-2 text-center">
                          {row.valid ? (
                            <CheckCircle2 className="mx-auto h-4 w-4 text-green-600" />
                          ) : (
                            <AlertCircle className="mx-auto h-4 w-4 text-amber-600" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {step === "importing" && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="mb-4 inline-flex items-center justify-center rounded-full bg-blue-100 p-3">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-300 border-t-blue-600" />
              </div>
              <p className="font-medium text-slate-900">Importing {validRowCount} students...</p>
              <p className="text-sm text-slate-500">This may take a moment.</p>
            </div>
          )}

          {step === "success" && importResult && (
            <div className="space-y-4">
              <div className="flex flex-col items-center justify-center py-8">
                <div className="mb-4 inline-flex items-center justify-center rounded-full bg-green-100 p-3">
                  <CheckCircle2 className="h-8 w-8 text-green-600" />
                </div>
                <p className="text-lg font-semibold text-slate-900">Import Successful!</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                  <p className="text-2xl font-bold text-slate-900">{importResult.created_students}</p>
                  <p className="text-sm text-slate-600">New Accounts Created</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                  <p className="text-2xl font-bold text-slate-900">{importResult.enrolled_students}</p>
                  <p className="text-sm text-slate-600">Newly Enrolled</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                  <p className="text-2xl font-bold text-slate-900">{importResult.already_enrolled}</p>
                  <p className="text-sm text-slate-600">Already Enrolled</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                  <p className="text-2xl font-bold text-slate-900">{importResult.total_rows}</p>
                  <p className="text-sm text-slate-600">Total Rows Processed</p>
                </div>
              </div>

              <div className="rounded-lg bg-green-50 p-4">
                <p className="text-sm text-green-800">
                  Students have been successfully imported into the course. Enrolled students will receive course enrollment notifications.
                </p>
              </div>
            </div>
          )}

          {step === "error" && parseError && (
            <div className="space-y-4">
              <div className="flex flex-col items-center justify-center py-8">
                <div className="mb-4 inline-flex items-center justify-center rounded-full bg-red-100 p-3">
                  <AlertCircle className="h-8 w-8 text-red-600" />
                </div>
                <p className="text-lg font-semibold text-slate-900">Import Failed</p>
              </div>

              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="font-medium text-red-900">{parseError.message}</p>
                {parseError.details && parseError.details.length > 0 && (
                  <ul className="mt-2 space-y-1 text-sm text-red-800">
                    {parseError.details.slice(0, 10).map((detail, idx) => (
                      <li key={idx}>• {detail}</li>
                    ))}
                    {parseError.details.length > 10 && <li>... and {parseError.details.length - 10} more errors</li>}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-6 py-4">
          {step === "upload" && (
            <button
              type="button"
              onClick={handleClose}
              disabled={isLoading}
              className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
            >
              Cancel
            </button>
          )}

          {step === "preview" && (
            <>
              <button
                type="button"
                onClick={handleReset}
                disabled={isLoading}
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
              >
                Choose Different File
              </button>
              <button
                type="button"
                onClick={handleStartImport}
                disabled={isLoading || validRowCount === 0}
                className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Import {validRowCount} Students
              </button>
            </>
          )}

          {step === "success" && (
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800"
            >
              Done
            </button>
          )}

          {step === "error" && (
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition hover:bg-blue-800"
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
