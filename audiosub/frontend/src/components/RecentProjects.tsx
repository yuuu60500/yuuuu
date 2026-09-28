"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Project } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";
import { languageName, useMeta } from "@/lib/meta";
import { StatusBadge } from "./StatusBadge";

export function RecentProjects() {
  const meta = useMeta();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setError(e.message));
  }, []);

  async function remove(p: Project) {
    if (!confirm(`Delete "${p.filename ?? "project"}" and its subtitles?`)) return;
    await api.deleteProject(p.id);
    setProjects((list) => list?.filter((x) => x.id !== p.id) ?? null);
  }

  if (error) return <p className="text-sm text-red-600">Could not load projects: {error}</p>;
  if (!projects) return <p className="text-sm text-gray-500">Loading…</p>;
  const visible = projects.filter((p) => p.filename);
  if (!visible.length) return <p className="text-sm text-gray-500">No projects yet.</p>;

  return (
    <ul className="divide-y divide-gray-100">
      {visible.map((p) => {
        const href = p.status === "READY" ? `/project/${p.id}/editor` : `/project/${p.id}/processing`;
        const source = languageName(meta, p.detected_language ?? p.source_language);
        return (
          <li key={p.id} className="flex items-center gap-3 py-3">
            <Link href={href} className="min-w-0 flex-1">
              <div className="truncate font-medium text-gray-900">{p.filename}</div>
              <div className="text-xs text-gray-500">
                {source}
                {p.target_language && p.subtitle_mode !== "original" ? ` → ${languageName(meta, p.target_language)}` : ""}
                {" · "}
                {formatDuration(p.duration)} · {formatDate(p.created_at)}
              </div>
            </Link>
            <StatusBadge status={p.status} />
            <button className="btn-icon" title="Delete project" onClick={() => remove(p)}>
              ✕
            </button>
          </li>
        );
      })}
    </ul>
  );
}
