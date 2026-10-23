"use client";

import React from "react";
import { CheckCircle2, Loader2, Circle } from "lucide-react";

interface TranslationProgressProps {
  stage: number; // 1 to 4, reported by the backend job
  percent: number; // 0 to 100
  message: string;
  queuePosition: number;
  reconnecting: boolean;
  uploadPercent: number | null; // set while the file is still being sent
  filename: string;
  targetLang: string;
}

const STEPS = [
  { id: 1, label: "Reading your document" },
  { id: 2, label: "Getting the translator ready", hint: "The first translation after starting can take a few minutes." },
  { id: 3, label: "Translating" },
  { id: 4, label: "Creating your translated file" },
];

export function TranslationProgress({
  stage,
  percent,
  message,
  queuePosition,
  reconnecting,
  uploadPercent,
  filename,
  targetLang,
}: TranslationProgressProps) {
  // Backend messages look like "Translating segments (12/40)"; show that as plain counts
  const counts = message.match(/\((\d+)\/(\d+)\)/);
  const uploading = uploadPercent !== null;
  const shownPercent = uploading ? uploadPercent : percent;
  const rounded = Math.round(shownPercent);

  const statusText = uploading
    ? `Sending your document to the translator… ${rounded}%`
    : reconnecting
    ? "Reconnecting to the translator… Your translation continues by itself, please wait."
    : queuePosition > 0
    ? `Waiting for another document to finish first (${queuePosition} ahead of yours)`
    : stage === 3 && counts
    ? `${counts[1]} of ${counts[2]} parts translated`
    : STEPS[Math.min(Math.max(stage, 1), 4) - 1].label;

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-6 sm:p-8 space-y-6" aria-labelledby="progress-title">
      <div className="space-y-1">
        <h2 id="progress-title" className="text-xl font-semibold text-neutral-900 flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-emerald-600" aria-hidden="true" />
          Translating into {targetLang}…
        </h2>
        <p className="text-base text-neutral-600 break-all">{filename}</p>
      </div>

      <div className="space-y-2" aria-live="polite">
        <div
          className="h-3 w-full rounded-full bg-neutral-200 overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={rounded}
          aria-label="Translation progress"
        >
          <div
            className={`h-full transition-all duration-500 ${reconnecting ? "bg-amber-400" : "bg-emerald-600"}`}
            style={{ width: `${Math.max(3, Math.min(100, shownPercent))}%` }}
          />
        </div>
        <p className={`text-base flex justify-between gap-4 ${reconnecting ? "text-amber-800" : "text-neutral-700"}`}>
          <span>{statusText}</span>
          <span className="font-semibold">{rounded}%</span>
        </p>
      </div>

      <ol className="space-y-3">
        {STEPS.map((s) => {
          const done = stage > s.id;
          const current = stage === s.id && queuePosition === 0;
          return (
            <li key={s.id} className="flex items-start gap-3">
              {done ? (
                <CheckCircle2 className="w-5 h-5 mt-0.5 text-emerald-600 shrink-0" aria-hidden="true" />
              ) : current ? (
                <Loader2 className="w-5 h-5 mt-0.5 text-emerald-600 animate-spin shrink-0" aria-hidden="true" />
              ) : (
                <Circle className="w-5 h-5 mt-0.5 text-neutral-300 shrink-0" aria-hidden="true" />
              )}
              <div>
                <p className={`text-base ${current ? "font-semibold text-neutral-900" : done ? "text-neutral-700" : "text-neutral-500"}`}>
                  {s.label}
                  <span className="sr-only">{done ? " (done)" : current ? " (in progress)" : " (waiting)"}</span>
                </p>
                {current && s.hint && <p className="text-sm text-neutral-500">{s.hint}</p>}
              </div>
            </li>
          );
        })}
      </ol>

      <p className="text-sm text-neutral-500 border-t border-neutral-200 pt-4">
        Long documents can take a while (about 10 to 15 minutes for 50 pages). It keeps going in the
        background: you can go back to the home page to translate other documents, or close this page
        and come back later.
      </p>
    </section>
  );
}
