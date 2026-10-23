"use client";

import React, { useRef, useState } from "react";
import { Upload, FileText, FileSpreadsheet, File as FileIcon, CheckCircle2 } from "lucide-react";

const VALID_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md"];

interface UploadCardProps {
  selectedFile: File | null;
  onFileSelect: (file: File) => void;
  onClearFile: () => void;
  onError: (message: string) => void;
  maxUploadMb: number;
  isProcessing: boolean;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileKind(name: string): { label: string; Icon: typeof FileIcon } {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return { label: "PDF document", Icon: FileText };
  if (ext === "docx") return { label: "Word document", Icon: FileText };
  if (ext === "xlsx" || ext === "xls" || ext === "csv") return { label: "Spreadsheet", Icon: FileSpreadsheet };
  return { label: "Text file", Icon: FileIcon };
}

export function UploadCard({
  selectedFile,
  onFileSelect,
  onClearFile,
  onError,
  maxUploadMb,
  isProcessing,
}: UploadCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndSetFile = (file: File) => {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!VALID_EXTENSIONS.includes(ext)) {
      onError("This type of file can't be translated. Please choose a PDF, Word (.docx), Excel (.xlsx or .xls), CSV, or text (.txt or .md) file.");
      return;
    }
    if (file.size === 0) {
      onError(`"${file.name}" is empty. Please choose a file that has content.`);
      return;
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      onError(`"${file.name}" is too large (${formatFileSize(file.size)}). The largest file you can upload is ${maxUploadMb} MB.`);
      return;
    }
    onFileSelect(file);
  };

  const openPicker = () => {
    if (!isProcessing) fileInputRef.current?.click();
  };

  const input = (
    <input
      ref={fileInputRef}
      type="file"
      accept={VALID_EXTENSIONS.join(",")}
      className="hidden"
      onChange={(e) => {
        if (e.target.files?.length) validateAndSetFile(e.target.files[0]);
        e.target.value = ""; // allow choosing the same file again
      }}
      disabled={isProcessing}
    />
  );

  if (selectedFile) {
    const { label, Icon } = fileKind(selectedFile.name);
    return (
      <div className="rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4 flex items-center gap-4">
        {input}
        <Icon className="w-8 h-8 text-emerald-600 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-base font-medium text-neutral-900 truncate">{selectedFile.name}</p>
          <p className="text-sm text-neutral-600 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" />
            {label} · {formatFileSize(selectedFile.size)}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 shrink-0">
          <button
            type="button"
            onClick={openPicker}
            disabled={isProcessing}
            className="h-10 px-4 rounded-lg border border-neutral-300 bg-white text-sm font-medium text-neutral-800 hover:bg-neutral-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 disabled:opacity-50"
          >
            Change file
          </button>
          <button
            type="button"
            onClick={onClearFile}
            disabled={isProcessing}
            className="h-10 px-4 rounded-lg text-sm font-medium text-neutral-600 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 disabled:opacity-50"
          >
            Remove
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {input}
      <button
        type="button"
        onClick={openPicker}
        onDragOver={(e) => {
          e.preventDefault();
          if (!isProcessing) setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (!isProcessing && e.dataTransfer.files?.length) validateAndSetFile(e.dataTransfer.files[0]);
        }}
        disabled={isProcessing}
        className={`w-full rounded-xl border-2 border-dashed p-8 sm:p-12 text-center transition cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
          isDragging
            ? "border-emerald-600 bg-emerald-50"
            : "border-neutral-300 bg-neutral-50 hover:border-emerald-600 hover:bg-emerald-50"
        }`}
      >
        <Upload className="w-10 h-10 mx-auto text-emerald-600 mb-3" aria-hidden="true" />
        <span className="block text-base font-semibold text-neutral-900">
          Click here to choose a file
        </span>
        <span className="block text-sm text-neutral-600 mt-1">or drag and drop it into this box</span>
        <span className="block text-sm text-neutral-500 mt-4">
          PDF, Word, Excel, CSV or text files · up to {maxUploadMb} MB
        </span>
      </button>
    </>
  );
}
