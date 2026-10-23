"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Header } from "@/components/Header";
import { UploadCard } from "@/components/UploadCard";
import { LanguageSelector } from "@/components/LanguageSelector";
import { TranslationProgress } from "@/components/TranslationProgress";
import { ComparisonWorkspace, TranslationResult } from "@/components/ComparisonWorkspace";
import { JobsPanel } from "@/components/JobsPanel";
import { FriendlyError, TrackedJob, isFinished, loadJobs, newTrackedJob, saveJobs } from "@/lib/jobs";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Download,
  Languages,
  Layers,
  Lock,
  RefreshCw,
  ScanLine,
  Sparkles,
  Upload,
} from "lucide-react";

// Empty = same origin: requests go through the Next.js /api rewrite to the backend,
// which works in dev, docker-compose and the unified image alike.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "";
const POLL_INTERVAL_MS = 2000;
// Jobs keep running (and resume after a backend restart), so ride out connection drops patiently
const RECONNECT_GIVE_UP_MS = 10 * 60 * 1000;
const JOB_MISSING_GIVE_UP_MS = 60 * 1000;

// FastAPI returns `detail` as a string, or as a list of validation errors
function extractErrorMessage(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "string" ? d : d?.msg || JSON.stringify(d))).join("; ");
  }
  return fallback;
}

interface JobStatus {
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  stage: number;
  progress: number;
  message: string;
  queue_position?: number;
  error?: string;
  error_type?: string;
  result?: TranslationResult;
}

// Turn backend failures into plain language; keep the raw message as optional details
function friendlyJobError(type: string | undefined, message: string | undefined): FriendlyError {
  const raw = message || "";
  // Document errors are already written for people; drop any trailing "(technical cause)"
  const plain = raw.replace(/\s*\([^()]*\)\.?\s*$/, "").trim();
  switch (type) {
    case "document":
      return { title: "We couldn't translate this file", text: plain || raw, details: raw !== plain ? raw : undefined };
    case "validation":
      return { title: "Please check your choices", text: raw };
    case "model":
      return {
        title: "The translator isn't ready on this computer",
        text: "The translation engine could not start. Please ask the person who set up this app to check it.",
        details: raw,
      };
    case "memory":
      return { title: "The document is too big for this computer", text: "Try a smaller document, or split it into parts.", details: raw };
    default:
      return {
        title: "The translation didn't finish",
        text: "Something went wrong while translating. Please try again. If it keeps happening, try a smaller document.",
        details: raw || undefined,
      };
  }
}

const CONNECTION_ERROR: FriendlyError = {
  title: "Can't connect to the translator",
  text: "The translation service isn't responding. Make sure it is running, then try again.",
};

const NO_LONGER_AVAILABLE: FriendlyError = {
  title: "This translation is no longer available",
  text: "It may have been interrupted, or removed after 24 hours. Please translate the document again.",
};

