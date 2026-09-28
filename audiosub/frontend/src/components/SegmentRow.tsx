"use client";

import { memo, useEffect, useRef } from "react";
import { Segment } from "@/lib/api";
import { TimeInput } from "./TimeInput";

export interface RowActions {
  play: (s: Segment) => void;
  edit: (s: Segment, patch: Partial<Segment>) => void;
  setTime: (s: Segment, field: "start_time" | "end_time", value: number) => boolean;
  setTimeToPlayhead: (s: Segment, field: "start_time" | "end_time") => void;
  toggleSelect: (s: Segment, shift: boolean) => void;
  split: (s: Segment) => void;
  mergeNext: (s: Segment) => void;
  addAfter: (s: Segment) => void;
  remove: (s: Segment) => void;
  retranslate: (s: Segment) => void;
}

function AutoTextarea({
  value,
  onChange,
  placeholder,
  label,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      aria-label={label}
      rows={1}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={`block w-full resize-none rounded border border-transparent bg-transparent px-1.5 py-1 text-sm leading-snug hover:border-gray-300 focus:border-indigo-500 focus:bg-white focus:outline-none ${className ?? ""}`}
    />
  );
}

function SegmentRowImpl({
  segment: s,
  index,
  active,
  selected,
  busy,
  translating,
  showTranslation,
  isLast,
  actions,
}: {
  segment: Segment;
  index: number;
  active: boolean;
  selected: boolean;
  busy: boolean;
  translating: boolean;
  showTranslation: boolean;
  isLast: boolean;
  actions: RowActions;
}) {
  const rowRef = useRef<HTMLDivElement>(null);
  const lowConfidence = s.confidence != null && s.confidence < 0.6;

  return (
    <div
      ref={rowRef}
      data-segment-id={s.id}
      onClick={(e) => {
        const tag = (e.target as HTMLElement).closest("textarea,input,button");
        if (!tag) actions.play(s);
      }}
      className={`group grid cursor-pointer grid-cols-[1.75rem_2.5rem_6.5rem_1fr] items-start gap-2 border-b border-gray-100 px-2 py-1.5 md:grid-cols-[1.75rem_2.5rem_6.5rem_1fr_1fr_auto] ${
        active ? "bg-indigo-50 ring-1 ring-inset ring-indigo-300" : selected ? "bg-sky-50" : "hover:bg-gray-50"
      }`}
    >
      <input
        type="checkbox"
        aria-label={`Select subtitle ${index + 1}`}
        className="mt-1.5"
        checked={selected}
        onChange={() => {}}
        onClick={(e) => actions.toggleSelect(s, e.shiftKey)}
      />
      <div className="pt-1 text-right font-mono text-xs text-gray-400">
        {active && <span className="mr-0.5 text-indigo-600">▶</span>}
        {index + 1}
        {lowConfidence && (
          <span title={`Low recognition confidence (${Math.round((s.confidence ?? 0) * 100)}%)`} className="ml-0.5 text-amber-500">
            •
          </span>
        )}
      </div>
      <div className="flex flex-col">
        <div className="flex items-center">
          <TimeInput label="Start time" value={s.start_time} onCommit={(v) => actions.setTime(s, "start_time", v)} />
          <button className="btn-icon h-5 w-5 text-[10px] opacity-0 group-hover:opacity-100" title="Set start to playhead"
            onClick={() => actions.setTimeToPlayhead(s, "start_time")}>⇤</button>
        </div>
        <div className="flex items-center">
          <TimeInput label="End time" value={s.end_time} onCommit={(v) => actions.setTime(s, "end_time", v)} />
          <button className="btn-icon h-5 w-5 text-[10px] opacity-0 group-hover:opacity-100" title="Set end to playhead"
            onClick={() => actions.setTimeToPlayhead(s, "end_time")}>⇥</button>
        </div>
      </div>
      <AutoTextarea
        label="Original text"
        value={s.original_text}
        onChange={(v) => actions.edit(s, { original_text: v })}
        placeholder="Original text"
      />
      <div className="col-span-4 col-start-1 md:col-span-1 md:col-start-auto">
        {showTranslation ? (
          <AutoTextarea
            label="Translation"
            value={s.translated_text ?? ""}
            onChange={(v) => actions.edit(s, { translated_text: v })}
            placeholder={translating ? "Translating…" : "Translation"}
            className={translating ? "animate-pulse text-gray-400" : "text-indigo-950"}
          />
        ) : (
          <span className="hidden md:block" />
        )}
      </div>
      <div className="col-span-4 flex flex-wrap items-center gap-0.5 md:col-span-1 md:opacity-40 md:group-hover:opacity-100">
        <button className="btn-icon" title="Play this subtitle" onClick={() => actions.play(s)}>▶</button>
        {showTranslation && (
          <button className="btn-icon" title="Retranslate" disabled={busy} onClick={() => actions.retranslate(s)}>↻</button>
        )}
        <button className="btn-icon" title="Split (at playhead, or in the middle)" disabled={busy} onClick={() => actions.split(s)}>✂</button>
        <button className="btn-icon" title="Merge with next" disabled={busy || isLast} onClick={() => actions.mergeNext(s)}>⤓</button>
        <button className="btn-icon" title="Add subtitle after" disabled={busy} onClick={() => actions.addAfter(s)}>＋</button>
        <button className="btn-icon hover:!text-red-600" title="Delete subtitle" disabled={busy} onClick={() => actions.remove(s)}>🗑</button>
      </div>
    </div>
  );
}

export const SegmentRow = memo(SegmentRowImpl);
