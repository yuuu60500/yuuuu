import { ProjectStatus } from "@/lib/api";

const STYLES: Record<ProjectStatus, string> = {
  CREATED: "bg-gray-100 text-gray-600",
  UPLOADED: "bg-gray-100 text-gray-700",
  PROCESSING_AUDIO: "bg-amber-100 text-amber-800",
  TRANSCRIBING: "bg-amber-100 text-amber-800",
  TRANSLATING: "bg-amber-100 text-amber-800",
  READY: "bg-green-100 text-green-800",
  FAILED: "bg-red-100 text-red-700",
};

const LABELS: Record<ProjectStatus, string> = {
  CREATED: "Created",
  UPLOADED: "Uploaded",
  PROCESSING_AUDIO: "Processing audio",
  TRANSCRIBING: "Transcribing",
  TRANSLATING: "Translating",
  READY: "Completed",
  FAILED: "Failed",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>{LABELS[status]}</span>;
}

export const isBusy = (s: ProjectStatus) => s === "PROCESSING_AUDIO" || s === "TRANSCRIBING" || s === "TRANSLATING";
