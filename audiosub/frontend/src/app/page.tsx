"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { RecentProjects } from "@/components/RecentProjects";
import { Select } from "@/components/Select";
import { api, SubtitleMode, uploadFile } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import { useMeta } from "@/lib/meta";

interface Picked {
  file: File;
  duration: number | null;
}

function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement(file.type.startsWith("video") || file.name.toLowerCase().endsWith(".mp4") ? "video" : "audio");
    el.preload = "metadata";
    const done = (v: number | null) => {
      URL.revokeObjectURL(url);
      resolve(v);
    };
    el.onloadedmetadata = () => done(Number.isFinite(el.duration) ? el.duration : null);
    el.onerror = () => done(null);
    el.src = url;
  });
}

export default function UploadPage() {
  const router = useRouter();
  const meta = useMeta();
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [dragging, setDragging] = useState(false);
  const [source, setSource] = useState("auto");
  const [target, setTarget] = useState("zh");
  const [mode, setMode] = useState<SubtitleMode>("bilingual");
  const [domain, setDomain] = useState("general");
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const extensions = meta?.supported_extensions ?? ["mp3", "wav", "m4a", "mp4"];

  async function pick(file: File | undefined) {
    if (!file) return;
    setError(null);
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!extensions.includes(ext)) {
      setError(`Unsupported file type ".${ext}". Supported: ${extensions.map((e) => e.toUpperCase()).join(", ")}.`);
      return;
    }
    if (meta && file.size > meta.max_upload_mb * 1024 * 1024) {
      setError(`File is larger than ${meta.max_upload_mb} MB.`);
      return;
    }
    setPicked({ file, duration: null });
    const duration = await readDuration(file);
    setPicked((p) => (p && p.file === file ? { file, duration } : p));
  }

  async function generate() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject({
        source_language: source,
        target_language: mode === "original" ? null : target,
        domain,
        subtitle_mode: mode,
      });
      setUploadProgress(0);
      await uploadFile(project.id, picked.file, setUploadProgress);
      await api.process(project.id);
      router.push(`/project/${project.id}/processing`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      setUploadProgress(null);
    }
  }

  const ext = picked?.file.name.split(".").pop()?.toUpperCase();

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 lg:grid-cols-[1fr_380px]">
      <section className="card p-6">
        <h1 className="text-xl font-semibold">Generate subtitles</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload audio or video. We transcribe it, split it into subtitles and translate them — then you can review and export.
        </p>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files[0]);
          }}
          className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
            dragging ? "border-indigo-500 bg-indigo-50" : "border-gray-300 hover:border-indigo-400 hover:bg-gray-50"
          }`}
        >
          <div className="text-3xl">⬆</div>
          <div className="mt-2 font-medium">Drag &amp; drop a file here, or click to choose</div>
          <div className="mt-1 text-xs text-gray-500">{extensions.map((e) => e.toUpperCase()).join(" · ")}</div>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept={extensions.map((e) => `.${e}`).join(",")}
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </div>

        {picked && (
          <dl className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-gray-50 p-4 text-sm sm:grid-cols-4">
            <div className="col-span-2 sm:col-span-1">
              <dt className="label">File</dt>
              <dd className="truncate font-medium" title={picked.file.name}>{picked.file.name}</dd>
            </div>
            <div>
              <dt className="label">Format</dt>
              <dd>{ext}</dd>
            </div>
            <div>
              <dt className="label">Size</dt>
              <dd>{formatBytes(picked.file.size)}</dd>
            </div>
            <div>
              <dt className="label">Duration</dt>
              <dd>{formatDuration(picked.duration)}</dd>
            </div>
          </dl>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Select id="source" label="Source language" value={source} onChange={setSource}
            options={meta?.source_languages ?? [{ code: "auto", name: "Auto Detect" }]} />
          <Select id="target" label="Translation language" value={target} onChange={setTarget}
            disabled={mode === "original"} options={meta?.target_languages ?? []} />
          <Select id="domain" label="Domain" value={domain} onChange={setDomain} options={meta?.domains ?? []} />
          <div>
            <span className="label">Subtitle mode</span>
            <div className="flex rounded-md border border-gray-300 bg-white p-0.5 text-sm">
              {(meta?.subtitle_modes ?? []).map((m) => (
                <button
                  key={m.code}
                  type="button"
                  onClick={() => setMode(m.code as SubtitleMode)}
                  className={`flex-1 rounded px-2 py-1 ${mode === m.code ? "bg-indigo-600 text-white" : "text-gray-600 hover:bg-gray-100"}`}
                >
                  {m.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        <ModePreview mode={mode} />

        {error && <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="mt-6 flex items-center gap-4">
          <button className="btn-primary px-5 py-2 text-base" disabled={!picked || busy} onClick={generate}>
            {busy ? "Starting…" : "Generate Subtitle"}
          </button>
          {uploadProgress !== null && (
            <div className="flex flex-1 items-center gap-2 text-sm text-gray-600">
              <div className="h-2 flex-1 overflow-hidden rounded bg-gray-200">
                <div className="h-full bg-indigo-500 transition-all" style={{ width: `${uploadProgress * 100}%` }} />
              </div>
              Uploading {Math.round(uploadProgress * 100)}%
            </div>
          )}
        </div>
      </section>

      <aside className="card h-fit p-6">
        <h2 className="font-semibold">Recent projects</h2>
        <div className="mt-2">
          <RecentProjects />
        </div>
      </aside>
    </div>
  );
}

function ModePreview({ mode }: { mode: SubtitleMode }) {
  const original = "Bom dia, tudo bem?";
  const translation = "早上好，你好吗？";
  return (
    <div className="mt-4 rounded-lg bg-gray-900 px-4 py-3 text-center text-sm text-white">
      {mode !== "translation" && <div>{original}</div>}
      {mode !== "original" && <div className="text-yellow-200">{translation}</div>}
    </div>
  );
}
