export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type StepName = "upload" | "audio" | "transcription" | "segmentation" | "translation" | "finalize";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type ProjectStatus =
  | "CREATED"
  | "UPLOADED"
  | "PROCESSING_AUDIO"
  | "TRANSCRIBING"
  | "TRANSLATING"
  | "READY"
  | "FAILED";
export type SubtitleMode = "original" | "translation" | "bilingual";

export interface Project {
  id: string;
  filename: string | null;
  file_type: string | null;
  file_size: number | null;
  duration: number | null;
  media_kind: "audio" | "video" | null;
  source_language: string;
  detected_language: string | null;
  target_language: string | null;
  domain: string;
  subtitle_mode: SubtitleMode;
  status: ProjectStatus;
  steps: Record<StepName, { status: StepStatus; error: string | null; progress?: number }>;
  progress: number;
  error_message: string | null;
  segment_count: number;
  created_at: string;
  updated_at: string;
}

export interface Segment {
  id: string;
  project_id: string;
  segment_index: number;
  start_time: number;
  end_time: number;
  original_text: string;
  translated_text: string | null;
  translation_language: string | null;
  speaker: string | null;
  confidence: number | null;
  updated_at: string;
}

export interface Option {
  code: string;
  name: string;
  native_name?: string;
}

export interface Meta {
  source_languages: Option[];
  target_languages: Option[];
  domains: Option[];
  subtitle_modes: Option[];
  supported_extensions: string[];
  max_upload_mb: number;
}

export interface GlossaryTerm {
  id: string;
  term: string;
  translation: string;
  target_language: string | null;
  project_id: string | null;
  note: string | null;
}

export type ExportFormat = "srt" | "vtt" | "txt";
export type ExportContent = "original" | "translation" | "bilingual";
export type ExportOrder = "original_first" | "translation_first";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData)
      ? { "Content-Type": "application/json", ...init?.headers }
      : init?.headers,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  meta: () => request<Meta>("/api/meta"),

  listProjects: (limit = 20) => request<Project[]>(`/api/projects?limit=${limit}`),
  createProject: (body: {
    source_language: string;
    target_language: string | null;
    domain: string;
    subtitle_mode: SubtitleMode;
  }) => request<Project>("/api/projects", { method: "POST", body: json(body) }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  updateProject: (id: string, body: Partial<Pick<Project, "source_language" | "target_language" | "domain" | "subtitle_mode">>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: json(body) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  process: (id: string) => request<Project>(`/api/projects/${id}/process`, { method: "POST" }),
  retry: (id: string) => request<Project>(`/api/projects/${id}/retry`, { method: "POST" }),
  translate: (id: string, body: { target_language?: string; domain?: string; segment_ids?: string[] }) =>
    request<{ project: Project; segments: Segment[] | null }>(`/api/projects/${id}/translate`, {
      method: "POST",
      body: json(body),
    }),

  mediaUrl: (id: string) => `${API_URL}/api/projects/${id}/media`,

  listSegments: (id: string) => request<Segment[]>(`/api/projects/${id}/segments`),
  updateSegment: (
    id: string,
    body: Partial<Pick<Segment, "start_time" | "end_time" | "original_text" | "translated_text" | "speaker">>,
  ) => request<Segment>(`/api/segments/${id}`, { method: "PATCH", body: json(body) }),
  deleteSegment: (id: string) => request<void>(`/api/segments/${id}`, { method: "DELETE" }),
  addSegment: (projectId: string, body: { start_time: number; end_time: number; original_text?: string; translated_text?: string | null }) =>
    request<Segment>(`/api/projects/${projectId}/segments`, { method: "POST", body: json(body) }),
  splitSegment: (id: string, at_time?: number) =>
    request<Segment[]>(`/api/segments/${id}/split`, { method: "POST", body: json({ at_time }) }),
  mergeSegments: (projectId: string, segment_ids: string[]) =>
    request<Segment>(`/api/projects/${projectId}/segments/merge`, { method: "POST", body: json({ segment_ids }) }),

  exportText: async (id: string, format: ExportFormat, content: ExportContent, order: ExportOrder) => {
    const res = await fetch(`${API_URL}/api/projects/${id}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: json({ format, content, order }),
    });
    if (!res.ok) {
      let message = res.statusText;
      try {
        message = (await res.json()).detail ?? message;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, message);
    }
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = /filename\*=UTF-8''([^;]+)/.exec(disposition);
    const filename = match ? decodeURIComponent(match[1]) : `subtitles.${format}`;
    return { filename, text: await res.text() };
  },

  listGlossary: (projectId?: string) =>
    request<GlossaryTerm[]>(`/api/glossary${projectId ? `?project_id=${projectId}` : ""}`),
  createGlossary: (body: Omit<GlossaryTerm, "id">) =>
    request<GlossaryTerm>("/api/glossary", { method: "POST", body: json(body) }),
  updateGlossary: (id: string, body: Omit<GlossaryTerm, "id">) =>
    request<GlossaryTerm>(`/api/glossary/${id}`, { method: "PUT", body: json(body) }),
  deleteGlossary: (id: string) => request<void>(`/api/glossary/${id}`, { method: "DELETE" }),
};

/** Upload with progress reporting (fetch has no upload progress events). */
export function uploadFile(projectId: string, file: File, onProgress: (fraction: number) => void): Promise<Project> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/projects/${projectId}/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as Project);
      else {
        const detail = (data as { detail?: unknown } | null)?.detail;
        reject(new ApiError(xhr.status, typeof detail === "string" ? detail : `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
