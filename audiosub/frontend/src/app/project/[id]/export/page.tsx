"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ExportContent, ExportFormat, ExportOrder, Project } from "@/lib/api";
import { languageName, useMeta } from "@/lib/meta";

interface Preset {
  label: string;
  format: ExportFormat;
  content: ExportContent;
  needsTranslation?: boolean;
}

const PRESETS: Preset[] = [
  { label: "Original SRT", format: "srt", content: "original" },
  { label: "Translated SRT", format: "srt", content: "translation", needsTranslation: true },
  { label: "Bilingual SRT", format: "srt", content: "bilingual", needsTranslation: true },
  { label: "Original VTT", format: "vtt", content: "original" },
  { label: "Translated VTT", format: "vtt", content: "translation", needsTranslation: true },
  { label: "TXT Transcript", format: "txt", content: "original" },
];

function download(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ExportPage() {
  const { id } = useParams<{ id: string }>();
  const meta = useMeta();
  const [project, setProject] = useState<Project | null>(null);
  const [format, setFormat] = useState<ExportFormat>("srt");
  const [content, setContent] = useState<ExportContent>("bilingual");
  const [order, setOrder] = useState<ExportOrder>("original_first");
  const [preview, setPreview] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getProject(id).then((p) => {
      setProject(p);
      if (!p.target_language) setContent("original");
    }).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    api.exportText(id, format, content, order)
      .then(({ text }) => {
        if (!cancelled) {
          setPreview(text.split("\n").slice(0, 24).join("\n"));
          setError(null);
        }
      })
      .catch((e) => !cancelled && (setPreview(""), setError(e.message)));
    return () => {
      cancelled = true;
    };
  }, [id, project, format, content, order]);

  async function exportFile(f: ExportFormat, c: ExportContent, o: ExportOrder = order) {
    try {
      const { filename, text } = await api.exportText(id, f, c, o);
      download(filename, text);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!project) return <p className="p-8 text-gray-500">{error ?? "Loading…"}</p>;
  const hasTranslation = !!project.target_language;
  const source = languageName(meta, project.detected_language ?? project.source_language);
  const target = languageName(meta, project.target_language);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Export — {project.filename}</h1>
          <p className="text-sm text-gray-500">
            {source}
            {hasTranslation ? ` → ${target}` : ""}
          </p>
        </div>
        <Link href={`/project/${id}/editor`} className="btn-secondary">← Back to editor</Link>
      </div>

      <div className="card p-5">
        <h2 className="font-medium">Quick export</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className="btn-secondary justify-start py-2"
              disabled={p.needsTranslation && !hasTranslation}
              onClick={() => exportFile(p.format, p.content)}
            >
              ⬇ {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card mt-4 grid gap-5 p-5 md:grid-cols-[260px_1fr]">
        <div className="space-y-4">
          <h2 className="font-medium">Custom export</h2>
          <fieldset>
            <legend className="label">Format</legend>
            {(["srt", "vtt", "txt"] as ExportFormat[]).map((f) => (
              <label key={f} className="mr-4 text-sm">
                <input type="radio" name="format" checked={format === f} onChange={() => setFormat(f)} /> {f.toUpperCase()}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="label">Content</legend>
            {([
              ["original", `Original (${source})`],
              ["translation", `Translation (${target})`],
              ["bilingual", "Bilingual"],
            ] as [ExportContent, string][]).map(([c, label]) => (
              <label key={c} className="block text-sm">
                <input type="radio" name="content" checked={content === c} disabled={c !== "original" && !hasTranslation}
                  onChange={() => setContent(c)} /> {label}
              </label>
            ))}
          </fieldset>
          {content === "bilingual" && (
            <fieldset>
              <legend className="label">Line order</legend>
              <label className="block text-sm">
                <input type="radio" name="order" checked={order === "original_first"} onChange={() => setOrder("original_first")} /> Original First
              </label>
              <label className="block text-sm">
                <input type="radio" name="order" checked={order === "translation_first"} onChange={() => setOrder("translation_first")} /> Translation First
              </label>
            </fieldset>
          )}
          <button className="btn-primary w-full" onClick={() => exportFile(format, content)}>Download</button>
        </div>
        <div>
          <div className="label">Preview</div>
          {error ? (
            <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
          ) : (
            <pre className="h-80 overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs leading-relaxed text-gray-100">{preview}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
