"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, CircleStop, Clock, Download, Loader2, WifiOff, X } from "lucide-react";
import { isFinished, TrackedJob } from "@/lib/jobs";

interface JobsPanelProps {
  jobs: TrackedJob[];
  backendUrl: string;
  onOpen: (jobId: string) => void;
  onRemove: (jobId: string) => void;
  onStop: (jobId: string) => void;
}

function statusLine(job: TrackedJob): string {
  if (job.reconnecting) return "Reconnecting… it keeps translating";
  switch (job.status) {
    case "completed":
      return "Ready to download";
    case "failed":
      return job.error?.title || "Something went wrong";
    case "cancelled":
      return "Stopped";
    case "queued":
      return job.queuePosition > 0 ? `Waiting to start (${job.queuePosition} ahead)` : "Starting…";
    case "processing":
      return `Translating… ${Math.round(job.progress)}%`;
    default:
      return "Checking…";
  }
}

function StatusIcon({ job }: { job: TrackedJob }) {
  const cls = "w-5 h-5 shrink-0";
  if (job.reconnecting) return <WifiOff className={`${cls} text-amber-600`} aria-hidden="true" />;
  if (job.status === "completed") return <CheckCircle2 className={`${cls} text-emerald-600`} aria-hidden="true" />;
  if (job.status === "failed") return <AlertTriangle className={`${cls} text-red-600`} aria-hidden="true" />;
  if (job.status === "cancelled") return <CircleStop className={`${cls} text-neutral-500`} aria-hidden="true" />;
  if (job.status === "queued") return <Clock className={`${cls} text-neutral-500`} aria-hidden="true" />;
  return <Loader2 className={`${cls} text-emerald-600 animate-spin`} aria-hidden="true" />;
}

const smallButton =
  "inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600";

export function JobsPanel({ jobs, backendUrl, onOpen, onRemove, onStop }: JobsPanelProps) {
  if (jobs.length === 0) return null;
  const running = jobs.filter((j) => !isFinished(j)).length;

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 sm:p-6 shadow-sm" aria-labelledby="jobs-title">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="jobs-title" className="text-lg font-semibold text-neutral-900">Your translations</h2>
        {running > 0 && <span className="text-sm text-neutral-600">{running} in progress</span>}
      </div>

      <ul className="mt-4 space-y-3" aria-live="polite">
        {jobs.map((job) => {
          const active = !isFinished(job);
          return (
            <li key={job.jobId} className="rounded-xl border border-neutral-200 p-3 space-y-2">
              <div className="flex items-start gap-3">
                <StatusIcon job={job} />
                <div className="min-w-0 flex-1">
                  <p className="text-base font-medium text-neutral-900 truncate" title={job.filename}>{job.filename}</p>
                  <p className="text-sm text-neutral-600">
                    {job.sourceLang ? `${job.sourceLang} → ` : "→ "}{job.targetLang}
                  </p>
                </div>
                <button
                  onClick={() => onRemove(job.jobId)}
                  className="p-1.5 rounded-md text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                  aria-label={active ? `Hide ${job.filename} from this list (it keeps translating)` : `Remove ${job.filename} from this list`}
                  title={active ? "Hide (keeps translating)" : "Remove from list"}
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>

              {active && (
                <div className="h-2 w-full rounded-full bg-neutral-200 overflow-hidden" aria-hidden="true">
                  <div
                    className={`h-full transition-all duration-500 ${job.reconnecting ? "bg-amber-400" : "bg-emerald-600"}`}
                    style={{ width: `${Math.max(3, Math.min(100, job.progress))}%` }}
                  />
                </div>
              )}
              <p className={`text-sm ${job.status === "failed" ? "text-red-700" : job.reconnecting ? "text-amber-800" : "text-neutral-700"}`}>
                {statusLine(job)}
              </p>

              <div className="flex flex-wrap gap-2">
                {job.status === "completed" && job.result ? (
                  <>
                    <a
                      href={`${backendUrl}${job.result.download_url}`}
                      download={job.result.download_filename || job.filename}
                      className={`${smallButton} bg-emerald-700 text-white hover:bg-emerald-800`}
                    >
                      <Download className="w-4 h-4" aria-hidden="true" />
                      Download
                    </a>
                    <button onClick={() => onOpen(job.jobId)} className={`${smallButton} border border-neutral-300 text-neutral-800 hover:bg-neutral-50`}>
                      Preview
                    </button>
                  </>
                ) : job.status === "failed" ? (
                  <button onClick={() => onOpen(job.jobId)} className={`${smallButton} border border-neutral-300 text-neutral-800 hover:bg-neutral-50`}>
                    See what went wrong
                  </button>
                ) : job.status === "cancelled" ? null : (
                  <>
                    <button onClick={() => onOpen(job.jobId)} className={`${smallButton} border border-neutral-300 text-neutral-800 hover:bg-neutral-50`}>
                      View progress
                    </button>
                    <button onClick={() => onStop(job.jobId)} className={`${smallButton} text-red-700 hover:bg-red-50`}>
                      Stop
                    </button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
