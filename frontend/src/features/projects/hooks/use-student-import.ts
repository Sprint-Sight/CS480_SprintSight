"use client";

import { useState, useCallback } from "react";
import { ApiError, apiRequest, getErrorMessage } from "@/lib/api/client";

export interface StudentImportResult {
  course_id: string;
  total_rows: number;
  created_students: number;
  enrolled_students: number;
  already_enrolled: number;
}

export interface StudentImportError {
  code: string;
  message: string;
  details?: string[];
}

export interface ParsedStudentRow {
  rowNumber: number;
  name: string;
  studentId: string;
  email: string;
  valid: boolean;
  errorMessage?: string;
}

const REQUIRED_HEADERS = ["student_name", "student_id", "student_email"];

export function useStudentImport() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<StudentImportError | null>(null);
  const [parsedRows, setParsedRows] = useState<ParsedStudentRow[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);

  const parseCSV = useCallback(async (file: File): Promise<ParsedStudentRow[]> => {
    const content = await file.text();
    const lines = content.trim().split("\n");

    if (lines.length === 0) {
      throw { code: "EMPTY_FILE", message: "CSV file is empty." };
    }

    // Parse headers
    const headerLine = lines[0];
    const headers = headerLine.split(",").map((h) => h.trim().toLowerCase());

    if (!REQUIRED_HEADERS.every((h) => headers.includes(h))) {
      throw {
        code: "INVALID_HEADERS",
        message: "CSV headers must be student_name, student_id, and student_email.",
        details: [`Found headers: ${headers.join(", ")}`],
      };
    }

    const rows: ParsedStudentRow[] = [];
    const seenNumbers = new Set<string>();
    const seenEmails = new Set<string>();

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = line.split(",").map((p) => p.trim());
      const nameIdx = headers.indexOf("student_name");
      const idIdx = headers.indexOf("student_id");
      const emailIdx = headers.indexOf("student_email");

      const name = parts[nameIdx] || "";
      const studentId = parts[idIdx] || "";
      const email = parts[emailIdx] || "";

      const rowNumber = i + 1;

      // Validate row
      if (!name || !studentId || !email) {
        rows.push({
          rowNumber,
          name,
          studentId,
          email,
          valid: false,
          errorMessage: "Missing required field (name, student_id, or email).",
        });
        continue;
      }

      if (!/^\d+$/.test(studentId)) {
        rows.push({
          rowNumber,
          name,
          studentId,
          email,
          valid: false,
          errorMessage: "student_id must be a number.",
        });
        continue;
      }

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        rows.push({
          rowNumber,
          name,
          studentId,
          email,
          valid: false,
          errorMessage: "Invalid email format.",
        });
        continue;
      }

      if (seenNumbers.has(studentId)) {
        rows.push({
          rowNumber,
          name,
          studentId,
          email,
          valid: false,
          errorMessage: `Duplicate student_id ${studentId}.`,
        });
        continue;
      }

      if (seenEmails.has(email.toLowerCase())) {
        rows.push({
          rowNumber,
          name,
          studentId,
          email,
          valid: false,
          errorMessage: `Duplicate student_email ${email}.`,
        });
        continue;
      }

      seenNumbers.add(studentId);
      seenEmails.add(email.toLowerCase());

      rows.push({
        rowNumber,
        name,
        studentId,
        email,
        valid: true,
      });
    }

    return rows;
  }, []);

  const validateAndPreview = useCallback(
    async (file: File): Promise<ParsedStudentRow[]> => {
      setError(null);
      setIsLoading(true);

      try {
        if (!file.name.toLowerCase().endsWith(".csv")) {
          throw { code: "INVALID_FILE_TYPE", message: "Please upload a CSV file." };
        }

        if (file.size > 10 * 1024 * 1024) {
          throw { code: "FILE_TOO_LARGE", message: "CSV file must be smaller than 10 MB." };
        }

        const rows = await parseCSV(file);

        if (rows.length === 0) {
          throw { code: "NO_VALID_ROWS", message: "CSV contains no valid student rows." };
        }

        setCsvFile(file);
        setParsedRows(rows);

        return rows;
      } catch (err) {
        const importError: StudentImportError =
          err && typeof err === "object" && "code" in err
            ? (err as StudentImportError)
            : {
                code: "PARSE_ERROR",
                message: getErrorMessage(err, "Failed to parse CSV file."),
              };

        setError(importError);
        setParsedRows([]);
        setCsvFile(null);
        throw importError;
      } finally {
        setIsLoading(false);
      }
    },
    [parseCSV]
  );

  const submitImport = useCallback(
    async (courseId: string): Promise<StudentImportResult> => {
      if (!csvFile) {
        throw new Error("No CSV file selected.");
      }

      setIsLoading(true);
      setError(null);

      try {
        const formData = new FormData();
        formData.append("file", csvFile);

        const result = await apiRequest<StudentImportResult>(
          `/courses/${encodeURIComponent(courseId)}/students/import`,
          { method: "POST", body: formData },
        );

        // Clear state on success
        setCsvFile(null);
        setParsedRows([]);

        return result;
      } catch (err) {
        const importError: StudentImportError =
          err instanceof ApiError
            ? {
                code: err.code,
                message: err.message,
                details: err.details.length > 0 ? err.details : undefined,
              }
            : {
                code: "IMPORT_ERROR",
                message: getErrorMessage(err, "Failed to import students."),
              };

        setError(importError);
        throw importError;
      } finally {
        setIsLoading(false);
      }
    },
    [csvFile]
  );

  const clearState = useCallback(() => {
    setCsvFile(null);
    setParsedRows([]);
    setError(null);
  }, []);

  return {
    isLoading,
    error,
    parsedRows,
    csvFile,
    validateAndPreview,
    submitImport,
    clearState,
  };
}
