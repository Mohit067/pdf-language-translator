"use client";

import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Copy, Check, Download, RotateCcw, Search, Info, ExternalLink } from "lucide-react";

export interface TranslationChunk {
  chunk_id: number;
  page?: number;
  original: string;
  translated: string;
  word_count_original: number;
  word_count_translated: number;
}

export interface TranslationResult {
  job_id: string;
  filename: string;
  output_filename?: string;
  output_format: string;
  pages: number;
  chunk_count: number;
  source_lang: string;
  target_lang: string;
  download_url: string;
  download_original_url?: string;
  original_url?: string;
  translated_url?: string;
  chunks: TranslationChunk[];
  full_original: string;
  full_translated: string;
  engine?: string;
  api_key_required?: boolean;
  download_filename?: string;
  warnings?: string[];
  chunks_truncated?: boolean;
  text_truncated?: boolean; // full_translated is only a preview; fetch full_text_url for everything
  full_text_url?: string;
}

interface ComparisonWorkspaceProps {
  result: TranslationResult;
  onReset: () => void;
  backendUrl: string;
}

const FORMAT_NAMES: Record<string, string> = {
  pdf: "PDF",
  docx: "Word document",
  xlsx: "Excel file",
  csv: "CSV file",
  txt: "text file",
  md: "text file",
};

const linkButton =
  "inline-flex items-center gap-2 h-10 px-3 rounded-lg text-sm font-medium text-neutral-700 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600";

