"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RowActions, SegmentRow } from "@/components/SegmentRow";
import { Select } from "@/components/Select";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { api, Project, Segment } from "@/lib/api";
import { useAutosave } from "@/lib/autosave";
import { formatTime } from "@/lib/format";
import { languageName, useMeta } from "@/lib/meta";

const MIN_GAP = 0.2;

function findActive(segments: Segment[], t: number): Segment | null {
  // Segments are sorted by start time; binary search the last one starting <= t.
  let lo = 0;
  let hi = segments.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segments[mid].start_time <= t) {
      found = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  const s = found >= 0 ? segments[found] : null;
  return s && t < s.end_time ? s : null;
}

const sortSegments = (list: Segment[]) =>
  [...list].sort((a, b) => a.start_time - b.start_time || a.segment_index - b.segment_index);

export default function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const meta = useMeta();
  const [project, setProject] = useState<Project | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [translatingIds, setTranslatingIds] = useState<Set<string>>(new Set());
  const [follow, setFollow] = useState(true);
  const [stopAtEnd, setStopAtEnd] = useState(false);
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const stopAt = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const lastSelected = useRef<string | null>(null);

  const state = useRef({ segments, project, currentTime, stopAtEnd });
  state.current = { segments, project, currentTime, stopAtEnd };

  const autosave = useAutosave(
    useCallback((saved: Segment) => {
      // Only take server-owned fields; local text may already be newer.
      setSegments((list) =>
        sortSegments(
          list.map((s) =>
            s.id === saved.id
              ? { ...s, updated_at: saved.updated_at, translation_language: saved.translation_language, segment_index: saved.segment_index }
              : s,
          ),
        ),
      );
    }, []),
  );

  const reload = useCallback(async () => {
    const [p, segs] = await Promise.all([api.getProject(id), api.listSegments(id)]);
    setProject(p);
    setSegments(sortSegments(segs));
    return p;
  }, [id]);

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [reload]);

  // Poll while a background translation runs.
  useEffect(() => {
    if (project?.status !== "TRANSLATING") return;
    const t = setInterval(async () => {
      const p = await api.getProject(id);
      setProject(p);
      if (p.status !== "TRANSLATING") {
        setTranslatingIds(new Set());
        await reload();
        if (p.status === "FAILED") setError(p.error_message ?? "Translation failed.");
        else setNotice("Translation updated.");
      }
    }, 1500);
    return () => clearInterval(t);
  }, [project?.status, id, reload]);

  // Smooth playhead tracking while playing.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const el = mediaRef.current;
      if (el) {
        if (stopAt.current !== null && el.currentTime >= stopAt.current) {
          el.pause();
          stopAt.current = null;
        }
        setCurrentTime(el.currentTime);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const active = useMemo(() => findActive(segments, currentTime), [segments, currentTime]);

  // Scroll the active subtitle into view.
  useEffect(() => {
    if (!follow || !active || !playing) return;
    const row = listRef.current?.querySelector(`[data-segment-id="${active.id}"]`);
    row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active, follow, playing]);

  const seek = useCallback((t: number, play = false, until: number | null = null) => {
    const el = mediaRef.current;
    if (!el) return;
    el.currentTime = t;
    setCurrentTime(t);
    stopAt.current = until;
    if (play) void el.play();
  }, []);

  const withBusy = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await autosave.flush();
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [autosave]);

  const actions: RowActions = useMemo(
    () => ({
      play: (s) => seek(s.start_time, true, state.current.stopAtEnd ? s.end_time : null),
      edit: (s, patch) => {
        setSegments((list) => list.map((x) => (x.id === s.id ? { ...x, ...patch } : x)));
        autosave.queue(s.id, patch);
      },
      setTime: (s, field, value) => {
        const current = state.current.segments.find((x) => x.id === s.id) ?? s;
        const start = field === "start_time" ? value : current.start_time;
        const end = field === "end_time" ? value : current.end_time;
        if (value < 0 || end <= start) {
          setError("End time must be after start time.");
          return false;
        }
        const rounded = Math.round(value * 1000) / 1000;
        setSegments((list) => sortSegments(list.map((x) => (x.id === s.id ? { ...x, [field]: rounded } : x))));
        autosave.queue(s.id, { [field]: rounded });
        return true;
      },
      setTimeToPlayhead: (s, field) => {
        const t = Math.round((mediaRef.current?.currentTime ?? state.current.currentTime) * 1000) / 1000;
        actions.setTime(s, field, t);
      },
      toggleSelect: (s, shift) => {
        setSelected((prev) => {
          const next = new Set(prev);
          const list = state.current.segments;
          if (shift && lastSelected.current) {
            const a = list.findIndex((x) => x.id === lastSelected.current);
            const b = list.findIndex((x) => x.id === s.id);
            if (a >= 0 && b >= 0) {
              for (let i = Math.min(a, b); i <= Math.max(a, b); i++) next.add(list[i].id);
              return next;
            }
          }
          if (next.has(s.id)) next.delete(s.id);
          else next.add(s.id);
          lastSelected.current = s.id;
          return next;
        });
      },
      split: (s) =>
        withBusy(async () => {
          const t = mediaRef.current?.currentTime ?? 0;
          const inside = t > s.start_time + 0.05 && t < s.end_time - 0.05;
          await api.splitSegment(s.id, inside ? t : undefined);
          await reload();
        }),
      mergeNext: (s) =>
        withBusy(async () => {
          const list = state.current.segments;
          const i = list.findIndex((x) => x.id === s.id);
          if (i < 0 || i + 1 >= list.length) return;
          await api.mergeSegments(id, [s.id, list[i + 1].id]);
          await reload();
        }),
      addAfter: (s) =>
        withBusy(async () => {
          const list = state.current.segments;
          const i = list.findIndex((x) => x.id === s.id);
          const nextStart = list[i + 1]?.start_time ?? (state.current.project?.duration ?? s.end_time + 3);
          const start = s.end_time;
          const end = Math.min(nextStart, start + 2);
          if (end - start < MIN_GAP) throw new Error("No room after this subtitle. Shorten it or the next one first.");
          const created = await api.addSegment(id, { start_time: start, end_time: Math.round(end * 1000) / 1000 });
          await reload();
          setTimeout(() => {
            listRef.current?.querySelector<HTMLTextAreaElement>(`[data-segment-id="${created.id}"] textarea`)?.focus();
          }, 50);
        }),
      remove: (s) =>
        withBusy(async () => {
          autosave.drop(s.id);
          await api.deleteSegment(s.id);
          setSegments((list) => list.filter((x) => x.id !== s.id));
          setSelected((prev) => {
            const next = new Set(prev);
            next.delete(s.id);
            return next;
          });
        }),
      retranslate: (s) => void retranslateIds([s.id]),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [id, seek, withBusy, reload, autosave.queue, autosave.drop],
  );

  async function retranslateIds(ids: string[]) {
    setTranslatingIds((prev) => new Set([...prev, ...ids]));
    await withBusy(async () => {
      const res = await api.translate(id, { segment_ids: ids });
      setProject(res.project);
      const byId = new Map((res.segments ?? []).map((s) => [s.id, s]));
      setSegments((list) => list.map((s) => byId.get(s.id) ?? s));
      if (res.untranslated.length) {
        setError(`${res.untranslated.length} line(s) could not be translated. Try ↻ again, or type the translation yourself.`);
      }
    });
    setTranslatingIds((prev) => {
      const next = new Set(prev);
      ids.forEach((x) => next.delete(x));
      return next;
    });
  }

  async function retranslateAll() {
    if (!confirm("Retranslate all subtitles? Manual edits to translations will be replaced.")) return;
    await withBusy(async () => {
      const res = await api.translate(id, {});
      setProject(res.project);
      setTranslatingIds(new Set(state.current.segments.map((s) => s.id)));
    });
  }

  async function mergeSelected() {
    const ids = segments.filter((s) => selected.has(s.id)).map((s) => s.id);
    await withBusy(async () => {
      await api.mergeSegments(id, ids);
      setSelected(new Set());
      await reload();
    });
  }

  async function deleteSelected() {
    if (!confirm(`Delete ${selected.size} subtitle(s)?`)) return;
    await withBusy(async () => {
      for (const sid of selected) {
        autosave.drop(sid);
        await api.deleteSegment(sid);
      }
      setSelected(new Set());
      await reload();
    });
  }

  async function addAtPlayhead() {
    await withBusy(async () => {
      const t = mediaRef.current?.currentTime ?? 0;
      const next = segments.find((s) => s.start_time > t);
      if (findActive(segments, t)) throw new Error("The playhead is inside a subtitle. Move it to a gap first.");
      const end = Math.min(next?.start_time ?? t + 2, t + 2);
      if (end - t < MIN_GAP) throw new Error("Not enough room at the playhead.");
      await api.addSegment(id, { start_time: Math.round(t * 1000) / 1000, end_time: Math.round(end * 1000) / 1000 });
      await reload();
    });
  }

  async function changeSettings(patch: { target_language?: string; domain?: string }) {
    try {
      setProject(await api.updateProject(id, patch));
      setNotice("Settings changed. Click “Retranslate All” to apply them (speech recognition is not re-run).");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (error && !project) return <p className="p-8 text-red-600">{error}</p>;
  if (!project) return <p className="p-8 text-gray-500">Loading…</p>;

  const hasTranslation = !!project.target_language;
  const translatingAll = project.status === "TRANSLATING";
  const missingIds = hasTranslation && !translatingAll
    ? segments.filter((s) => !s.translated_text?.trim() && s.original_text.trim()).map((s) => s.id)
    : [];
  const staleLanguage =
    hasTranslation && segments.some((s) => s.translated_text && s.translation_language && s.translation_language !== project.target_language);
  const saveLabel = {
    idle: "All changes saved",
    saved: "All changes saved",
    pending: "Editing…",
    saving: "Saving…",
    error: `Save failed — retrying (${autosave.lastError ?? ""})`,
  }[autosave.state];

  const overlay = active && (
    <div className="pointer-events-none text-center leading-snug">
      {project.subtitle_mode !== "translation" && (
        <div className="whitespace-pre-line text-base text-white [text-shadow:0_1px_3px_#000]">{active.original_text}</div>
      )}
      {project.subtitle_mode !== "original" && active.translated_text && (
        <div className="whitespace-pre-line text-base text-yellow-200 [text-shadow:0_1px_3px_#000]">{active.translated_text}</div>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-4">
      {/* Top bar */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold">{project.filename}</h1>
          <p className="text-xs text-gray-500">
            {languageName(meta, project.detected_language ?? project.source_language)}
            {hasTranslation ? ` → ${languageName(meta, project.target_language)}` : ""} · {segments.length} subtitles ·{" "}
            <span className={autosave.state === "error" ? "text-red-600" : ""}>{saveLabel}</span>
          </p>
        </div>
        <StatusBadge status={project.status} />
        <Link href={`/project/${id}/export`} className="btn-primary" onClick={() => void autosave.flush()}>
          Export
        </Link>
      </div>

      {error && (
        <div className="mb-3 flex items-start justify-between rounded-md bg-red-50 p-3 text-sm text-red-700">
          <span>{error}</span>
          <button className="btn-icon" onClick={() => setError(null)}>✕</button>
        </div>
      )}
      {missingIds.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
          <span>{missingIds.length} subtitle(s) have no translation yet.</span>
          <button className="btn-secondary" disabled={busy} onClick={() => retranslateIds(missingIds)}>
            ↻ Translate missing lines
          </button>
        </div>
      )}
      {notice && (
        <div className="mb-3 flex items-start justify-between rounded-md bg-indigo-50 p-3 text-sm text-indigo-800">
          <span>{notice}</span>
          <button className="btn-icon" onClick={() => setNotice(null)}>✕</button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(320px,440px)_1fr]">
        {/* Left: player and settings */}
        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <div className="card overflow-hidden">
            <div className="relative bg-black">
              {project.media_kind === "video" ? (
                <video
                  ref={mediaRef}
                  src={api.mediaUrl(id)}
                  controls
                  className="aspect-video w-full"
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  onSeeked={(e) => setCurrentTime(e.currentTarget.currentTime)}
                />
              ) : (
                <div className="p-3">
                  <div className="flex min-h-24 items-center justify-center px-2 py-4">{overlay || <span className="text-sm text-gray-500">♪</span>}</div>
                  <audio
                    ref={mediaRef}
                    src={api.mediaUrl(id)}
                    controls
                    className="w-full"
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    onSeeked={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  />
                </div>
              )}
              {project.media_kind === "video" && overlay && (
                <div className="absolute inset-x-2 bottom-12">{overlay}</div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-xs text-gray-600">
              <span className="font-mono">{formatTime(currentTime)}</span>
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow playback
              </label>
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={stopAtEnd} onChange={(e) => setStopAtEnd(e.target.checked)} /> Stop at end of subtitle
              </label>
            </div>
          </div>

          <div className="card space-y-3 p-3">
            <div className="grid grid-cols-2 gap-3">
              <Select id="target" label="Translation" value={project.target_language ?? ""}
                options={[{ code: "", name: "— none —" }, ...(meta?.target_languages ?? [])]}
                onChange={(v) => v && changeSettings({ target_language: v })} disabled={busy || translatingAll} />
              <Select id="domain" label="Domain" value={project.domain} options={meta?.domains ?? []}
                onChange={(v) => changeSettings({ domain: v })} disabled={busy || translatingAll} />
            </div>
            {staleLanguage && (
              <p className="text-xs text-amber-700">Some translations are in another language than the selected one.</p>
            )}
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" disabled={!hasTranslation || busy || translatingAll} onClick={retranslateAll}>
                {translatingAll ? `Translating… ${Math.round((project.steps.translation?.progress ?? 0) * 100)}%` : "↻ Retranslate All"}
              </button>
              <Link href="/glossary" className="btn-secondary">Glossary</Link>
            </div>
          </div>
        </div>

        {/* Right: timeline and subtitle list */}
        <div className="min-w-0 space-y-3">
          <Timeline
            duration={project.duration ?? segments[segments.length - 1]?.end_time ?? 0}
            segments={segments}
            currentTime={currentTime}
            activeId={active?.id ?? null}
            selected={selected}
            playing={playing}
            onSeek={(t) => seek(t)}
            onSegmentClick={(s) => actions.play(s)}
          />

          <div className="card">
            <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-3 py-2 text-sm">
              {selected.size > 0 ? (
                <>
                  <span className="font-medium">{selected.size} selected</span>
                  {hasTranslation && (
                    <button className="btn-secondary" disabled={busy || translatingAll} onClick={() => retranslateIds([...selected])}>
                      ↻ Retranslate Selected
                    </button>
                  )}
                  <button className="btn-secondary" disabled={busy || selected.size < 2} onClick={mergeSelected}>Merge</button>
                  <button className="btn-danger" disabled={busy} onClick={deleteSelected}>Delete</button>
                  <button className="btn-icon" title="Clear selection" onClick={() => setSelected(new Set())}>✕</button>
                </>
              ) : (
                <>
                  <span className="text-gray-500">Click a subtitle to play it. Edits save automatically.</span>
                  <button className="btn-secondary ml-auto" disabled={busy} onClick={addAtPlayhead}>＋ Add at playhead</button>
                </>
              )}
            </div>
            <div className="hidden grid-cols-[1.75rem_2.5rem_6.5rem_1fr_1fr_auto] gap-2 border-b border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid">
              <span />
              <span className="text-right">#</span>
              <span>Start / End</span>
              <span>Original · {languageName(meta, project.detected_language ?? project.source_language)}</span>
              <span>{hasTranslation ? `Translation · ${languageName(meta, project.target_language)}` : ""}</span>
              <span className="w-[11rem]" />
            </div>
            <div ref={listRef}>
              {segments.length === 0 && <p className="p-6 text-center text-sm text-gray-500">No subtitles.</p>}
              {segments.map((s, i) => (
                <SegmentRow
                  key={s.id}
                  segment={s}
                  index={i}
                  active={s.id === active?.id}
                  selected={selected.has(s.id)}
                  busy={busy}
                  translating={translatingIds.has(s.id)}
                  showTranslation={hasTranslation}
                  isLast={i === segments.length - 1}
                  actions={actions}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