// XMLHttpRequest (unlike fetch) reports upload progress, which matters for large files
function uploadWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void
): Promise<{ status: number; data: { job_id?: string; detail?: unknown } | null }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BACKEND_URL}/api/translate`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON error page
      }
      resolve({ status: xhr.status, data });
    };
    xhr.onerror = () => reject(CONNECTION_ERROR);
    xhr.send(formData);
  });
}

function ErrorBanner({ error, onClose }: { error: FriendlyError; onClose?: () => void }) {
  const [showDetails, setShowDetails] = useState(false);
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 flex gap-3">
      <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0 space-y-1">
        <p className="text-base font-semibold text-red-800">{error.title}</p>
        <p className="text-base text-red-700">{error.text}</p>
        {error.details && (
          <>
            <button
              onClick={() => setShowDetails((s) => !s)}
              className="text-sm text-red-700 underline underline-offset-2 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded"
              aria-expanded={showDetails}
            >
              {showDetails ? "Hide details" : "Show details"}
            </button>
            {showDetails && <p className="text-sm text-red-700 break-words font-mono">{error.details}</p>}
          </>
        )}
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="self-start text-sm font-medium text-red-700 hover:underline cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded"
        >
          Dismiss
        </button>
      )}
    </div>
  );
}

// Shared full-width page container (header, content and footer line up)
const CONTAINER = "max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-10";

const HOW_IT_WORKS = [
  { icon: Upload, title: "Choose your document", text: "PDF, Word, Excel, CSV or a text file." },
  { icon: Languages, title: "Pick a language", text: "22 Indian languages and English." },
  { icon: Sparkles, title: "Click Translate", text: "It runs in the background. You can add more documents meanwhile." },
  { icon: Download, title: "Download", text: "Get your file back in the same format and layout." },
];

function HowItWorks() {
  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 sm:p-6 shadow-sm" aria-labelledby="how-title">
      <h2 id="how-title" className="text-lg font-semibold text-neutral-900">How it works</h2>
      <ol className="mt-4 space-y-4">
        {HOW_IT_WORKS.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center shrink-0" aria-hidden="true">
              <Icon className="w-5 h-5" />
            </span>
            <div>
              <p className="text-base font-medium text-neutral-900">{title}</p>
              <p className="text-sm text-neutral-600">{text}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function GoodToKnow() {
  return (
    <section className="rounded-2xl border border-neutral-200 bg-neutral-50 p-5 sm:p-6" aria-labelledby="good-title">
      <h2 id="good-title" className="text-lg font-semibold text-neutral-900">Good to know</h2>
      <ul className="mt-3 space-y-3 text-sm text-neutral-700">
        <li className="flex gap-2.5">
          <Lock className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" aria-hidden="true" />
          Your files never leave this computer.
        </li>
        <li className="flex gap-2.5">
          <Layers className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" aria-hidden="true" />
          You can translate several documents at once. They share the computer, so each one takes a little longer.
        </li>
        <li className="flex gap-2.5">
          <Clock className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" aria-hidden="true" />
          Big files take longer: about 10 to 15 minutes for 50 pages.
        </li>
        <li className="flex gap-2.5">
          <ScanLine className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" aria-hidden="true" />
          Scanned pages (photos of paper) can&apos;t be translated. The text must be selectable.
        </li>
      </ul>
    </section>
  );
}

function StepCard({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 sm:p-7 space-y-5 shadow-sm" aria-labelledby={`step-${number}`}>
      <h2 id={`step-${number}`} className="text-xl font-semibold text-neutral-900 flex items-center gap-3">
        <span className="w-9 h-9 rounded-full bg-emerald-700 text-white text-base font-bold flex items-center justify-center shrink-0" aria-hidden="true">
          {number}
        </span>
        <span>
          <span className="sr-only">Step {number}: </span>
          {title}
        </span>
      </h2>
      {children}
    </section>
  );
}

interface DirectionInfo {
  available: boolean | null; // null = couldn't check (e.g. offline)
  state: string;
  reason?: string;
}

function DirectionNotice({ sourceLang, targetLang, englishToIndicWorks, details }: {
  sourceLang: string; targetLang: string; englishToIndicWorks: boolean; details?: string;
}) {
  const [showDetails, setShowDetails] = useState(false);
  return (
    <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-1.5">
      <p className="text-base font-semibold text-amber-800">
        {sourceLang} → {targetLang} isn&apos;t available on this computer yet
      </p>
      <p className="text-base text-amber-800">
        {englishToIndicWorks
          ? "Right now you can translate from English into any Indian language. To add this language pair, ask the person who set up this app."
          : "Please ask the person who set up this app to turn on this language pair."}
      </p>
      {details && (
        <>
          <button
            onClick={() => setShowDetails((s) => !s)}
            className="text-sm text-amber-800 underline underline-offset-2 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded"
            aria-expanded={showDetails}
          >
            {showDetails ? "Hide details" : "Details for the person who set it up"}
          </button>
          {showDetails && <p className="text-sm text-amber-800 break-words font-mono">{details}</p>}
        </>
      )}
    </div>
  );
}

function BackToHome({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 h-10 px-3 -ml-3 rounded-lg text-base font-medium text-neutral-700 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
    >
      <ArrowLeft className="w-5 h-5" aria-hidden="true" />
      Back to home
    </button>
  );
}

export default function Home() {
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [modelProblem, setModelProblem] = useState<string | null>(null);
  const [directions, setDirections] = useState<Record<string, DirectionInfo>>({});
  const [maxUploadMb, setMaxUploadMb] = useState<number>(50);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceLang, setSourceLang] = useState<string>("English");
  const [targetLang, setTargetLang] = useState<string>("Hindi");

  // Every translation the user started; the backend runs several in parallel
  const [jobs, setJobs] = useState<TrackedJob[]>([]);
  const [jobsLoaded, setJobsLoaded] = useState(false);
  const [openJobId, setOpenJobId] = useState<string | null>(null);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [startedJobId, setStartedJobId] = useState<string | null>(null);
  const [error, setError] = useState<FriendlyError | null>(null);

  const jobsRef = useRef<TrackedJob[]>([]);
  const pollState = useRef<Record<string, { offlineSince?: number; missingSince?: number }>>({});
  const polling = useRef(false);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/health`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setModelProblem(data.model_error || null);
      setDirections(data.directions || {});
      if (data.max_upload_mb) setMaxUploadMb(data.max_upload_mb);
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount and restore the remembered translations (localStorage exists only in the browser)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkHealth();
    setJobs(loadJobs());
    setJobsLoaded(true);
    // Availability of language directions can change (e.g. a model gets set up), so refresh it now and then
    const timer = setInterval(checkHealth, 60_000);
    return () => clearInterval(timer);
  }, [checkHealth]);

  useEffect(() => {
    jobsRef.current = jobs;
    if (jobsLoaded) saveJobs(jobs);
  }, [jobs, jobsLoaded]);

  const patchJob = (jobId: string, patch: Partial<TrackedJob>) =>
    setJobs((prev) => prev.map((j) => (j.jobId === jobId ? { ...j, ...patch } : j)));

  // One poller for all unfinished translations (and finished ones whose result isn't loaded yet)
  useEffect(() => {
    const fetchStatus = async (job: TrackedJob): Promise<Partial<TrackedJob>> => {
      const state = (pollState.current[job.jobId] ??= {});
      const now = Date.now();
      try {
        const res = await fetch(`${BACKEND_URL}/api/jobs/${job.jobId}`);
        if (res.status === 404) {
          state.missingSince ??= now;
          return now - state.missingSince > JOB_MISSING_GIVE_UP_MS
            ? { status: "failed", reconnecting: false, error: NO_LONGER_AVAILABLE }
            : { reconnecting: true };
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: JobStatus = await res.json();
        state.offlineSince = undefined;
        state.missingSince = undefined;
        return {
          status: data.status,
          stage: data.stage || 1,
          progress: data.status === "completed" ? 100 : data.progress || 0,
          // status "cancelled" passes straight through and ends polling for this job
          message: data.message || "",
          queuePosition: data.queue_position || 0,
          reconnecting: false,
          result: data.result,
          error: data.status === "failed" ? friendlyJobError(data.error_type, data.error) : undefined,
        };
      } catch {
        state.offlineSince ??= now;
        return now - state.offlineSince > RECONNECT_GIVE_UP_MS
          ? { status: "failed", reconnecting: false, error: CONNECTION_ERROR }
          : { reconnecting: true };
      }
    };

    const tick = async () => {
      if (polling.current) return;
      polling.current = true;
      try {
        const pending = jobsRef.current.filter((j) => !isFinished(j) || (j.status === "completed" && !j.result));
        const updates = await Promise.all(pending.map(async (j) => [j.jobId, await fetchStatus(j)] as const));
        for (const [jobId, patch] of updates) patchJob(jobId, patch);
      } finally {
        polling.current = false;
      }
    };

    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const sameLanguage = sourceLang === targetLang;
  const uploading = uploadPercent !== null;
  // Each direction uses its own model; one may be set up while another is not
  const direction = sourceLang === "English" ? "en-indic" : targetLang === "English" ? "indic-en" : "indic-indic";
  const directionInfo = directions[direction];
  const directionBlocked = !sameLanguage && directionInfo?.available === false;
  const canTranslate = !!selectedFile && !sameLanguage && !uploading && !directionBlocked;

  const handleStartTranslation = async () => {
    if (!selectedFile || sameLanguage) return;
    setUploadPercent(0);
    setError(null);
    setStartedJobId(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("source_lang", sourceLang);
      formData.append("target_lang", targetLang);
      formData.append("tone", "Professional");

      const { status, data } = await uploadWithProgress(formData, setUploadPercent);
      if (status < 200 || status >= 300) {
        throw {
          title: status === 413 ? "This file is too large" : "We couldn't start the translation",
          text: extractErrorMessage(data, "Please try again."),
        } as FriendlyError;
      }
      if (!data?.job_id) throw CONNECTION_ERROR;

      const job = newTrackedJob({
        jobId: data.job_id,
        filename: selectedFile.name,
        sourceLang,
        targetLang,
        createdAt: Date.now(),
      });
      setJobs((prev) => [{ ...job, status: "queued" }, ...prev]);
      setStartedJobId(job.jobId);
      setSelectedFile(null); // ready for the next document
    } catch (err: unknown) {
      const known = err as FriendlyError;
      setError(known && typeof known.title === "string" ? known : friendlyJobError(undefined, String(err)));
    } finally {
      setUploadPercent(null);
    }
  };

  const stopJob = async (jobId: string) => {
    const job = jobs.find((j) => j.jobId === jobId);
    if (!job || !window.confirm(`Stop translating "${job.filename}"? You will need to start it again to get the translation.`)) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/jobs/${jobId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      // A running job stops after its current batch; the poller picks up the final "cancelled" state
      const data: JobStatus = await res.json();
      patchJob(jobId, { status: data.status === "cancelled" ? "cancelled" : job.status, message: "Stopping…" });
    } catch {
      setError({ title: "Couldn't stop the translation", text: "Please try again in a moment." });
    }
  };

  const removeJob = (jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.jobId !== jobId));
    if (startedJobId === jobId) setStartedJobId(null);
  };

  const goHome = () => {
    setOpenJobId(null);
    window.scrollTo({ top: 0 });
  };

  const openJob = openJobId ? jobs.find((j) => j.jobId === openJobId) : undefined;
  const startedJob = startedJobId ? jobs.find((j) => j.jobId === startedJobId) : undefined;

  const jobsPanel = (
    <JobsPanel jobs={jobs} backendUrl={BACKEND_URL} onOpen={setOpenJobId} onRemove={removeJob} onStop={stopJob} />
  );

  return (
    <div className="flex-1 flex flex-col">
      <Header onHome={goHome} />

      <main className="flex-1 w-full">
        {openJob ? (
          <div className={`${CONTAINER} py-6 sm:py-8 space-y-4`}>
            <BackToHome onClick={goHome} />
            {openJob.status === "completed" && openJob.result ? (
              <ComparisonWorkspace result={openJob.result} onReset={goHome} backendUrl={BACKEND_URL} />
            ) : openJob.status === "failed" ? (
              <div className="max-w-3xl space-y-4">
                <h1 className="text-2xl font-semibold text-neutral-900 break-all">{openJob.filename}</h1>
                <ErrorBanner error={openJob.error || NO_LONGER_AVAILABLE} />
              </div>
            ) : openJob.status === "cancelled" ? (
              <div className="max-w-3xl space-y-2">
                <h1 className="text-2xl font-semibold text-neutral-900 break-all">{openJob.filename}</h1>
                <p className="text-base text-neutral-700">This translation was stopped. Choose the document again on the home page to restart it.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
                <div className="lg:col-span-7 xl:col-span-8">
                  <TranslationProgress
                    stage={openJob.stage}
                    percent={openJob.progress}
                    message={openJob.message}
                    queuePosition={openJob.queuePosition}
                    reconnecting={openJob.reconnecting}
                    uploadPercent={null}
                    filename={openJob.filename}
                    targetLang={openJob.targetLang}
                  />
                  <button
                    onClick={() => stopJob(openJob.jobId)}
                    className="mt-3 inline-flex items-center gap-2 h-10 px-4 rounded-lg text-sm font-medium text-red-700 hover:bg-red-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                  >
                    Stop this translation
                  </button>
                </div>
                <aside className="lg:col-span-5 xl:col-span-4 space-y-6">
                  {jobs.length > 1 && jobsPanel}
                  <GoodToKnow />
                </aside>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Welcome band */}
            <section className="border-b border-neutral-200 bg-linear-to-b from-emerald-50 to-transparent">
              <div className={`${CONTAINER} py-8 lg:py-10`}>
                <p className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white px-3 py-1 text-sm font-medium text-emerald-700">
                  <Lock className="w-4 h-4" aria-hidden="true" />
                  Private · Works on this computer
                </p>
                <h1 className="mt-4 text-3xl sm:text-4xl xl:text-5xl font-bold tracking-tight text-neutral-900 max-w-3xl">
                  Translate your documents into Indian languages
                </h1>
                <p className="mt-3 text-lg text-neutral-600 max-w-2xl">
                  Choose a file, pick a language, and download the translated copy. It keeps the same layout as your original.
                </p>
                <ul className="mt-6 flex flex-wrap gap-2 text-sm text-neutral-700">
                  {["22 Indian languages + English", "PDF, Word, Excel, CSV & text", "Keeps your layout", "Several documents at once"].map((fact) => (
                    <li key={fact} className="inline-flex items-center gap-1.5 rounded-full bg-white border border-neutral-200 px-3 py-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                      {fact}
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <div className={`${CONTAINER} py-8 lg:py-10 grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start`}>
              <div className="lg:col-span-7 xl:col-span-8 space-y-6">
                {backendOnline === false && (
                  <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" aria-hidden="true" />
                    <div className="flex-1 space-y-2">
                      <p className="text-base font-semibold text-amber-800">Can&apos;t connect to the translator</p>
                      <p className="text-base text-amber-800">
                        The translation service isn&apos;t running. Please start it (or ask the person who set up this app), then try again.
                      </p>
                      <button
                        onClick={checkHealth}
                        className="inline-flex items-center gap-2 h-10 px-4 rounded-lg border border-amber-200 bg-white text-sm font-medium text-amber-800 hover:bg-amber-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                      >
                        <RefreshCw className="w-4 h-4" aria-hidden="true" />
                        Try again
                      </button>
                    </div>
                  </div>
                )}

                {backendOnline && modelProblem && (
                  <ErrorBanner
                    error={{
                      title: "The translator isn't ready on this computer",
                      text: "Translations may not work right now. Please ask the person who set up this app to check it.",
                      details: modelProblem,
                    }}
                  />
                )}

                {error && <ErrorBanner error={error} onClose={() => setError(null)} />}

                {startedJob && !isFinished(startedJob) && (
                  <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" aria-hidden="true" />
                    <p className="flex-1 text-base text-emerald-900">
                      <span className="font-semibold break-all">{startedJob.filename}</span> is being translated. You can add another
                      document now, or follow its progress under &quot;Your translations&quot;.
                    </p>
                    <button
                      onClick={() => setOpenJobId(startedJob.jobId)}
                      className="h-10 px-4 rounded-lg border border-emerald-200 bg-white text-sm font-medium text-emerald-800 hover:bg-emerald-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 shrink-0"
                    >
                      View progress
                    </button>
                  </div>
                )}

                {/* On small screens the list goes above the form so it's easy to find */}
                <div className="lg:hidden">{jobsPanel}</div>

                <StepCard number={1} title={jobs.length ? "Choose a document" : "Choose your document"}>
                  <UploadCard
                    selectedFile={selectedFile}
                    onFileSelect={(file) => {
                      setSelectedFile(file);
                      setError(null);
                    }}
                    onClearFile={() => setSelectedFile(null)}
                    onError={(text) => setError({ title: "This file can't be used", text })}
                    maxUploadMb={maxUploadMb}
                    isProcessing={uploading}
                  />
                </StepCard>

                <StepCard number={2} title="Choose the languages">
                  <LanguageSelector
                    sourceLang={sourceLang}
                    targetLang={targetLang}
                    onSourceChange={setSourceLang}
                    onTargetChange={setTargetLang}
                    onSwap={() => {
                      setSourceLang(targetLang);
                      setTargetLang(sourceLang);
                    }}
                    disabled={uploading}
                  />
                  {directionBlocked && (
                    <DirectionNotice
                      sourceLang={sourceLang}
                      targetLang={targetLang}
                      englishToIndicWorks={directions["en-indic"]?.available !== false}
                      details={directionInfo?.reason}
                    />
                  )}
                </StepCard>

                <div className="space-y-2">
                  <button
                    onClick={handleStartTranslation}
                    disabled={!canTranslate}
                    className="relative w-full overflow-hidden inline-flex items-center justify-center gap-2 h-14 px-6 rounded-xl bg-emerald-700 text-white text-lg font-semibold hover:bg-emerald-800 cursor-pointer disabled:cursor-not-allowed disabled:bg-neutral-300 disabled:text-neutral-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2"
                  >
                    {uploading ? (
                      <>
                        <span
                          className="absolute inset-y-0 left-0 bg-emerald-600/40 transition-all"
                          style={{ width: `${uploadPercent}%` }}
                          aria-hidden="true"
                        />
                        <span className="relative">Sending your document… {Math.round(uploadPercent ?? 0)}%</span>
                      </>
                    ) : (
                      <>
                        Translate to {targetLang}
                        <ArrowRight className="w-5 h-5" aria-hidden="true" />
                      </>
                    )}
                  </button>
                  {!canTranslate && !uploading && (
                    <p className="text-sm text-neutral-600 text-center" aria-live="polite">
                      {!selectedFile
                        ? jobs.length
                          ? "Choose another document in step 1 to translate it too."
                          : "First, choose a document in step 1."
                        : directionBlocked
                        ? "This language pair isn't available yet. See the note in step 2."
                        : "Please choose two different languages in step 2."}
                    </p>
                  )}
                </div>
              </div>

              <aside className="lg:col-span-5 xl:col-span-4 space-y-6 lg:sticky lg:top-6">
                <div className="hidden lg:block">{jobsPanel}</div>
                <HowItWorks />
                <GoodToKnow />
              </aside>
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-neutral-200 bg-white py-5">
        <div className={`${CONTAINER} flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-neutral-600`}>
          <p className="flex items-center gap-2">
            <Lock className="w-4 h-4" aria-hidden="true" />
            Your documents are translated on this computer and are never sent to the internet.
          </p>
          <p className="text-neutral-500">Translation by AI4Bharat IndicTrans2</p>
        </div>
      </footer>
    </div>
  );
}
