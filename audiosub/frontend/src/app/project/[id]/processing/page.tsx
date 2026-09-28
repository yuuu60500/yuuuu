"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { isBusy, StatusBadge } from "@/components/StatusBadge";
import { api, Project, StepName, StepStatus } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { domainName, languageName, useMeta } from "@/lib/meta";

const STEPS: { key: StepName; label: string }[] = [
  { key: "upload", label: "File Uploaded" },
  { key: "audio", label: "Audio Extracted" },
  { key: "transcription", label: "Speech Recognition" },
  { key: "segmentation", label: "Subtitle Segmentation" },
  { key: "translation", label: "Translation" },
  { key: "finalize", label: "Final Processing" },
];

function StepIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case "completed":
      return <span className="text-green-600">✓</span>;
    case "running":
      return <span className="animate-pulse text-indigo-600">●</span>;
    case "failed":
      return <span className="text-red-600">✕</span>;
    case "skipped":
      return <span className="text-gray-400">–</span>;
    default:
      return <span className="text-gray-300">○</span>;
  }
}

const RETRY_LABEL: Partial<Record<StepName, string>> = {
  audio: "Retry Audio Extraction",
  transcription: "Retry Speech Recognition",
  segmentation: "Retry Segmentation",
  translation: "Retry Translation",
};

export default function ProcessingPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const meta = useMeta();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const load = useCallback(async () => {
    try {
      setProject(await api.getProject(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!project || !isBusy(project.status)) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [project, load]);

  useEffect(() => {
    if (project?.status === "READY") {
      const t = setTimeout(() => router.push(`/project/${id}/editor`), 1200);
      return () => clearTimeout(t);
    }
  }, [project?.status, id, router]);

  async function retry() {
    setRetrying(true);
    try {
      setProject(await api.retry(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrying(false);
    }
  }

  if (error && !project) return <p className="p-8 text-red-600">{error}</p>;
  if (!project) return <p className="p-8 text-gray-500">Loading…</p>;

  const failedStep = STEPS.find((s) => project.steps[s.key]?.status === "failed")?.key;
  const lang = project.detected_language ?? (project.source_language !== "auto" ? project.source_language : null);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold">{project.filename}</h1>
            <p className="text-sm text-gray-500">
              {domainName(meta, project.domain)}
              {project.target_language && project.subtitle_mode !== "original"
                ? ` · Translate to ${languageName(meta, project.target_language)}`
                : ""}
            </p>
          </div>
          <StatusBadge status={project.status} />
        </div>

        <div className="mt-6">
          <div className="flex justify-between text-sm">
            <span className="font-medium">Progress</span>
            <span>{Math.round(project.progress)}%</span>
          </div>
          <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-gray-200">
            <div
              className={`h-full transition-all duration-500 ${project.status === "FAILED" ? "bg-red-500" : "bg-indigo-600"}`}
              style={{ width: `${project.progress}%` }}
            />
          </div>
        </div>

        <ul className="mt-6 space-y-2.5">
          {STEPS.map((s) => {
            const step = project.steps[s.key];
            const status = step?.status ?? "pending";
            return (
              <li key={s.key} className="flex items-start gap-3">
                <span className="w-5 text-center text-lg leading-6"><StepIcon status={status} /></span>
                <div className="flex-1">
                  <div className={`leading-6 ${status === "pending" ? "text-gray-400" : ""}`}>
                    {s.label}
                    {status === "running" && s.key === "translation" && step.progress != null && (
                      <span className="ml-2 text-sm text-gray-500">{Math.round(step.progress * 100)}%</span>
                    )}
                    {status === "skipped" && <span className="ml-2 text-sm text-gray-400">(not needed)</span>}
                  </div>
                  {status === "failed" && step.error && <p className="text-sm text-red-600">{step.error}</p>}
                  {step?.warning && <p className="text-sm text-amber-700">{step.warning}</p>}
                </div>
              </li>
            );
          })}
        </ul>

        <dl className="mt-6 grid grid-cols-3 gap-4 rounded-lg bg-gray-50 p-4 text-sm">
          <div>
            <dt className="label">Detected language</dt>
            <dd>{languageName(meta, lang)}</dd>
          </div>
          <div>
            <dt className="label">Duration</dt>
            <dd>{formatDuration(project.duration)}</dd>
          </div>
          <div>
            <dt className="label">Subtitle segments</dt>
            <dd>{project.segment_count}</dd>
          </div>
        </dl>

        {project.status === "FAILED" && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
            <p className="text-sm text-red-700">
              {project.error_message ?? "Processing failed."} Completed steps are kept — retrying continues from the failed step.
            </p>
            <div className="mt-3 flex gap-2">
              <button className="btn-primary" disabled={retrying} onClick={retry}>
                {retrying ? "Retrying…" : (failedStep && RETRY_LABEL[failedStep]) || "Retry"}
              </button>
              {project.segment_count > 0 && (
                <Link className="btn-secondary" href={`/project/${id}/editor`}>
                  Open editor anyway
                </Link>
              )}
            </div>
          </div>
        )}

        {project.status === "UPLOADED" && (
          <button className="btn-primary mt-6" onClick={() => api.process(id).then(setProject)}>
            Generate Subtitle
          </button>
        )}

        {project.status === "READY" && (
          <div className="mt-6 flex items-center gap-3">
            <Link className="btn-primary" href={`/project/${id}/editor`}>
              Open Subtitle Editor
            </Link>
            <span className="text-sm text-gray-500">Opening automatically…</span>
          </div>
        )}
      </div>
    </div>
  );
}