export function ComparisonWorkspace({ result, onReset, backendUrl }: ComparisonWorkspaceProps) {
  const isPdf = result.output_format.toLowerCase() === "pdf";
  const [view, setView] = useState<"document" | "text">(isPdf ? "document" : "text");
  const [showOriginal, setShowOriginal] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Move focus to the success message so screen-reader and keyboard users land on it
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const translatedFileUrl = `${backendUrl}/api/document/${result.job_id}/translated`;
  const originalFileUrl = `${backendUrl}/api/document/${result.job_id}/original`;
  const downloadTranslatedUrl = `${backendUrl}/api/download/${result.job_id}?type=translated`;
  const downloadOriginalUrl = `${backendUrl}/api/download/${result.job_id}?type=original`;
  const formatName = FORMAT_NAMES[result.output_format.toLowerCase()] || "file";

  const query = searchQuery.trim().toLowerCase();
  const visibleChunks = query
    ? result.chunks.filter(
        (c) => c.original.toLowerCase().includes(query) || c.translated.toLowerCase().includes(query)
      )
    : result.chunks;

  const download = (url: string, filename: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const copy = async (text: string, onDone: () => void) => {
    try {
      await navigator.clipboard.writeText(text);
      onDone();
    } catch {
      // clipboard blocked (e.g. non-secure context); nothing else to do
    }
  };

  return (
    <div className="space-y-6">
      {/* Success + main actions */}
      <section className="rounded-2xl border-2 border-emerald-200 bg-white p-6 sm:p-8 space-y-5">
        <div className="flex items-start gap-3">
          <CheckCircle2 className="w-8 h-8 text-emerald-600 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <h2 ref={headingRef} tabIndex={-1} className="text-xl font-semibold text-neutral-900 focus:outline-none">
              Your translation is ready
            </h2>
            <p className="text-base text-neutral-600 break-all">
              {result.filename} · {result.source_lang} → {result.target_lang}
            </p>
          </div>
        </div>

        {result.warnings && result.warnings.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 flex gap-3">
            <Info className="w-5 h-5 shrink-0 text-amber-600" aria-hidden="true" />
            <div className="space-y-1">
              <p className="font-semibold">Please note</p>
              {result.warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => download(downloadTranslatedUrl, result.download_filename || `translated_${result.filename}`)}
            className="flex-1 inline-flex items-center justify-center gap-2 h-12 px-6 rounded-lg bg-emerald-700 text-white text-base font-semibold hover:bg-emerald-800 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2"
          >
            <Download className="w-5 h-5" aria-hidden="true" />
            Download translated {formatName}
          </button>
          <button
            onClick={onReset}
            className="inline-flex items-center justify-center gap-2 h-12 px-6 rounded-lg border border-neutral-300 bg-white text-base font-medium text-neutral-800 hover:bg-neutral-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
          >
            <RotateCcw className="w-5 h-5" aria-hidden="true" />
            Translate another document
          </button>
        </div>

        <div className="flex flex-wrap gap-1 -ml-3">
          <button onClick={() => download(downloadOriginalUrl, result.filename)} className={linkButton}>
            <Download className="w-4 h-4" aria-hidden="true" />
            Download original file
          </button>
          <button
            onClick={async () => {
              let text = result.full_translated;
              if (result.text_truncated && result.full_text_url) {
                const res = await fetch(`${backendUrl}${result.full_text_url}`).catch(() => null);
                if (res?.ok) text = await res.text();
              }
              copy(text, () => { setCopiedAll(true); setTimeout(() => setCopiedAll(false), 2000); });
            }}
            className={linkButton}
          >
            {copiedAll ? <Check className="w-4 h-4 text-emerald-600" aria-hidden="true" /> : <Copy className="w-4 h-4" aria-hidden="true" />}
            {copiedAll ? "Copied!" : "Copy all translated text"}
          </button>
        </div>
      </section>

      {/* Preview */}
      <section className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-6 space-y-4" aria-labelledby="preview-title">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 id="preview-title" className="text-lg font-semibold text-neutral-900">Preview</h2>
          {isPdf && (
            <div className="inline-flex rounded-lg border border-neutral-300 p-1" role="tablist" aria-label="Preview type">
              {(["document", "text"] as const).map((v) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={`h-9 px-4 rounded-md text-sm font-medium cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
                    view === v ? "bg-neutral-900 text-white" : "text-neutral-700 hover:bg-neutral-100"
                  }`}
                >
                  {v === "document" ? "Document" : "Text side by side"}
                </button>
              ))}
            </div>
          )}
        </div>

        {view === "document" && isPdf ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="inline-flex items-center gap-2 text-sm text-neutral-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showOriginal}
                  onChange={(e) => setShowOriginal(e.target.checked)}
                  className="w-4 h-4 accent-emerald-600"
                />
                Show the original next to it
              </label>
              <a href={translatedFileUrl} target="_blank" rel="noopener noreferrer" className={linkButton}>
                <ExternalLink className="w-4 h-4" aria-hidden="true" />
                Open in a new tab
              </a>
            </div>
            <div className={`grid gap-4 ${showOriginal ? "lg:grid-cols-2" : "grid-cols-1"}`}>
              {showOriginal && (
                <figure className="space-y-1">
                  <figcaption className="text-sm font-medium text-neutral-600">Original ({result.source_lang})</figcaption>
                  <iframe src={originalFileUrl} className="w-full h-[70vh] rounded-lg border border-neutral-200 bg-neutral-100" title="Original document" />
                </figure>
              )}
              <figure className="space-y-1">
                <figcaption className="text-sm font-medium text-neutral-600">Translation ({result.target_lang})</figcaption>
                <iframe src={translatedFileUrl} className="w-full h-[70vh] rounded-lg border border-neutral-200 bg-neutral-100" title="Translated document" />
              </figure>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {!isPdf && (
              <p className="text-sm text-neutral-600">
                Here is the text, side by side. Download the file to see it with its original formatting.
              </p>
            )}
            {result.chunks.length > 8 && (
              <div className="relative">
                <label htmlFor="find-text" className="sr-only">Find text</label>
                <Search className="w-4 h-4 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                <input
                  id="find-text"
                  type="search"
                  placeholder="Find text…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full h-11 pl-9 pr-3 rounded-lg border border-neutral-300 bg-white text-base text-neutral-900 placeholder:text-neutral-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                />
              </div>
            )}
            {result.chunks_truncated && (
              <p className="text-sm text-neutral-600">
                Only the first {result.chunks.length} parts are shown here. The downloaded file has everything.
              </p>
            )}

            <div className="hidden md:grid grid-cols-2 gap-4 px-4 text-sm font-semibold text-neutral-600">
              <span>Original ({result.source_lang})</span>
              <span>Translation ({result.target_lang})</span>
            </div>
            {visibleChunks.length === 0 ? (
              <p className="text-base text-neutral-600 py-8 text-center">Nothing matches &quot;{searchQuery}&quot;.</p>
            ) : (
              <ul className="space-y-2">
                {visibleChunks.map((chunk) => (
                  <li key={chunk.chunk_id} className="rounded-lg border border-neutral-200 p-4 grid md:grid-cols-2 gap-3 md:gap-4">
                    <div className="text-base text-neutral-600 whitespace-pre-wrap">
                      <span className="md:hidden block text-xs font-semibold uppercase text-neutral-500 mb-1">Original</span>
                      {chunk.original}
                    </div>
                    <div className="text-base text-neutral-900 whitespace-pre-wrap">
                      <span className="md:hidden block text-xs font-semibold uppercase text-emerald-700 mb-1">Translation</span>
                      {chunk.translated}
                      <div className="mt-2 flex items-center gap-3 text-sm text-neutral-500">
                        {isPdf && chunk.page ? <span>Page {chunk.page}</span> : null}
                        <button
                          onClick={() => copy(chunk.translated, () => { setCopiedId(chunk.chunk_id); setTimeout(() => setCopiedId(null), 2000); })}
                          className="inline-flex items-center gap-1 hover:text-neutral-900 cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                        >
                          {copiedId === chunk.chunk_id ? <Check className="w-4 h-4 text-emerald-600" aria-hidden="true" /> : <Copy className="w-4 h-4" aria-hidden="true" />}
                          {copiedId === chunk.chunk_id ? "Copied!" : "Copy"}
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
