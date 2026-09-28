"use client";

import { useEffect, useRef, useState } from "react";
import { Segment } from "@/lib/api";
import { formatTime } from "@/lib/format";

export function Timeline({
  duration,
  segments,
  currentTime,
  activeId,
  selected,
  playing,
  onSeek,
  onSegmentClick,
}: {
  duration: number;
  segments: Segment[];
  currentTime: number;
  activeId: string | null;
  selected: Set<string>;
  playing: boolean;
  onSeek: (t: number) => void;
  onSegmentClick: (s: Segment) => void;
}) {
  const [pxPerSec, setPxPerSec] = useState(40);
  const scroller = useRef<HTMLDivElement>(null);
  const width = Math.max(duration * pxPerSec, 100);

  // Keep the playhead in view while playing.
  useEffect(() => {
    const el = scroller.current;
    if (!el || !playing) return;
    const x = currentTime * pxPerSec;
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 80) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [currentTime, pxPerSec, playing]);

  const tickEvery = pxPerSec >= 80 ? 1 : pxPerSec >= 30 ? 5 : pxPerSec >= 10 ? 15 : 60;
  const ticks: number[] = [];
  for (let t = 0; t <= duration; t += tickEvery) ticks.push(t);

  return (
    <div className="card p-2">
      <div className="mb-1 flex items-center justify-between px-1 text-xs text-gray-500">
        <span>Timeline</span>
        <div className="flex items-center gap-1">
          <button className="btn-icon" title="Zoom out" onClick={() => setPxPerSec((v) => Math.max(2, v / 1.5))}>−</button>
          <button className="btn-icon" title="Zoom in" onClick={() => setPxPerSec((v) => Math.min(300, v * 1.5))}>+</button>
        </div>
      </div>
      <div ref={scroller} className="overflow-x-auto">
        <div
          className="relative h-16 cursor-pointer select-none"
          style={{ width }}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            onSeek(Math.max(0, Math.min(duration, (e.clientX - rect.left) / pxPerSec)));
          }}
        >
          {ticks.map((t) => (
            <div key={t} className="absolute top-0 h-full border-l border-gray-100" style={{ left: t * pxPerSec }}>
              <span className="ml-0.5 text-[10px] text-gray-400">{formatTime(t, false)}</span>
            </div>
          ))}
          {segments.map((s) => {
            const active = s.id === activeId;
            return (
              <div
                key={s.id}
                title={s.original_text}
                onClick={(e) => {
                  e.stopPropagation();
                  onSegmentClick(s);
                }}
                className={`absolute top-5 h-9 overflow-hidden rounded border px-1 text-[10px] leading-tight ${
                  active
                    ? "border-indigo-600 bg-indigo-500 text-white"
                    : selected.has(s.id)
                      ? "border-indigo-400 bg-indigo-100 text-indigo-900"
                      : "border-sky-300 bg-sky-100 text-sky-900 hover:bg-sky-200"
                }`}
                style={{ left: s.start_time * pxPerSec, width: Math.max(2, (s.end_time - s.start_time) * pxPerSec) }}
              >
                {s.original_text}
              </div>
            );
          })}
          <div className="pointer-events-none absolute top-0 h-full w-px bg-red-500" style={{ left: currentTime * pxPerSec }} />
        </div>
      </div>
    </div>
  );
}
