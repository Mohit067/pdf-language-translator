import type { TranslationResult } from "@/components/ComparisonWorkspace";

export interface FriendlyError {
  title: string;
  text: string;
  details?: string;
}

export type JobState = "unknown" | "queued" | "processing" | "completed" | "failed" | "cancelled";

// A translation the user started, tracked in the browser (the work itself runs on the backend)
export interface TrackedJob {
  jobId: string;
  filename: string;
  sourceLang: string;
  targetLang: string;
  createdAt: number;
  status: JobState;
  stage: number;
  progress: number;
  message: string;
  queuePosition: number;
  reconnecting: boolean;
  error?: FriendlyError;
  result?: TranslationResult;
}

const JOBS_KEY = "transdoc.jobs";
const LEGACY_ACTIVE_JOB_KEY = "transdoc.activeJob";
const MAX_REMEMBERED = 25;

type StoredJob = Pick<TrackedJob, "jobId" | "filename" | "sourceLang" | "targetLang" | "createdAt">;

export function newTrackedJob(job: StoredJob): TrackedJob {
  return { ...job, status: "unknown", stage: 1, progress: 0, message: "", queuePosition: 0, reconnecting: false };
}

/** Jobs remembered from earlier visits; their live status is fetched from the backend. */
export function loadJobs(): TrackedJob[] {
  try {
    const stored: StoredJob[] = JSON.parse(localStorage.getItem(JOBS_KEY) || "[]");
    const legacy = JSON.parse(localStorage.getItem(LEGACY_ACTIVE_JOB_KEY) || "null");
    if (legacy?.jobId && !stored.some((j) => j.jobId === legacy.jobId)) {
      stored.unshift({ jobId: legacy.jobId, filename: legacy.filename, sourceLang: "", targetLang: legacy.targetLang, createdAt: Date.now() });
    }
    localStorage.removeItem(LEGACY_ACTIVE_JOB_KEY);
    return stored.filter((j) => j?.jobId).map(newTrackedJob);
  } catch {
    return [];
  }
}

export function saveJobs(jobs: TrackedJob[]): void {
  try {
    const stored: StoredJob[] = jobs.slice(0, MAX_REMEMBERED).map(({ jobId, filename, sourceLang, targetLang, createdAt }) => ({
      jobId, filename, sourceLang, targetLang, createdAt,
    }));
    localStorage.setItem(JOBS_KEY, JSON.stringify(stored));
  } catch {
    // storage unavailable: the list just won't survive a refresh
  }
}

export const isFinished = (job: TrackedJob) =>
  job.status === "completed" || job.status === "failed" || job.status === "cancelled";
